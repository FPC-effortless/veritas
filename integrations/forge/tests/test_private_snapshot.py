import unittest,tempfile,hashlib,copy,importlib.util
from pathlib import Path
from forge_data.core import ForgeError
from forge_data.dataset import Dataset
p=Path(__file__).parents[1]/'src/forge_data/private_snapshot.py'
s=importlib.util.spec_from_file_location('forge_data.private_snapshot',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
SPEC=dict(snapshot_id='test',source_version='1',ai_use_allowed=True,redistribution_allowed=False,privacy_reviewed=True,visibility='operator_private',purpose='private synthetic fixture',excluded_claims='No scientific qualification')
class PrivateSnapshotTests(unittest.TestCase):
 def test_private_integrity_and_public_rejection(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/'data').write_text('private');out=r/'snapshot';m.freeze_private(r,['data'],SPEC,out);h=hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest();self.assertTrue(m.verify_private(out,h)['valid'])
   with self.assertRaises(ForgeError):Dataset(out,manifest_sha256=h)
   with self.assertRaises(ForgeError):m.freeze_private(r,['data'],SPEC,out)
   (out/'extra').write_text('x')
   with self.assertRaises(ForgeError):m.verify_private(out,h)
   (out/'extra').unlink();(out/'data').write_text('changed')
   with self.assertRaises(ForgeError):m.verify_private(out,h)
 def test_no_permission_weakening(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/'data').write_text('x')
   for key,val in [('redistribution_allowed',True),('visibility','public'),('ai_use_allowed',False),('privacy_reviewed',False)]:
    s=copy.deepcopy(SPEC);s[key]=val
    with self.assertRaises(ForgeError):m.freeze_private(r,['data'],s,r/'out')
   for files in [['../data'],['data','data'],['/tmp/data'],['manifest.json']]:
    with self.assertRaises(ForgeError):m.freeze_private(r,files,SPEC,r/'out')
   (r/'link').symlink_to(r/'data')
   with self.assertRaises(ForgeError):m.freeze_private(r,['link'],SPEC,r/'out')
if __name__=='__main__':unittest.main()
