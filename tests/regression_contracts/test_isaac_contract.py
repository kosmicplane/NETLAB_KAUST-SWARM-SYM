import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class TestIsaac(unittest.TestCase):
 def test_extension_and_bridge(self):
  e=ROOT/'Docker/workspace/isaac/exts/netlab.snaas.bridge/config/extension.toml';b=ROOT/'Docker/workspace/isaac/scripts/netlab_snaas_bridge.py';self.assertTrue(e.exists());t=b.read_text();
  for term in ('scene_checksum','observed_positions','revision_id','scene_ready','0o664'):self.assertIn(term,t)
 def test_bridge_requires_observed_transform_application(self):
  text=(ROOT/'Docker/workspace/isaac/scripts/netlab_snaas_bridge.py').read_text()
  self.assertIn('/World/NETLAB_SNAAS_Relay_Chain_Demo',text)
  self.assertIn('applied_count == expected_count',text)
  self.assertIn('maximum_error_m <= tolerance_m',text)
  self.assertIn('"accepted": self.scene_ready',text)

if __name__=='__main__':unittest.main()

class TestIsaacAuthoritativeAck(unittest.TestCase):
    def test_default_scene_ack_is_observation_gated(self):
        text=(ROOT/'Docker/workspace/isaac/scripts/snaas_relay_scene.py').read_text()
        for term in (
            'def _observe_scene_application',
            'ComputeLocalToWorldTransform',
            'applied_count == expected_count',
            'maximum_error_m <= tolerance_m',
            '"accepted": accepted',
            '"observed_hashes": (dict(self.current_revision_hashes) if accepted else {})',
            'ISAAC_SCENE_APPLICATION_INCOMPLETE',
            'scene_checksum',
        ):
            self.assertIn(term,text)

    def test_default_compose_has_single_isaac_ack_writer(self):
        compose=(ROOT/'Docker/compose/docker-compose.yml').read_text()
        # The persistent scene application is the default control-plane bridge.
        self.assertIn('/workspace/isaac/scripts/snaas_autoload.py',compose)
        self.assertNotIn('--enable\n      - netlab.snaas.bridge',compose)
