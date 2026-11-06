"""Training-interface and loss checks; does not establish model capability."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import torch
    import numpy
except ImportError:
    raise unittest.SkipTest("Optional synthetic CPU pilot requires torch and numpy; stdlib Research Lab OS remains usable")
from csa_training_pilot import build_vocab, PairDataset, batchify, StateGRU,loss_for_pairs,ANSWERS

class ObjectiveChecks(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(8)
        self.vocab=build_vocab()
        self.dataset=PairDataset("train",8,8,810,self.vocab,185)
        self.X,self.Y,self.K=batchify(self.dataset,range(8),"cpu")
    def test_input_only_raw_history_query_and_no_teacher_codes(self):
        self.assertEqual(len(self.dataset.items),8)
        self.assertGreaterEqual(len(self.vocab),40)
        self.assertTrue(torch.all(self.X>=0))
        self.assertTrue(torch.all(self.Y>=0))
        self.assertTrue(torch.all(self.Y<len(ANSWERS)))
    def test_pair_objective_has_finite_gradient(self):
        model=StateGRU(len(self.vocab))
        logits=model(self.X.reshape(-1,self.X.shape[-1])).reshape(-1,4,len(ANSWERS))
        vals={}
        for variant in ("CE","CE_REWEIGHT","PAIR"):
            loss,penalty=loss_for_pairs(logits,self.Y,self.K,variant)
            self.assertTrue(torch.isfinite(loss))
            vals[variant]=float(loss.detach())
        self.assertNotAlmostEqual(vals["CE"],vals["PAIR"])
        l,_=loss_for_pairs(logits,self.Y,self.K,"PAIR")
        l.backward()
        self.assertTrue(all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None))
        self.assertTrue(any(p.grad.abs().sum()>0 for p in model.parameters() if p.grad is not None))
    def test_equal_ce_when_only_ce_selected(self):
        logits=torch.randn(8,4,len(ANSWERS),requires_grad=True)
        l,penalty=loss_for_pairs(logits,self.Y,self.K,"CE")
        self.assertEqual(penalty,0)
        self.assertTrue(float(l.detach())>0)
        self.assertEqual(sum(k=="irrelevant_relocate" for k in self.K),2)

if __name__=="__main__":unittest.main()
