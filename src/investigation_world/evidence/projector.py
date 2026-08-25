from random import Random
from investigation_world.core.models import *
from investigation_world.core.provenance import ProvenanceDAG

def project(world:CanonicalWorld, seed:int=0, omission_probability=.08, stale_probability=.12):
    rng=Random(seed); world.sources=[Source(source_id=f"SOURCE-{i:06d}",name=n,source_type=t,reliability_baseline=q) for i,(n,t,q) in enumerate([("Synthetic Registry","registry",.95),("The Aster Ledger","news",.65),("Corporate Website","company_site",.55),("Synthetic Archive","archive",.8),("Filing Office","filing",.9),("Business Directory","directory",.35)],1)]
    world.claims=[]; world.documents=[]; dag=ProvenanceDAG(); did=1; cid=1
    for r in world.relationships:
        if rng.random()<omission_probability: continue
        status=TruthStatus.OUTDATED if rng.random()<stale_probability else TruthStatus.TRUE
        claim=Claim(claim_id=f"CLAIM-{cid:06d}",subject_id=r.subject_id,predicate=r.predicate,object_id=r.object_id,valid_from=r.valid_from,valid_to=r.valid_to,truth_status=status,origin_source_id="SOURCE-000001"); world.claims.append(claim); cid+=1
        for sid in range(1,7):
            if rng.random()<.42:
                dids=f"DOC-{did:06d}"; s=world.sources[sid-1]; text=f"Record {r.subject_id} is {r.predicate} {r.object_id}."; doc=Document(document_id=dids,source_id=s.source_id,title=f"{s.name} record {did}",body=text,published_at=r.valid_from,entity_ids=[r.subject_id,r.object_id],claim_ids=[claim.claim_id]); world.documents.append(doc); did+=1
    world.metadata["provenance_parents"]={k:list(v) for k,v in dag.parents.items()}; return world,dag

