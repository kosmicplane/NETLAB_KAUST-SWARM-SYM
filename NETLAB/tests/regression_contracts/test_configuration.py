import json,unittest
from pathlib import Path
from netlab.configuration import validate_file,validate_configuration
ROOT=Path(__file__).resolve().parents[2]
class TestConfiguration(unittest.TestCase):
 def test_default(self):
  r=validate_file(ROOT/'Docker/workspace/shared/snaas_relay_config.json');self.assertTrue(r['ok'],r['errors']);self.assertEqual(r['config']['swarm']['visual_asset_scale'],.2)
 def test_all_scenarios(self):
  files=list((ROOT/'scenarios').rglob('*.json'));self.assertGreaterEqual(len(files),30)
  bad={str(p):validate_file(p)['errors'] for p in files if not validate_file(p)['ok']};self.assertFalse(bad,bad)
 def test_unknown_antenna(self):
  c=json.loads((ROOT/'Docker/workspace/shared/snaas_relay_config.json').read_text());c['swarm']['drones'][0]['antenna_id']='missing';r=validate_configuration(c);self.assertFalse(r['ok']);self.assertIn('UNKNOWN_ANTENNA',{e['code'] for e in r['errors']})
if __name__=='__main__':unittest.main()
