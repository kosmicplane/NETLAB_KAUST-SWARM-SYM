import tempfile,unittest,zipfile
from pathlib import Path
from netlab.security import safe_extract_zip,UnsafeAssetError,validate_asset
class TestSecurity(unittest.TestCase):
 def test_zip_slip(self):
  with tempfile.TemporaryDirectory() as td:
   z=Path(td)/'x.zip'
   with zipfile.ZipFile(z,'w') as f:f.writestr('../escape','x')
   with self.assertRaises(UnsafeAssetError):safe_extract_zip(z,Path(td)/'out')
 def test_asset(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'a.usd';p.write_text('#usda 1.0');self.assertEqual(validate_asset(p)['size_bytes'],len('#usda 1.0'))
if __name__=='__main__':unittest.main()
