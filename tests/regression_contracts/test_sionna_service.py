import importlib.util,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('linkserver',ROOT/'Docker/workspace/sionna/realtime_link_server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class TestLink(unittest.TestCase):
 def test_feasible_and_outage(self):
  q={'source_position_m':[0,0,0],'destination_position_m':[28,0,0],'parameters':{'operational_range_m':90,'hard_outage_distance_m':220,'min_snr_db':3,'min_capacity_mbps':1}}
  a=m.evaluate(q);self.assertTrue(a['feasible']);q['destination_position_m']=[200,0,0];b=m.evaluate(q);self.assertFalse(b['feasible']);self.assertEqual(b['gate_reason'],'OUT_OF_RANGE')
 def test_failed_endpoint(self):
  a=m.evaluate({'source_position_m':[0,0,0],'destination_position_m':[10,0,0],'parameters':{'source_failed':True}});self.assertEqual(a['gate_reason'],'SOURCE_FAILED')
if __name__=='__main__':unittest.main()
