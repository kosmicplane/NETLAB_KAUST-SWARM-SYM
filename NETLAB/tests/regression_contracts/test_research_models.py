import math,unittest
from netlab.research_tools import *
class TestModels(unittest.TestCase):
 def test_fspl(self):self.assertAlmostEqual(fspl_db(1000,1e9),92.45,places=1)
 def test_noise(self):self.assertAlmostEqual(thermal_noise_dbm(1e6,0),-114,delta=.5)
 def test_capacity(self):self.assertGreater(shannon_capacity_mbps(20e6,10,.75),40)
 def test_a2g(self):
  r=probabilistic_a2g_path_loss(100,50,3.5e9,'urban');self.assertTrue(0<r.values['los_probability']<1);self.assertGreater(r.values['path_loss_db'],70)
 def test_ntn(self):self.assertGreater(ntn_slant_range_delay(600000,45).values['one_way_delay_s'],.001)
 def test_energy(self):self.assertGreater(rotary_wing_power_w(0),100)
 def test_offload(self):self.assertIn('offload_delay_s',edge_offloading(1e9,1e9,1e6,10,10e9).values)
 def test_fairness(self):self.assertEqual(jain_fairness([1,1,1]),1)
 def test_calibration(self):self.assertGreater(calibrate_log_distance([(10,70),(100,90)],3.5e9)['path_loss_exponent'],0)
 def test_radio_map(self):self.assertEqual(len(inverse_distance_radio_map([(0,0,-70)],[(0,0),(1,1)])),2)
if __name__=='__main__':unittest.main()
