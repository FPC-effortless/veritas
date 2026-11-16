"""Operator-private byte snapshots, NOT redistributable temporal releases.

This API never changes source rights. No export/network API is provided.
Filesystem ownership and operator trust remain outside this integrity boundary.
"""
from __future__ import annotations
import hashlib,json,os,shutil,tempfile,stat
from pathlib import Path
from .core import ForgeError,canonical
SCHEMA='forge.private-snapshot.v1'
LIMIT=64*1024*1024
SPEC_FIELDS={'snapshot_id','source_version','ai_use_allowed','redistribution_allowed','privacy_reviewed','visibility','purpose','excluded_claims'}

def _spec(s):
 if type(s)!=dict or set(s)!=SPEC_FIELDS:raise ForgeError('exact private snapshot specification required')
 if s['ai_use_allowed'] is not True or s['redistribution_allowed'] is not False or s['privacy_reviewed'] is not True or s['visibility']!='operator_private':raise ForgeError('private snapshot requires reviewed AI-use and explicit no-redistribution')
 for k in ('snapshot_id','source_version','purpose','excluded_claims'):
  if type(s[k])!=str or not s[k].strip() or len(s[k])>1024:raise ForgeError('bounded explicit private scope required')
 return s

def _no_symlinks(path):
 p=Path(path).absolute()
 if any(x.is_symlink() for x in [p,*p.parents]):raise ForgeError('symlink root/ancestor unsupported')
 return p

def _path(root,name):
 if type(name)!=str or not name or '\\' in name or '\x00' in name or Path(name).is_absolute() or any(p in ('','.','..') for p in name.split('/')):raise ForgeError('relative regular file required')
 root=_no_symlinks(root).resolve();p=root/name
 if any(x.is_symlink() for x in [p,*p.parents] if x!=root.parent):raise ForgeError('symlink unsupported')
 if not p.resolve().is_relative_to(root) or not p.is_file():raise ForgeError('file missing or escapes source')
 return p

def _read(p):
 with p.open('rb') as f:b=f.read(LIMIT+1)
 if len(b)>LIMIT:raise ForgeError('private file exceeds bound')
 return b

def freeze_private(root,files,spec,destination):
 """Immutable copy of explicit files, keeping caller's scientific split map.
 No inferred split independence, data adequacy, provenance authenticity or rights.
 """
 spec=_spec(spec)
 if type(files)!=list or not 1<=len(files)<=128 or len(set(files))!=len(files) or 'manifest.json' in files:raise ForgeError('unique bounded file roster required')
 dest=_no_symlinks(destination)
 if dest.exists() or dest.is_symlink():raise ForgeError('private snapshot destination already exists')
 dest.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.forge-private-',dir=dest.parent));os.chmod(stage,0o700)
 try:
  entries={};total=0
  for name in sorted(files):
   content=_read(_path(root,name));total+=len(content)
   if total>LIMIT:raise ForgeError('snapshot exceeds total bound')
   out=stage/name;out.parent.mkdir(parents=True,exist_ok=True)
   for parent in out.parents:
    if parent==stage.parent:break
    os.chmod(parent,0o700)
   out.write_bytes(content);os.chmod(out,0o600);entries[name]={'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
  manifest={'schema':SCHEMA,'specification':spec,'files':entries,'qualification':'BYTE_INTEGRITY_ONLY_NOT_SCIENTIFIC_QUALIFICATION','export_policy':'NO_REDISTRIBUTION'}
  m=stage/'manifest.json';m.write_bytes(canonical(manifest));os.chmod(m,0o600);os.replace(stage,dest)
 finally:
  if stage.exists():shutil.rmtree(stage)
 return manifest

def verify_private(root,manifest_sha256):
 root=_no_symlinks(root);raw=_read(_path(root,'manifest.json'))
 if type(manifest_sha256)!=str or hashlib.sha256(raw).hexdigest()!=manifest_sha256:raise ForgeError('private manifest pin mismatch')
 m=json.loads(raw)
 if set(m)!= {'schema','specification','files','qualification','export_policy'} or m['schema']!=SCHEMA or m['qualification']!='BYTE_INTEGRITY_ONLY_NOT_SCIENTIFIC_QUALIFICATION' or m['export_policy']!='NO_REDISTRIBUTION':raise ForgeError('invalid private snapshot schema/policy')
 _spec(m['specification']);files=m['files']
 if type(files)!=dict or not 1<=len(files)<=128 or 'manifest.json' in files:raise ForgeError('invalid private file roster')
 observed={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() or p.is_symlink()}
 if observed!=set(files)|{'manifest.json'}:raise ForgeError('extra/missing private snapshot files')
 if os.name=='posix':
  for p in [root,*root.rglob('*')]:
   mode=stat.S_IMODE(p.stat().st_mode)
   if mode!=(0o700 if p.is_dir() else 0o600):raise ForgeError('private snapshot permissions changed')
 total=0
 for name,entry in files.items():
  b=_read(_path(root,name));total+=len(b)
  if type(entry)!=dict or set(entry)!={'sha256','bytes'} or type(entry['bytes'])!=int or len(b)!=entry['bytes'] or hashlib.sha256(b).hexdigest()!=entry['sha256']:raise ForgeError('private snapshot content mismatch')
 if total>LIMIT:raise ForgeError('private snapshot exceeds bound')
 return {'valid':True,'schema':SCHEMA,'manifest_sha256':manifest_sha256,'files':len(files),'redistribution_allowed':False,'qualification':'BYTE_INTEGRITY_ONLY_NOT_SCIENTIFIC_QUALIFICATION'}
