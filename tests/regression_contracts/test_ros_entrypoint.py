import re,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class TestROS(unittest.TestCase):
 def test_shell_syntax(self):
  for p in [ROOT/'Docker/workspace/ros2/runtime_entrypoint.sh',ROOT/'Docker/workspace/ros2/netlab_ros_env.sh']:
   r=subprocess.run(['bash','-n',str(p)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
 def test_nounset_after_setup(self):
  t=(ROOT/'Docker/workspace/ros2/runtime_entrypoint.sh').read_text();self.assertIn('set -eo pipefail',t);self.assertNotIn('set -euo pipefail',t)
  helper=(ROOT/'Docker/workspace/ros2/netlab_ros_env.sh').read_text();self.assertIn('set +u',helper);self.assertIn('setup.bash',helper)
 def test_interfaces(self):
  base=ROOT/'Docker/workspace/ros2/src/netlab_interfaces';self.assertTrue((base/'package.xml').exists());self.assertGreaterEqual(len(list((base/'msg').glob('*.msg'))),6);self.assertGreaterEqual(len(list((base/'srv').glob('*.srv'))),3);self.assertGreaterEqual(len(list((base/'action').glob('*.action'))),2)
if __name__=='__main__':unittest.main()
