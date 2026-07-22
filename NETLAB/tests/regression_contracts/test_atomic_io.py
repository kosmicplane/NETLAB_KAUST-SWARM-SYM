import json,os,tempfile,threading,time,unittest
from pathlib import Path
from netlab.io import atomic_write_json,read_json,repair_shared_tree
class TestAtomicIO(unittest.TestCase):
 def test_mode_and_atomic_readers(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'state.json';stop=False;errors=[]
   def reader():
    while not stop:
     if p.exists():
      try:json.loads(p.read_text())
      except Exception as e:errors.append(e)
   t=threading.Thread(target=reader);t.start()
   for i in range(200):atomic_write_json(p,{'sequence':i,'payload':'x'*200})
   stop=True;t.join();self.assertFalse(errors);self.assertEqual(os.stat(p).st_mode&0o777,0o664);self.assertEqual(read_json(p)['sequence'],199)
 def test_repair(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'x';p.mkdir();f=p/'a';f.write_text('x');os.chmod(f,0o600);r=repair_shared_tree(p);self.assertEqual(os.stat(f).st_mode&0o777,0o664);self.assertEqual(r['errors'],0)
if __name__=='__main__':unittest.main()
