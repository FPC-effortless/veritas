from random import Random
from investigation_world.core.models import CanonicalWorld,Claim,Document,Source,SourceType,TruthStatus
from investigation_world.core.provenance import ProvenanceDAG

def project(world:CanonicalWorld, seed:int=0, omission_probability:float=.08, stale_probability:float=.12):
    rng=Random(seed); specs=[('Synthetic Registry',SourceType.REGISTRY,.95),('Aster Ledger',SourceType.NEWS,.65),('Corporate Website',SourceType.COMPANY_SITE,.55),('Synthetic Archive',SourceType.ARCHIVE,.8),('Filing Office',SourceType.FILING,.9),('Business Directory',SourceType.DIRECTORY,.35)]
    world.sources=[Source(source_id=f'SOURCE-{i:06d}',name=n,source_type=t,reliability_baseline=q) for i,(n,t,q) in enumerate(specs,1)]
    world.claims=[]; world.documents=[]; dag=ProvenanceDAG(); cid=did=1
    for rel in world.relationships:
        if rng.random()<omission_probability: continue
        claim=Claim(claim_id=f'CLAIM-{cid:06d}',subject_id=rel.subject_id,predicate=rel.predicate,object_id=rel.object_id,valid_from=rel.valid_from,valid_to=rel.valid_to,truth_status=TruthStatus.OUTDATED if rng.random()<stale_probability else TruthStatus.TRUE,origin_source_id='SOURCE-000001')
        world.claims.append(claim); cid+=1; previous=None
        for source in world.sources:
            if rng.random()>.42: continue
            doc_id=f'DOC-{did:06d}'; text=f'Record {rel.subject_id} is {rel.predicate.value} {rel.object_id}.'
            doc=Document(document_id=doc_id,source_id=source.source_id,title=f'{source.name} record {did}',body=text,published_at=rel.valid_from,entity_ids=[rel.subject_id,rel.object_id],claim_ids=[claim.claim_id],cites_document_ids=[previous] if previous and rng.random()<.3 else [],is_stale=claim.truth_status==TruthStatus.OUTDATED)
            world.documents.append(doc)
            if doc.cites_document_ids: dag.add_citation(doc_id,doc.cites_document_ids[0])
            previous=doc_id; did+=1
    world.metadata['provenance_parents']={k:sorted(v) for k,v in dag.parents.items()}; return world,dag
