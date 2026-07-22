import tempfile,unittest
from netlab.acceptance import run_embedded_acceptance
class TestAcceptance(unittest.TestCase):
 def test_complete_sequence(self):
  with tempfile.TemporaryDirectory() as td:
   r=run_embedded_acceptance(td);self.assertTrue(r['ok']);self.assertGreaterEqual(r['stage_count'],10);self.assertTrue(all(x['ok'] for x in r['stages']))
if __name__=='__main__':unittest.main()
