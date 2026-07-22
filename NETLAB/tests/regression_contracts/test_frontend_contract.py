import re,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];FRONT=ROOT/'apps/mission_control/frontend'
class TestFrontend(unittest.TestCase):
 def test_modules(self):
  app=(FRONT/'modules/app.js').read_text();pages=re.findall(r"\['([a-z_]+)','",app);self.assertGreaterEqual(len(pages),17)
  for p in pages:self.assertTrue((FRONT/f'modules/{p}.js').exists(),p)
 def test_english_and_no_dead_inline(self):
  text='\n'.join(p.read_text(errors='ignore') for p in FRONT.rglob('*') if p.is_file());self.assertNotIn('Demo con User',text);self.assertNotIn('Ejecutar demo',text)
 def test_node_syntax(self):
  import shutil
  if not shutil.which('node'):self.skipTest('node unavailable')
  for p in (FRONT/'modules').glob('*.js'):
   r=subprocess.run(['node','--check',str(p)],capture_output=True,text=True);self.assertEqual(r.returncode,0,f'{p}: {r.stderr}')
if __name__=='__main__':unittest.main()
