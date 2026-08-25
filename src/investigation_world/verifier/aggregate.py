from investigation_world.core.models import CanonicalWorld, InvestigationResult, VerificationResult

def verify_identity(result: InvestigationResult, world: CanonicalWorld) -> tuple[float, int]:
    false_merges = sum(1 for x in result.identity_assertions if x.get('same_entity') is True and x.get('left') != x.get('right'))
    false_splits = sum(1 for x in result.identity_assertions if x.get('same_entity') is False and x.get('left') == x.get('right'))
    return max(0.0, 1.0 - min(1.0, .85 * false_merges + .15 * false_splits)), false_merges

def verify_relationships(result: InvestigationResult, world: CanonicalWorld) -> tuple[float, set[tuple[str, str, str]]]:
    truth = {(r.subject_id, r.predicate.value, r.object_id) for r in world.relationships}
    predicted = {(x.get('subject'), x.get('predicate'), x.get('object')) for x in result.relationships}
    return len(predicted & truth) / max(1, len(truth)), predicted - truth

def verify_evidence(result: InvestigationResult, world: CanonicalWorld, correct: set[tuple[str, str, str]]) -> float:
    cited = {x.get('document_id') for x in result.evidence}
    docs = {d.document_id: d for d in world.documents}
    supported = {claim for claim in correct if any(claim[0] in docs.get(doc, type('D', (), {'body': ''})()).body and claim[2] in docs.get(doc, type('D', (), {'body': ''})()).body for doc in cited)}
    return len(supported) / max(1, len(correct))

def verify(result: InvestigationResult, world: CanonicalWorld, task_answerable: bool=True, budget_spent: int=0, budget_total: int=40):
    identity, false_merges = verify_identity(result, world)
    relationships, unsupported = verify_relationships(result, world)
    predicted = {(x.get('subject'), x.get('predicate'), x.get('object')) for x in result.relationships}
    correct = predicted - unsupported
    evidence_support = verify_evidence(result, world, correct)
    abstention = 1.0 if (not task_answerable and result.unknowns) else (0.0 if not task_answerable else 1.0)
    calibration = max(0.0, 1 - abs(result.overall_confidence - relationships))
    efficiency = max(0.0, 1 - budget_spent / max(1, budget_total))
    provenance = evidence_support
    reward = max(0.0, .25*identity + .25*relationships + .15*evidence_support + .1*provenance + .1*abstention + .1*calibration + .05*efficiency)
    return VerificationResult(identity=identity, relationships=relationships, temporal=relationships, evidence_support=evidence_support, provenance=provenance, calibration=calibration, abstention=abstention, efficiency=efficiency, false_merge_count=false_merges, unsupported_claim_count=len(unsupported), overall_reward=reward).model_dump()
