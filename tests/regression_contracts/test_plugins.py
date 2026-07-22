import importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class TestPlugins(unittest.TestCase):
 def test_manifests_and_hooks(self):
  manifests=list((ROOT/'plugins').rglob('manifest.json'));self.assertGreaterEqual(len(manifests),14)
  required={'initialize','validate','reset','plan_positions','on_state_update','on_failure','select_standby','recompute_topology','compute_metric','shutdown'}
  for m in manifests:
   d=json.loads(m.read_text());p=m.parent/d['entrypoint'];spec=importlib.util.spec_from_file_location('plugin_'+d['plugin_id'],p);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);self.assertFalse(required-set(dir(mod)),m)
if __name__=='__main__':unittest.main()
