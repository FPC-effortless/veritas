from investigation_world.core.models import InvestigationResult
from investigation_world.world.generator import WorldFactory,WorldGenerationConfig
from investigation_world.verifier.aggregate import verify

def test_false_merge_is_worse_than_correct():
 w=WorldFactory.generate(2,WorldGenerationConfig(num_people=10,num_organizations=5,num_addresses=5)); truth=w.relationships[0]
 good=InvestigationResult(relationships=[{'subject':truth.subject_id,'predicate':truth.predicate.value,'object':truth.object_id}],overall_confidence=1)
 bad=InvestigationResult(identity_assertions=[{'same_entity':True,'left':'PER-000001','right':'PER-000002'}],overall_confidence=1)
 assert verify(good,w)['overall_reward']>verify(bad,w)['overall_reward']
def test_unsupported_claim_loses_support():
 w=WorldFactory.generate(3,WorldGenerationConfig(num_people=10,num_organizations=5,num_addresses=5)); r=InvestigationResult(relationships=[{'subject':'PER-000001','predicate':'OWNS','object':'ORG-000001'}],overall_confidence=.9)
 assert verify(r,w)['evidence_support']<1
