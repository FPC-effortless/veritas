import tempfile
from pathlib import Path
import unittest

from investigation_world.life import Action, LifeWorld, LOCATIONS, MILESTONES, OBJECTS, PEOPLE
from investigation_world.life.runtime import hash_obj

class LifeWorldTests(unittest.TestCase):
 def test_seeded_autonomy_exact_and_local(self):
     a, b = LifeWorld(81), LifeWorld(81)
     assert len(PEOPLE) == 8 and len(LOCATIONS) == 3
     genesis = a.port("p0").observe()
     assert len(genesis) == 1 and genesis[0].payload == {
         "person": "p0", "location": a.truth()["people"]["p0"], "stage": "childhood",
     }
     a.advance(27)
     for t in (3, 12, 13, 24, 27): b.advance(t)
     assert a.event_log() == b.event_log()
     assert a.event_log() != LifeWorld(82).event_log()
     assert {e["kind"] for e in a.event_log()} >= {"placement","promise","testimony","request","arrival"}
     assert [x.payload["stage"] for x in a.port("p0").observe() if x.kind=="milestone"] == list(MILESTONES.values())
     for person in PEOPLE:
         rows=a.port(person).observe()
         assert [r.seq for r in rows] == list(range(1,len(rows)+1))
         assert a.port(person).observe(since_seq=len(rows)) == ()
         assert all(set(r.parents) <= {x.id for x in rows[:r.seq-1]} for r in rows)
         assert all("seed" not in r.payload for r in rows)

 def test_hidden_insertion_does_not_disturb_other_agent_prefix_ids_or_counts(self):
     a,b=LifeWorld(88),LifeWorld(88)
     a.advance(5); b.advance(5)
     hidden = b.inject("hidden_marker",{"private":"truth"},("p1",))
     x=a.inject("seen",{"thing":"cup"},("p0",))
     y=b.inject("seen",{"thing":"cup"},("p0",))
     a.inject("next",{"thing":"box"},("p0",),parents=(x,))
     b.inject("next",{"thing":"box"},("p0",),parents=(y,hidden))
     assert a.port("p0").observe()==b.port("p0").observe()
     assert b.port("p0").observe()[-1].parents==(b.port("p0").observe()[-2].id,)
     assert b.provenance_roots(y,hidden)==(hidden,y)
     assert all(x.kind!="seen" for x in b.port("p1").observe())

 def test_typed_scope_citations_and_idempotency(self):
     w=LifeWorld(3);agent=w.port("p0")
     o=w.truth()["objects"]["o0"]
     assert agent.act(Action("move",o["location"])).applied
     receipt=agent.act(Action("inspect","o0"));assert receipt.applied
     target=next(l for l in LOCATIONS if l!=o["location"])
     wrong=agent.act(Action("place","o0",target,expected_version=2));assert wrong.authorized and not wrong.applied
     legal=Action("place","o0",target,(receipt.observation_id,),0,"retry-token")
     first=agent.act(legal);assert first.authorized and first.applied
     assert w.truth()["objects"]["o0"]["location"]==target
     n=len(w.event_log()); again=agent.act(legal)
     assert again.replayed and again.cost==0 and first.observation_id==again.observation_id
     assert n==len(w.event_log())
     with self.assertRaisesRegex(ValueError,"idempotency"):
         agent.act(Action("move","school",request_id="retry-token"))
     closed = w.port("p1").act(Action("testify","p0","my claim",(receipt.observation_id,)))
     assert not closed.authorized and not closed.applied
     assert agent.observe()[-1].kind=="place"
     links=agent.observe()[-1].parents
     assert links==(receipt.observation_id,)

 def test_checkpoint_replay_resume_and_counterfactual_fork(self):
     tmp_path=Path(self.enterContext(tempfile.TemporaryDirectory()))
     w=LifeWorld(81);w.advance(12)
     w.register_probe("toy",{"on":{"sensor":1}},allowed=("p0",))
     assert not w.port("p1").act(Action("probe","toy","on")).authorized
     r=w.port("p0").act(Action("probe","toy","on",request_id="persist"))
     assert r.applied and w.port("p0").observe()[-1].payload["effect"]["observation"]=={"sensor":1}
     p=tmp_path/"state.json";w.save(p);v=LifeWorld.load(p)
     assert v.event_log()==w.event_log() and v.truth()==w.truth()
     assert v.port("p0").act(Action("probe","toy","on",request_id="persist")).replayed
     prefix=w.event_log();f=w.fork(len(prefix)-1)
     assert f.event_log()==prefix[:-1] and w.event_log()==prefix
     v.advance(31);w.advance(31)
     assert v.event_log()==w.event_log()

 def test_recompute_rejects_false_authority_even_with_valid_rehashed_chain(self):
     tmp_path=Path(self.enterContext(tempfile.TemporaryDirectory()))
     w=LifeWorld(81);w.port("p0").act(Action("testify","p1","claim"))
     rows=list(w.event_log())
     e=rows[-1];e["public"]["authorized"]=False
     e["digest"]=hash_obj({k:v for k,v in e.items() if k!="digest"})
     with self.assertRaisesRegex(ValueError,"replay diverged"):
         LifeWorld.replay(rows)
     p=tmp_path/"bad.json";p.write_text('{"schema":"veritas.cog-life.v1","schema":"veritas.cog-life.v1","events":[]}')
     with self.assertRaisesRegex(ValueError,"duplicate"):
         LifeWorld.load(p)

 def test_returned_visible_payload_is_a_defensive_copy(self):
     w=LifeWorld(0);p=w.port("p0")
     p.observe()[0].payload["location"]="private_modify"
     assert p.observe()[0].payload["location"] in LOCATIONS
     log=w.event_log();log[0]["instruction"]["seed"]=999
     assert w.event_log()[0]["instruction"]["seed"]==0

 def test_native_factory_bound_and_machine_experience_privacy(self):
     from investigation_world.life.native_bridge import life_experience, life_trajectory
     from investigation_world.world.generator import WorldFactory, WorldGenerationConfig
     cfg=WorldGenerationConfig(num_people=8,num_addresses=3,num_organizations=2)
     source=WorldFactory.generate(81,cfg)
     w=LifeWorld.from_world_factory(81)
     binding=w.native_identity()
     assert binding["world_id"]==source.world_id
     assert set(binding["person_ids"].values())==set(source.people)
     assert set(binding["location_ids"].values())==set(source.addresses)
     for a,d in binding["initial_locations"].items():
         native=binding["person_ids"][a];loc=binding["location_ids"][d]
         assert any(r.subject_id==native and r.object_id==loc and r.predicate.name=="RESIDES_AT"
                    and r.created_by_event_id==binding["residence_witnesses"][a]
                    for r in source.relationships_at(cfg.timeline_start))
         assert w.port(a).observe()[0].payload["location"]==d
     w.advance(25);w.inject("hidden_note",{"marker":"private"},("p1",))
     e=life_experience(w,"p0");t=life_trajectory(w,"p0")
     assert e.trajectory.trajectory_id==t.trajectory_id and e.maturity.value=="E0_TRACEABLE"
     assert t.world.world_bundle.digest==binding["world_digest"]
     assert t.visibility.value==e.visibility.value=="evaluator_private"
     assert all(row.event_type!="hidden_note" for row in t.events)
     assert t.original_evaluation.reward==0.0
     with self.assertRaises(ValueError):e.public_payload()
     with self.assertRaises(ValueError):t.public_payload()

 def test_fixture_cannot_impersonate_native_event_or_source(self):
     w=LifeWorld(2);n=len(w.event_log())
     with self.assertRaises(ValueError):w.inject("placement",{"object":"o0"},("p0",))
     with self.assertRaises(ValueError):w.inject("sensor",{},("p0",),source="p2")
     with self.assertRaises(ValueError):w.inject("sensor",{},("p0",),parents=(99,))
     assert len(w.event_log())==n

if __name__=="__main__":
    unittest.main()
