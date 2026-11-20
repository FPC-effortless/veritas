"""Append native operator-private evidence from already-verified aggregate receipts."""
from datetime import UTC,datetime
from pathlib import Path
import json,sys
from investigation_world.evidence import EvidenceRecord,serialize_evidence_record
from research_lab.core import Controller
from research_lab.evidence import put_node,link
from trainlab.runner import contained_file,digest
import conductor

def register(root,study):
    if study not in ('cog084','cog086'):raise ValueError('scope refused')
    bindings=[]
    stage_records={}
    for phase in ('fit','predict','verify'):
        d=root/study/phase
        r=d/'stage-receipt.json';n=conductor.provenance(r,phase,study)
        stage_records[phase]=(d,n)
        bindings.append(dict(artifact_id=phase+'-receipt',role='stage-receipt',content_sha256=digest(r)))
    d,r=stage_records['verify']
    path=contained_file(d/'runs'/r['id']/'output','aggregates.json')
    h=digest(path)
    if h!=r['artifacts']['aggregates.json']:raise ValueError('aggregate drift')
    doc=json.loads(path.read_bytes())
    if doc['qualification']!='NOT_QUALIFIED' or doc['study']!=study or len(doc['runs'])!=3:
        raise ValueError('scope/qualification mismatch')
    scope=digest(d/'closure'/'PROTOCOL_ROLE.md')
    worker=digest(d/'closure'/('stage_084_086_worker.py' if study=='cog084' else 'stage_086_worker.py'))
    ev=EvidenceRecord(evidence_type='research.life_stage_diagnostic',outcome='OBSERVED',visibility='operator_private',
          claim='Bounded constructed three-seed diagnostic; observations only, NOT_QUALIFIED',
          subjects=[dict(kind='experiment',subject_id=study,content_sha256=scope)],
          producer=dict(producer_id='cog-life-stage-pilot',producer_version='1',content_sha256=worker),
          policy=dict(policy_id='cog-life-role-separated-diagnostic',policy_version='1',content_sha256=scope),
          artifacts=[*bindings,dict(artifact_id='bounded-aggregate',role='observation',content_sha256=h)],
          observed_at=datetime.now(UTC),provenance={'qualification':'NOT_QUALIFIED','independent_exact_stage_reviews_recorded':True})
    b=serialize_evidence_record(ev); EvidenceRecord.model_validate_json(b)
    out=root/study/'OPERATOR_PRIVATE_EVIDENCE.json'
    with out.open('xb') as f:f.write(b)
    out.chmod(0o600)
    lab=Controller(root/'ledger')
    id=f'{study}.observed'
    put_node(lab,id,'evidence',{'qualification':'NOT_QUALIFIED','evidence_id':ev.evidence_id,'sha256':digest(out)})
    link(lab,f'{study}.verify.receipt','supports',id)
    return {'study':study,'qualification':'NOT_QUALIFIED','outcome':ev.outcome.value,'sha256':digest(out),'evidence_id':ev.evidence_id}
if __name__=='__main__':print(json.dumps(register(Path(sys.argv[1]).resolve(),sys.argv[2]),sort_keys=True))
