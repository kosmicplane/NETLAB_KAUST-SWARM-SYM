import unittest
from netlab.readiness import aggregate_readiness
class TestReadiness(unittest.TestCase):
 def test_no_contradictory_ready(self):
  r=aggregate_readiness({'docker_ready':True,'compose_ready':True,'sionna_ready':True,'ros_container_ready':True,'ros_graph_ready':False,'packet_runtime_ready':False,'isaac_process_ready':True,'isaac_scene_ready':True,'isaac_scenario_acknowledged':False,'telemetry_ready':False,'synchronized':False});self.assertFalse(r['readiness']['ready']);self.assertNotEqual(r['phase'],'READY');self.assertEqual(r['telemetry_source'],'OFFLINE')
if __name__=='__main__':unittest.main()
