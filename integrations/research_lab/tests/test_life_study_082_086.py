import unittest
from types import SimpleNamespace as Frame
from research_lab.life_study_082_086 import (
    BeliefLedger,BeliefObservation,CausalEstimator,CausalObservation,
    DecisionInput,GroundedLearner,PracticeObservation,ReplayLearner,
    WitnessedAction,from_visible_frame,graded_commit,
)

class LifeBoundedTools(unittest.TestCase):
    def test_082_witnessed_effects_then_novel_composition(self):
        menu=[f'k{i}' for i in range(8)]
        x=GroundedLearner(menu);y=GroundedLearner(menu,exact_only=True)
        z=GroundedLearner(menu)
        for i,(action,phrase,old,new) in enumerate([
            ('k1','blen into', (0,0,0),(1,0,0)),
            ('k1','blen nearby',(1,2,0),(2,2,0)),
            ('k4','fez across',(0,0,0),(0,1,0)),
            ('k4','fez onward',(2,0,1),(2,1,1)),
        ]):
            w=WitnessedAction(i,f'utter{i}',action,phrase,old,new,f'effect{i}')
            x.learn(w);y.learn(w)
        self.assertEqual(x.rank('blen later'),('k1',))
        self.assertEqual(y.rank('blen later'),())
        self.assertEqual(x.rank('unseen-unlearned'),())
        self.assertEqual(x.synthesize((0,0,0),(1,1,0)),('k1','k4'))
        self.assertIsNone(x.synthesize((0,0,0),(1,1,0),max_steps=1))
        self.assertIsNone(z.synthesize((0,0,0),(1,1,0)))
        with self.assertRaisesRegex(ValueError,'repeated'):
            x.learn(w)

    def test_082_requires_independent_starts_and_refuses_conflict(self):
        x=GroundedLearner([f'k{i}' for i in range(8)])
        for i in range(2):x.learn(WitnessedAction(i,f'a{i}','k1','blen',(0,0,0),(1,0,0),f'b{i}'))
        self.assertEqual(x.inferred_effects(),{})
        x.learn(WitnessedAction(2,'a2','k1','blen',(2,0,0),(4,0,0),'b2'))
        self.assertEqual(x.inferred_effects(),{})

    def test_083_duplicate_lineage_is_one_signal_not_fact(self):
        x=BeliefLedger()
        x.update(BeliefObservation(1,'a','c','sense','report',1,'source0'))
        initial=x.belief('c')
        x.update(BeliefObservation(2,'b','c','echo','report',1,'source0'))
        self.assertEqual(x.belief('c'),initial)
        self.assertEqual(initial['level'],'provisional')
        with self.assertRaises(ValueError):
            x.update(BeliefObservation(3,'c','c','echo','firsthand',1,'source0'))
        x.update(BeliefObservation(4,'d','c','eye','firsthand',0,None,'obs0'))
        self.assertEqual(x.belief('c')['probability_one'],0.)
        self.assertEqual(x.belief('c')['level'],'observed')

    def test_084_separates_safe_probe_from_passive_frozen(self):
        p,a,f=map(CausalEstimator,('probe','passive','frozen'))
        for i in range(100):
            w=bool(i%2)
            p.observe(CausalObservation(i,f'p{i}',int(w),int(not w),True,f'r{i}'))
            o=CausalObservation(i,f'o{i}',int(w),int(w),False,None)
            a.observe(o)
            if i==50:f.freeze()
            f.observe(o)
        self.assertLess(p.estimate()['effect'],-.90)
        self.assertGreater(a.estimate()['effect'],.90)
        self.assertEqual(f.estimate()['cost']['opportunities'],100)
        self.assertEqual(f.estimate()['cost']['updates'],50)
        with self.assertRaises(ValueError):
            a.observe(CausalObservation(102,'x',0,0,True,'xy'))
        with self.assertRaises(ValueError):
            p.observe(CausalObservation(102,'x',0,0,True,'r0'))

    def test_085_risk_authority_and_no_write_controls(self):
        d=lambda c,r,a=True,v=True,q=True:DecisionInput(('a','b'),c,r,a,v,q)
        self.assertEqual(graded_commit(d(.81,'low')),('commit','a'))
        self.assertEqual(graded_commit(d(.81,'high')),('clarify',None))
        self.assertEqual(graded_commit(d(.99,'high',a=False)),('clarify',None))
        self.assertEqual(graded_commit(d(.99,'high',v=False,q=False)),('defer',None))
        self.assertEqual(graded_commit(d(.70,'low',v=False,q=False)),('recommend','a'))
        self.assertEqual(graded_commit(d(.99,'low'),'defer'),('defer',None))

    def test_086_equal_update_slots_and_no_future_replay(self):
        arms=[ReplayLearner(mode,37) for mode in ('current','uniform','selective')]
        for i in range(24):
            row=PracticeObservation(i,f'a{i}',('cue','phase'+str(i//8)),i%2,f'b{i}')
            pred=[m.observe(row) for m in arms]
            self.assertEqual(pred[0]['secondary_observation_id'],f'a{i}')
            if i:
                for result in pred[1:]:
                    self.assertLess(int(result['secondary_observation_id'][1:]),i)
        self.assertEqual([m.cost['updates'] for m in arms],[48]*3)
        self.assertEqual([m.cost['features_touched'] for m in arms],[144]*3)
        self.assertEqual([m.cost['replayed_updates'] for m in arms],[0,23,23])
        self.assertGreater(arms[2].cost['retrieval_inspections'],arms[1].cost['retrieval_inspections'])
        with self.assertRaises(ValueError):arms[0].observe(row)

    def test_projection_checks_exact_witnessed_payload_no_future_or_gold(self):
        effect=Frame(id='e2',seq=1,kind='life082_effect',source='host',parents=(),
                      payload={'action':'k1','before':[0,0,0],'after':[1,0,0]})
        utter=Frame(id='e3',seq=2,kind='life082_witness',source='host',parents=('e2',),
                    payload=dict(effect.payload,phrase='blen',consequence='e2'))
        self.assertEqual(from_visible_frame(utter,[effect],trusted_observer='host').after,(1,0,0))
        with self.assertRaises(ValueError):from_visible_frame(utter,[],trusted_observer='host')
        utter.payload['answer_key']='k1'
        with self.assertRaises(ValueError):from_visible_frame(utter,[effect],trusted_observer='host')

if __name__=='__main__':unittest.main()
