"""Input-token gradient attribution diagnostic at random initialization.

Gradient sensitivity is not a causal attribution of a trained model. This only
assesses whether learning signals reach history positions at initialization.
"""
from __future__ import annotations
import json
import math
import torch
import torch.nn.functional as F
from csa_training_pilot import StateGRU, PairDataset, build_vocab, tokens, ANSWERS

def scan(n=16,seed=918):
    torch.set_num_threads(2)
    torch.manual_seed(seed)
    v=build_vocab()
    ds=PairDataset("train",8,16,1004,v,185)
    model=StateGRU(len(v))
    outputs=[]
    for x,y,k in ds.items[:n]:
        x=torch.from_numpy(x[0]).reshape(1,-1)
        eb=model.embedding(x).detach().requires_grad_(True)
        _,h=model.encoder(eb)
        logits=model.head(h[-1])
        ce=F.cross_entropy(logits,torch.tensor([int(y[0])]))
        grad,=torch.autograd.grad(ce,eb)
        norms=grad[0].norm(dim=-1).numpy()
        xs=x[0].tolist()
        sep=xs.index(v["<sep>"])
        first_nonpad=next(i for i,t in enumerate(xs) if t!=v["<pad>"])
        history=norms[first_nonpad:sep]
        tail=norms[sep+1:]
        outputs.append({"kind":k,"pre_query_grad_mean":float(history.mean()),
                        "query_grad_mean":float(tail.mean()),
                        "history_over_query":float(history.mean()/max(tail.mean(),1e-30)),
                        "history_max_over_query":float(history.max()/max(tail.mean(),1e-30)),
                        "prefix_start_grad":float(history[:15].mean()),
                        "pre_query_grad_last15":float(history[-15:].mean()),
                        "last_history_over_query":float(history[-15:].mean()/max(tail.mean(),1e-30))})
    return {"scope":"random_initialization_one_gru_no_fit","rows":len(outputs),
            "mean_gradient_ratios":{key:sum(o[key] for o in outputs)/len(outputs) for key in
               ("history_over_query","history_max_over_query","last_history_over_query")},
            "samples":outputs}

if __name__=="__main__":
    d=scan()
    print(json.dumps(d["mean_gradient_ratios"],indent=2))
    open("gradient_probe.json","w").write(json.dumps(d,indent=2)+"\n")
