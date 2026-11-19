"""Check archived receipts/content hashes and compare all deterministic observations."""
import argparse
import json
import tempfile
from pathlib import Path
from zipfile import ZipFile
from forge_data.dataset import Dataset
from investigation_world.evidence import EvidenceRecord
from trainlab.runner import digest, verify_run

def read_bundle(archive):
    with tempfile.TemporaryDirectory() as tmp, ZipFile(archive) as bundle:
        root=Path(tmp)
        bundle.extractall(root)
        run,=(root/'runs').iterdir()
        if not verify_run(run)['valid']:
            raise ValueError('Run receipt failed verification')
        record=EvidenceRecord.model_validate_json((root/'evidence.json').read_text())
        Dataset(root/'dataset',manifest_sha256=record.subjects[0].content_sha256)
        path=run/'output/results.json'
        if digest(path)!=record.artifacts[0].content_sha256:
            raise ValueError('Veritas evidence hash mismatch')
        return json.loads(path.read_text())

def scientific(value):
    if isinstance(value,dict):
        return {k:scientific(v) for k,v in value.items() if '_ns' not in k and 'bytes' not in k and k!='ns_per_query'}
    return value

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('archive',type=Path)
    parser.add_argument('--replay',type=Path)
    args=parser.parse_args()
    rows=read_bundle(args.archive)
    if args.replay and scientific(rows)!=scientific(read_bundle(args.replay)):
        raise ValueError('Scientific observations differ')
    print(f'Validated {len(rows)} seed records')
