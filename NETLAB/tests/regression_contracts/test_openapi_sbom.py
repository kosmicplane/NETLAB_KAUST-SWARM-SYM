import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class TestRelease(unittest.TestCase):
 def test_openapi(self):self.assertIn('openapi: 3.0.3',(ROOT/'openapi/netlab-openapi.yaml').read_text())
 def test_sbom(self):self.assertEqual(json.loads((ROOT/'security/sbom.cdx.json').read_text())['bomFormat'],'CycloneDX')
 def test_version(self):self.assertEqual((ROOT/'VERSION').read_text().strip(),'9.0.0')
if __name__=='__main__':unittest.main()
