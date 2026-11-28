import hashlib,json,math,sys,zipfile,platform
from pathlib import Path
import numpy as np
root=Path(sys.argv[1]); arms=('gpt','HH','A0','U','UA','AU'); seeds=(9001,9011,9029)
def check(ok,msg):
    if not ok: raise ValueError(msg)
def close(a,b): return abs(a-b)<1e-9
base={'model.py':'eaf5ae7973957bc68330fe754a8aa6cdb1199189413fee6995aa749f809e75c8','data009.py':'d0bf2a6e560487f254d4a14cb7887f30559c592f61010aa4e48cf1c5f091d27d','train009.py':'8037dd96af919c14e7b17a6f8a608c49fbe1d1cb48274b337cf08990434156d7','PROTOCOL.md':'7fe339597c3e2e6f95d1748dad8e4d64dc8ed0b9d7c5af8cf576dda1bc18211b'}
R={}; X={}; ids=[]
for line in (root/'provider.tsv').read_text().splitlines():
    name,i,size,sha=line.split();p=root/f'dept014-{name}.zip';b=p.read_bytes();check(len(b)==int(size) and hashlib.sha256(b).hexdigest()==sha,name+' outer')
    with zipfile.ZipFile(p) as z:
        member='comparison.json' if name=='terminal-paired-comparison' else 'validation.json';check(z.namelist()==[member] and z.testzip() is None,name+' inventory');r=json.loads(z.read(member))
    ids.append(int(i))
    if name=='terminal-paired-comparison': agg=r;continue
    a,s=r['arm'],r['seed'];k=(a,s);check(name==f'validation-{a}-{s}' and k not in R,'identity');c=r['checkpoint'];l=c['lock'];e=r['eval'];x=np.asarray(e['per_document'],dtype=np.float64)
    check(c['step']==8192 and c['targets']==100663296 and l['arm']==a and l['seed']==s and l['context']==768 and l['batch']==16 and l['steps']==8192,'budget')
    check(all(l['source'].get(k)==v for k,v in base.items()) and set(l['source'])==set(base)|({'gpt009.py'} if a=='gpt' else set()),'source')
    check(x.shape==(60,3) and np.isfinite(x).all() and (x>=0).all() and (x[:,1]<=x[:,2]).all() and np.equal(x[:,1:],np.floor(x[:,1:])).all(),'rows')
    n=x[:,2].sum();check(n==1145486==e['targets'] and close(x[:,0].sum()/n/math.log(2),e['bpb']) and close(x[:,1].sum()/n,e['accuracy']),'arithmetic')
    R[k]=r;X[k]=x
check(len(ids)==len(set(ids))==19 and set(R)=={(a,s) for a in arms for s in seeds},'matrix')
check(len({r['checkpoint']['sha256'] for r in R.values()})==18,'unique model')
check(len({r['data_manifest'] for r in R.values()})==len({r['checkpoint']['lock']['data'] for r in R.values()})==1,'data')
check(all(len({R[a,s]['checkpoint']['lock']['data_order'] for a in arms})==1 for s in seeds),'order')
check(len({R['gpt',s]['checkpoint']['lock']['source']['gpt009.py'] for s in seeds})==1,'gpt lock')
n=X['gpt',9001][:,2];check(all(np.array_equal(x[:,2],n) for x in X.values()),'document counts')
check(agg['fits']==18 and agg['predictions_per_fit']==100663296 and agg['total_predictions']==1811939328 and agg['targets_per_validation']==1145486 and agg['validation_manifest']==R['gpt',9001]['data_manifest'],'aggregate header')
idx=np.random.default_rng(9013909).integers(0,len(n),(10000,len(n)))
def pair(a,b,s):
 d=X[a,s][:,0]-X[b,s][:,0];q=d[idx].sum(1)/n[idx].sum(1)/math.log(2);return {'delta_bpb':float(d.sum()/n.sum()/math.log(2)),'document_bootstrap_95pct':np.quantile(q,[.025,.975]).tolist()}
for a,ar in zip(arms,agg['arms'],strict=True):
 check(a==ar['arm'],'arm ordering');scores=[R[a,s]['eval']['bpb'] for s in seeds];check(np.allclose(scores,ar['bpb_per_seed'],atol=1e-10,rtol=0) and close(float(np.mean(scores)),ar['mean_bpb']),'score')
 check(ar['parameters']==[R[a,s]['checkpoint']['parameters'] for s in seeds] and ar['training_seconds']==[R[a,s]['checkpoint']['training_seconds'] for s in seeds],'metadata')
 for b in ('gpt','A0'):
  for s in seeds:
   x=pair(a,b,s);y=ar['paired_vs_'+b][str(s)];check(close(x['delta_bpb'],y['delta_bpb']) and np.allclose(x['document_bootstrap_95pct'],y['document_bootstrap_95pct'],rtol=0,atol=1e-10),'bootstrap')
# Additional descriptive comparisons, not preregistered promotion tests.
extra={f'{a}-{b}':{str(s):pair(a,b,s) for s in seeds} for a,b in [('U','HH'),('UA','U'),('AU','UA')]}
summary={'environment':{'python':platform.python_version(),'numpy':np.__version__},'verified_archive_count':19,'verified_receipt_count':18,'verified_original_bootstrap_intervals':36,'means':{a:float(np.mean([R[a,s]['eval']['bpb'] for s in seeds])) for a in arms},'extra':extra,'limits':'saved receipt arithmetic only; no new model replay, no training, no checkpoint byte re-download; exact document identities and model bytes rely on existing owner audit; descriptive post-hoc contrasts, no promotion'}
print(json.dumps(summary,sort_keys=True,indent=2))
