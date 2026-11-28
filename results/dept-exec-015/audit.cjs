// DEPT-EXEC-015, no dependencies except Node standard library.
// Usage: node audit.cjs /path/to/pinned/model.py > result.json
const fs=require('node:fs'); const crypto=require('node:crypto');
const bytes=fs.readFileSync(process.argv[2]); const hash=crypto.createHash('sha1').update(Buffer.from('blob '+bytes.length+'\0')).update(bytes).digest('hex');
if(hash!=='31c3555521469425d884c700aed01b48c4fab50e') throw Error('source blob mismatch');
function audit(source){
  function require(ok,msg){if(!ok)throw Error(msg)}
  const anchors=[
    ["local-window","ids=torch.cat((last,x),1);a=emb(ids);h=self.trunk(torch.cat([a[:,:-4],a[:,1:-3],a[:,2:-2],a[:,3:-1],a[:,4:]],-1))"],
    ["local-ax","return a[:,4:]+z,ids[:,-4:].clone(),(ty,self.keyhead(k),self.valhead(v))"],
    ["same-ax","h,last,ax=self.local(x,self.core.emb,None if state is None else state[1])"],
    ["same-ax-each-H","if self.kinds[i]=='H':h,s=l(h,ax,self.payload_map[i],st,extra)"],
    ["hard-local-route","typ,key,val=ax;role=typ.softmax(-1);addr=key.softmax(-1);a=hard(addr);rp=hard(role);w=rp[...,1:2]+rp[...,3:4];rd=rp[...,2:3];gate=w*a"],
    ["hard-forward","return q+(p-p.detach())"],
    ["slot-count","slot,bg=s[:,:8],s[:,8:]"],
    ["local-slot-read","msg=(a.unsqueeze(-1)*seq).sum(-2)"],
    ["contextual-background","q=F.normalize(self.readaddr(u)[...,8:],dim=-1)"],
    ["role-mixture","msg=msg*(rd+w)+mb*rp[...,0:1]"],
    ["gqa-position","p=0 if state is None else state[0].shape[2]"],
    ["side-default","s=self.initial[None].expand(len(h),-1) if state is None else state[1]"]
  ];
  function check(s){return anchors.map(([id,a])=>{const n=s.split(a).length-1;require(n===1,"missing/duplicate "+id);return {id,line:s.slice(0,s.indexOf(a)).split("\n").length}})}
  const hits=check(source);
  const negatives=anchors.map(([id,a])=>{let rejected=false;try{check(source.replace(a,"# removed "+id))}catch(e){rejected=true}require(rejected,"negative accepted: "+id);return id});
  const lengths=[128,768,1024,8192], summaries=[], examples=[];
  for(const n of lengths){
    const groups=new Map();let oracle=0,rows=0;
    for(let f=0;f<16;f++){
      const suffix="Q:"+String(f).padStart(2,"0")+"?";
      const va=String.fromCharCode(65+f),vb=String.fromCharCode(97+f);
      const pair=["A","B"].map(subject=>{
        const prefix="A="+va+";B="+vb+";SELECT="+subject+";";
        const prompt=prefix+"x".repeat(n-prefix.length-suffix.length)+suffix;
        const label=subject==="A"?va:vb;
        require(prompt.length===n&&prompt.slice(-5)===suffix,"bad fixture length/suffix");
        const m=/^A=(.);B=(.);SELECT=([AB]);x+Q:\d{2}\?$/.exec(prompt);
        require(m!==null,"oracle parse fail");
        oracle+=Number(m[m[3]==="A"?1:2]===label);
        const k=prompt.slice(-5), counts=groups.get(k)||new Map();
        counts.set(label,(counts.get(label)||0)+1);groups.set(k,counts);rows++;
        return {label,subject,prompt};
      });
      require(pair[0].label!==pair[1].label&&pair[0].prompt.slice(-5)===pair[1].prompt.slice(-5),"bad contrast");
      require(pair[0].prompt.split("").reduce((z,c,i)=>z+Number(c!==pair[1].prompt[i]),0)===1,"not one-byte contrast");
      examples.push({length:n,family:f,common_suffix:suffix,prefix_A:pair[0].prompt.slice(0,17),prefix_B:pair[1].prompt.slice(0,17),labels:pair.map(x=>x.label),different_input_bytes:1});
    }
    let best=0;for(const g of groups.values())best+=Math.max(...g.values());
    require(best*2===rows&&oracle===rows,"bound or oracle mismatch");
    summaries.push({length:n,rows,families:groups.size,optimal_deterministic_suffix_only_correct:best,oracle_correct:oracle});
  }
  return {source_anchors:hits,negative_anchor_deletions_rejected:negatives,fixture_summary:summaries,fixtures:examples,classification:"Source-anchor checks and deterministic synthetic fixture arithmetic only; no model/checkpoint execution, training, protected data, or scientific acceptance."};
}
console.log(JSON.stringify(audit(bytes.toString('utf8')),null,2));
