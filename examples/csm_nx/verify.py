"""Verify the archived public run, then optionally compare an independent replay."""
import argparse
import json
import tempfile
from pathlib import Path
from zipfile import ZipFile

from forge_data.dataset import Dataset
from investigation_world.evidence import EvidenceRecord
from trainlab.runner import digest, verify_run

parser = argparse.ArgumentParser()
parser.add_argument('archive',type=Path)
parser.add_argument('--replay',type=Path)
args = parser.parse_args()
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    with ZipFile(args.archive) as z:
        z.extractall(root)
    run, = (root/'runs').iterdir()
    assert verify_run(run)['valid']
    rec = EvidenceRecord.model_validate_json((root/'evidence.json').read_text())
    Dataset(root/'dataset',manifest_sha256=rec.subjects[0].content_sha256)
    output = run/'output/results.json'
    assert rec.artifacts[0].content_sha256 == digest(output)
    if args.replay:
        replay, = (args.replay/'runs').glob('*/output/results.json')
        a,b = (json.loads(p.read_text()) for p in (output,replay))
        for rows in (a,b):
            perf = rows.pop('NX-009')
            assert all(v[k][3] == 1 for v in perf.values() for k in ('1','2','4'))
        assert a == b
    print('Verified',rec.record_id)
