"""Bounded exploratory CPU GRU pilot for WIL-TRAIN-002.

Not a scientific-qualified two-architecture comparison. No GPU or private data.
Training arms receive the same examples, labels, batches, and optimizer steps.
The additional pair objective uses labels already available to the CE control;
measured training time differs and training FLOPs are NOT matched.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import random
import re
import time
from pathlib import Path
from typing import NamedTuple
import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from csa_v02 import PLACES, PEOPLE, PROJECTS,generate,model_view,query,answer

VOCAB_RE=re.compile(r"[A-Za-z]+|\d+|[?.:]",re.ASCII)
ANSWERS=tuple(PLACES)+("UNKNOWN",)


def tokens(text):
    return ["<num>" if x.isdecimal() else x.lower() for x in VOCAB_RE.findall(text)]


def build_vocab():
    # Vocabulary supports all public grammar families; OOD grammar tokens are
    # included but remain untrained as intended diagnostic limitation.
    words={"<pad>","<sep>","<unk>","<num>"}
    for p in PROJECTS: words.add(p.lower())
    for p in PEOPLE: words.add(p.lower())
    for p in PLACES: words.add(p.lower())
    samples=[]
    for split in ("train","dev_ood_syntax"):
        samples.extend(generate(split,8,8,9001))
    for case in samples:
        for row in (case.a,case.b):
            words.update(tokens(row["history"]));words.update(tokens(row["query"]))
    vocab={word:i for i,word in enumerate(sorted(words))}
    return vocab


class PairDataset:
    def __init__(self,split,length,pairs,seed,vocab,max_len):
        self.items=[]
        self.vocab=vocab
        self.max_len=max_len
        self.cases=generate(split,length,pairs,seed)
        self.answers=ANSWERS
        for case in self.cases:
            rows=[case.a,case.b]
            if case.kind=="irrelevant_relocate":
                grammar="ood" if split=="dev_ood_syntax" else "base"
                for arm,events in zip((case.a,case.b),(case.events_a,case.events_b)):
                    rows.append({"history":arm["history"],"query":query(case.cross_project,grammar),
                                 "answer":answer(list(events),case.cross_project)})
            while len(rows)<4:
                rows.append(rows[0]) # not sampled by CE or paired gradient; masks used
            x=[self.encode(model_view(row)) for row in rows]
            y=[ANSWERS.index(row["answer"]) for row in rows]
            self.items.append((np.asarray(x,np.int64),np.asarray(y,np.int64),case.kind))

    def encode(self,view):
        t=tokens(view["history"])+["<sep>"]+tokens(view["query"])
        if len(t)>self.max_len: raise ValueError(f"sequence {len(t)}>{self.max_len}")
        return [self.vocab["<pad>"]]*(self.max_len-len(t)) + [self.vocab.get(w,self.vocab["<unk>"]) for w in t]


class StateGRU(nn.Module):
    """A learned recurrent state with explicit input erasure at inference boundary."""
    def __init__(self,vocab_size,d=40,h=64):
        super().__init__()
        self.embedding=nn.Embedding(vocab_size,d,padding_idx=0)
        self.encoder=nn.GRU(d,h,batch_first=True)
        self.head=nn.Sequential(nn.LayerNorm(h),nn.Linear(h,h),nn.GELU(),nn.Linear(h,len(ANSWERS)))
    def forward(self,tokens):
        _, s=self.encoder(self.embedding(tokens))
        return self.head(s[-1])



class FullContextTransformer(nn.Module):
    """Bidirectional answer-time Transformer upper control, NOT erasure-safe state."""
    def __init__(self,vocab_size,d=48,nhead=4,layers=2,max_len=185):
        super().__init__()
        self.embed=nn.Embedding(vocab_size,d,padding_idx=0)
        self.position=nn.Embedding(max_len,d)
        layer=nn.TransformerEncoderLayer(d_model=d,nhead=nhead,dim_feedforward=2*d,
                                           dropout=0.,batch_first=True,norm_first=False)
        self.encoder=nn.TransformerEncoder(layer,num_layers=layers,enable_nested_tensor=False)
        self.head=nn.Sequential(nn.LayerNorm(d),nn.Linear(d,d),nn.GELU(),nn.Linear(d,len(ANSWERS)))
    def forward(self,tokens):
        pos=torch.arange(tokens.shape[1],device=tokens.device)
        x=self.embed(tokens)+self.position(pos)[None,:,:]
        x=self.encoder(x,src_key_padding_mask=tokens.eq(0))
        return self.head(x[:,-1])

def loss_for_pairs(logits,ys,kinds,variant):
    # [B,4,K]; first 2 main query; other 2 for cross query on irrelevant pairs.
    B=logits.size(0)
    p=logits[:,:2,:]
    labels=ys[:,:2]
    is_cross=torch.tensor([k=="irrelevant_relocate" for k in kinds],dtype=torch.bool,device=logits.device)
    cross_logits=logits[is_cross,2:,:]
    cross_labels=ys[is_cross,2:]
    main_ce=F.cross_entropy(p.reshape(-1,len(ANSWERS)),labels.reshape(-1),reduction="none").reshape(-1,2)
    cross_ce=F.cross_entropy(cross_logits.reshape(-1,len(ANSWERS)),
                             cross_labels.reshape(-1),reduction="none") if is_cross.any() else torch.empty(0,device=logits.device)
    base=(main_ce.sum()+cross_ce.sum())/(main_ce.numel()+cross_ce.numel())
    if variant=="CE": return base,0.0
    if variant=="CE_REWEIGHT":
        # Alternative explanation: identical paired examples, but increase the
        # relative supervised pressure on answer-flipping changes. No pair KL.
        w_main=torch.where(is_cross,1.0,1.3).unsqueeze(-1)
        weighted=(main_ce*w_main).sum() + 1.3*cross_ce.sum()
        total=(w_main.sum()*2 + 1.3*cross_ce.numel())
        return weighted/total,0.0
    if variant!="PAIR": raise ValueError(variant)
    logp=F.log_softmax(logits,dim=-1)
    idx=torch.arange(B,device=logits.device)
    mainA,mainB=logp[:,0],logp[:,1]
    a,b=ys[:,0],ys[:,1]
    margin_a=mainA[idx,a]-mainB[idx,a]
    margin_b=mainB[idx,b]-mainA[idx,b]
    relevant=~is_cross
    pair_term=torch.zeros((),device=logits.device)
    if relevant.any():
        pair_term=pair_term+(F.softplus(.5-margin_a[relevant])+F.softplus(.5-margin_b[relevant])).mean()/2
    if is_cross.any():
        cA,cB=logp[is_cross,2],logp[is_cross,3]
        ca,cb=ys[is_cross,2],ys[is_cross,3]
        i=torch.arange(len(ca),device=logits.device)
        pair_term=pair_term+.5*(F.softplus(.5-(cA[i,ca]-cB[i,ca]))+F.softplus(.5-(cB[i,cb]-cA[i,cb]))).mean()
        qA,qB=logp[is_cross,0],logp[is_cross,1]
        m=.5*(qA.exp()+qB.exp())
        inv=.5*(F.kl_div(m.log(),qA.exp(),reduction="batchmean")+
                F.kl_div(m.log(),qB.exp(),reduction="batchmean"))
        pair_term=pair_term+inv
    return base+.2*pair_term, float(pair_term.detach())


def batchify(ds,inds,device):
    x=np.stack([ds.items[i][0] for i in inds])
    y=np.stack([ds.items[i][1] for i in inds])
    kinds=[ds.items[i][2] for i in inds]
    return torch.from_numpy(x).to(device),torch.from_numpy(y).to(device),kinds


@torch.inference_mode()
def evaluate(model,ds,batch=64):
    model.eval()
    n=correct=opposite=paired=0
    cc=cn=0
    losses=[]
    for i in range(0,len(ds.items),batch):
        x,y,kind=batchify(ds,range(i,min(i+batch,len(ds.items))),"cpu")
        logits=model(x.reshape(-1,x.shape[-1])).reshape(-1,4,len(ANSWERS))
        preds=logits.argmax(-1)
        matches=(preds[:,:2]==y[:,:2])
        correct+=int(matches.sum());n+=matches.numel()
        for z,k in enumerate(kind):
            if k!="irrelevant_relocate":
                opposite+=int(matches[z].all());paired+=1
            else:
                cc+=int((preds[z,2:]==y[z,2:]).sum());cn+=2
        losses.append((float(F.cross_entropy(logits[:,:2].reshape(-1,len(ANSWERS)),y[:,:2].reshape(-1),reduction="sum")),len(kind)*2))
    total=sum(z for z,sz in losses)
    return {"accuracy":correct/n,"n":n,"ce":total/n,
            "opposing_pair_both_correct":opposite/paired,"opposing_pairs":paired,
            "cross_accuracy":cc/max(1,cn),"cross_n":cn}


def train(seed=10,updates=200,batch=24,lr=0.003,variant="CE",train_pairs=1600,dev_pairs=200,max_len=185,architecture="gru"):
    torch.set_num_threads(2)
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    vocab=build_vocab()
    sources={"train":PairDataset("train",8,train_pairs,seed+8701,vocab,max_len),
             "dev_iid":PairDataset("dev_iid",8,dev_pairs,seed+9901,vocab,max_len),
             "dev_ood_comp":PairDataset("dev_ood_comp",8,dev_pairs,seed+10901,vocab,max_len),
             "dev_ood_syntax":PairDataset("dev_ood_syntax",8,dev_pairs,seed+11901,vocab,max_len)}
    model=StateGRU(len(vocab)) if architecture=="gru" else FullContextTransformer(len(vocab),max_len=max_len)
    opt=torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=.01)
    sampler=np.random.default_rng(seed+808)
    start=time.monotonic()
    result={"architecture":architecture,"state_erasure_interface":architecture=="gru",
            "variant":variant,"seed":seed,"updates":updates,"batch_pairs":batch,
            "train_pairs":train_pairs,"dev_pairs":dev_pairs,"max_len":max_len,
            "total_parameters":sum(p.numel() for p in model.parameters()),
            "embedding_vocab":len(vocab),"requested_device":"cpu",
            "same_examples_per_update_across_arms":True,"equal_flops":False,
            "privileged_oracle_inputs":False}
    losses=[]
    for step in range(updates):
        ix=sampler.integers(len(sources["train"].items),size=batch).tolist()
        x,y,k=batchify(sources["train"],ix,"cpu")
        pred=model(x.reshape(-1,x.shape[-1])).reshape(-1,4,len(ANSWERS))
        loss,penalty=loss_for_pairs(pred,y,k,variant)
        if not torch.isfinite(loss):raise RuntimeError(f"nonfinite step {step}")
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
        opt.step()
        if step==0 or (step+1)%50==0 or step==updates-1:
            losses.append({"step":step+1,"loss":float(loss.detach()),"pair_penalty":float(penalty),
                           "seconds":round(time.monotonic()-start,2)})
    result["training_seconds"]=round(time.monotonic()-start,3)
    result["loss_snapshots"]=losses
    result["eval"]={k:evaluate(model,v) for k,v in sources.items()}
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--seed",type=int,default=10)
    p.add_argument("--updates",type=int,default=200)
    p.add_argument("--batch",type=int,default=24)
    p.add_argument("--train-pairs",type=int,default=1600)
    p.add_argument("--dev-pairs",type=int,default=200)
    p.add_argument("--variant",choices=("CE","CE_REWEIGHT","PAIR"),default="CE")
    p.add_argument("--architecture",choices=("gru","transformer"),default="gru")
    x=p.parse_args()
    result=train(seed=x.seed,updates=x.updates,batch=x.batch,
                 train_pairs=x.train_pairs,dev_pairs=x.dev_pairs,variant=x.variant,architecture=x.architecture)
    x.output.parent.mkdir(parents=True,exist_ok=True)
    x.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__": main()
