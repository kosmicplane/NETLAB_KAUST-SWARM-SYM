import importlib.util,json,socket,subprocess,sys,tempfile,time,unittest,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class TestAPI(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  s=socket.socket();s.bind(('127.0.0.1',0));cls.port=s.getsockname()[1];s.close();cls.p=subprocess.Popen([sys.executable,str(ROOT/'apps/mission_control/backend/server.py'),'--host','127.0.0.1','--port',str(cls.port)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  for _ in range(50):
   try:urllib.request.urlopen(f'http://127.0.0.1:{cls.port}/api/health',timeout=.2);break
   except Exception:time.sleep(.1)
 @classmethod
 def tearDownClass(cls):
  cls.p.terminate()
  try: cls.p.communicate(timeout=10)
  except subprocess.TimeoutExpired:
   cls.p.kill(); cls.p.communicate(timeout=5)
 def get(self,p):return json.load(urllib.request.urlopen(f'http://127.0.0.1:{self.port}{p}',timeout=3))
 def post(self,p,obj):
  req=urllib.request.Request(f'http://127.0.0.1:{self.port}{p}',data=json.dumps(obj).encode(),headers={'Content-Type':'application/json'},method='POST');return json.load(urllib.request.urlopen(req,timeout=3))
 def test_health_config_research(self):
  self.assertTrue(self.get('/api/health')['ok']);self.assertTrue(self.get('/api/config')['validation']['ok']);self.assertTrue(self.post('/api/research/ntn',{'altitude_m':600000,'elevation_deg':45})['ok']);self.assertIn('source',self.get('/api/telemetry'))
 def test_static(self):self.assertIn('NETLAB',(urllib.request.urlopen(f'http://127.0.0.1:{self.port}/').read().decode()))
if __name__=='__main__':unittest.main()
