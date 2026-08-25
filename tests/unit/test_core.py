from datetime import date
from investigation_world.world.generator import WorldFactory,WorldGenerationConfig,validate_world
from investigation_world.core.provenance import ProvenanceDAG

def test_seed_reproducibility():
 c=WorldGenerationConfig(num_people=20,num_organizations=10,num_addresses=10)
 assert WorldFactory.generate(42,c).model_dump()==WorldFactory.generate(42,c).model_dump()
 assert WorldFactory.generate(42,c).model_dump()!=WorldFactory.generate(43,c).model_dump()
def test_scale_and_temporal_query():
 w=WorldFactory.generate(7,WorldGenerationConfig(num_people=100,num_organizations=50,num_addresses=50))
 assert len(w.people)==100 and len(w.organizations)==50 and len(w.relationships)>=300 and len(w.events)>=200
 assert w.relationships_at(date(2020,1,1))
 assert not validate_world(w)
def test_provenance_laundering():
 d=ProvenanceDAG(); d.add_citation('B','A'); d.add_citation('C','B'); d.add_citation('D','C')
 assert d.independent_source_count(['B','C','D'])==1
 try:d.add_citation('A','D'); assert False
 except ValueError: pass
