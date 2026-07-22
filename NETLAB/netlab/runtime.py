from __future__ import annotations
import json, os, shutil, socket, subprocess, time, urllib.request, urllib.error
from pathlib import Path
from typing import Any, Iterable
from .io import atomic_write_json, read_json, ensure_shared_directory, repair_shared_tree, freshness
from .configuration import validate_file
from .readiness import aggregate_readiness

class RuntimeFailure(RuntimeError):
    def __init__(self,code:str,message:str,details:dict[str,Any]|None=None,recommendation:str=''):
        self.code=code;self.details=details or {};self.recommendation=recommendation
        super().__init__(message)
    def to_dict(self):return {'code':self.code,'message':str(self),'details':self.details,'recommendation':self.recommendation}

class NetlabRuntime:
    def __init__(self,root:str|Path):
        self.root=Path(root).resolve(); self.compose_dir=self.root/'Docker/compose'; self.compose_file=self.compose_dir/'docker-compose.yml'
        self.env_file=self.compose_dir/'.env'; self.results=self.root/'Docker/workspace/results'; self.shared=self.root/'Docker/workspace/shared'
        self.config_path=self.shared/'snaas_relay_config.json'; ensure_shared_directory(self.results); ensure_shared_directory(self.shared)
        self.state_path=self.results/'netlab_runtime_state.json'
    def run(self,args:Iterable[str],*,cwd:Path|None=None,timeout:float=120,check:bool=False,env:dict[str,str]|None=None)->dict[str,Any]:
        argv=[str(x) for x in args]; start=time.perf_counter()
        try:
            p=subprocess.run(argv,cwd=str(cwd or self.root),env=(os.environ|env if env else None),text=True,capture_output=True,timeout=timeout)
            result={'argv':argv,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'duration_s':time.perf_counter()-start,'timed_out':False,'ok':p.returncode==0}
        except subprocess.TimeoutExpired as exc:
            result={'argv':argv,'returncode':124,'stdout':exc.stdout or '','stderr':exc.stderr or '', 'duration_s':time.perf_counter()-start,'timed_out':True,'ok':False}
        if check and not result['ok']: raise RuntimeFailure('COMMAND_FAILED',f'Command failed: {" ".join(argv)}',result)
        return result
    def compose(self,*args:str,timeout:float=600,check:bool=False)->dict[str,Any]:
        return self.run(['docker','compose','--env-file','.env','-f','docker-compose.yml',*args],cwd=self.compose_dir,timeout=timeout,check=check)
    def write_state(self,phase:str,**extra)->dict[str,Any]:
        state=read_json(self.state_path,{}) or {}; state.update({'phase':phase,'updated_at':time.time(),**extra}); atomic_write_json(self.state_path,state); return state
    def generate_env(self)->dict[str,str]:
        values={}
        if self.env_file.exists():
            for line in self.env_file.read_text(errors='ignore').splitlines():
                if line and not line.lstrip().startswith('#') and '=' in line:
                    k,v=line.split('=',1);values[k]=v
        ip=values.get('ISAACSIM_HOST') or self._detect_ip()
        defaults={'ROS_DISTRO':'jazzy','ROS_DOMAIN_ID':'42','ISAACSIM_HOST':ip,'ISAACSIM_SIGNAL_PORT':'49100','ISAACSIM_STREAM_PORT':'47998',
          'ISAACSIM_TAG':'5.1.0','NETLAB_UID':str(os.getuid()),'NETLAB_GID':str(os.getgid()),'NETLAB_SHARED_FILE_MODE':'0664','NETLAB_SHARED_DIR_MODE':'2775'}
        for k,v in defaults.items(): values[k]=values.get(k) or v
        self.env_file.parent.mkdir(parents=True,exist_ok=True)
        self.env_file.write_text('\n'.join(f'{k}={v}' for k,v in sorted(values.items()))+'\n')
        return values
    def _detect_ip(self)->str:
        if shutil.which('tailscale'):
            r=self.run(['tailscale','ip','-4'],timeout=10)
            if r['ok'] and r['stdout'].strip(): return r['stdout'].splitlines()[0].strip()
        try:
            s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));ip=s.getsockname()[0];s.close();return ip
        except OSError:return '127.0.0.1'
    def repair(self)->dict[str,Any]:
        paths=[self.results,self.shared,self.root/'Docker/data/isaac/cache/main',self.root/'Docker/data/isaac/cache/computecache',self.root/'Docker/data/isaac/logs',self.root/'Docker/data/isaac/config',self.root/'Docker/data/isaac/local-data',self.root/'Docker/data/isaac/pkg']
        repaired=[]
        for p in paths: repaired.append({'path':str(p),'result':repair_shared_tree(p)})
        for stale in self.results.glob('*.pid'):
            try: stale.unlink()
            except OSError: pass
        self.generate_env(); return {'ok':True,'paths':repaired}
    def preflight(self)->dict[str,Any]:
        findings=[]; docker=self.run(['docker','info','--format','{{.ServerVersion}}'],timeout=20)
        if not docker['ok']:findings.append({'severity':'ERROR','code':'DOCKER_UNAVAILABLE','message':docker['stderr'].strip()})
        compose=self.compose('config','--quiet',timeout=30) if docker['ok'] else {'ok':False}
        if not compose.get('ok'):findings.append({'severity':'ERROR','code':'COMPOSE_INVALID','message':compose.get('stderr','')})
        validation=validate_file(self.config_path) if self.config_path.exists() else {'ok':False,'errors':[{'code':'MISSING_CONFIG','message':str(self.config_path)}]}
        if not validation['ok']:findings.append({'severity':'ERROR','code':'CONFIG_INVALID','message':f"{len(validation['errors'])} configuration error(s)",'errors':validation['errors']})
        gpu=self.run(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader'],timeout=20)
        if not gpu['ok']:findings.append({'severity':'WARNING','code':'GPU_HOST_CHECK_FAILED','message':gpu['stderr'].strip() or 'nvidia-smi unavailable'})
        disk=shutil.disk_usage(self.root).free
        if disk<15*1024**3: findings.append({'severity':'ERROR','code':'LOW_DISK','message':f'Only {disk/1024**3:.1f} GiB free'})
        return {'ok':not any(f['severity']=='ERROR' for f in findings),'findings':findings,'docker':docker,'compose':compose,'gpu':gpu,
                'configuration':validation,'disk_free_bytes':disk,'root':str(self.root),'timestamp':time.time()}
    def http_json(self,url:str,timeout:float=5)->dict[str,Any]:
        try:
            with urllib.request.urlopen(url,timeout=timeout) as r:return {'ok':200<=r.status<300,'status':r.status,'data':json.load(r)}
        except Exception as exc:return {'ok':False,'status':None,'data':None,'error':str(exc)}
    def service_container(self,service:str)->str:
        q=self.compose('ps','-q',service,timeout=20)
        cid=q['stdout'].strip() if q['ok'] else ''
        if not cid:return ''
        n=self.run(['docker','inspect','--format','{{.Name}}',cid],timeout=20)
        return n['stdout'].strip().lstrip('/') if n['ok'] else cid
    def container_state(self,service:str)->dict[str,Any]:
        name=self.service_container(service)
        if not name:return {'service':service,'exists':False,'running':False,'health':'missing'}
        r=self.run(['docker','inspect','--format','{{json .State}}',name],timeout=20)
        if not r['ok']:return {'service':service,'container':name,'exists':True,'running':False,'health':'unknown','error':r['stderr']}
        s=json.loads(r['stdout']);return {'service':service,'container':name,'exists':True,'running':bool(s.get('Running')),
          'status':s.get('Status'),'health':(s.get('Health') or {}).get('Status','none'),'exit_code':s.get('ExitCode'),'restart_count':self._restart_count(name)}
    def _restart_count(self,name:str)->int:
        r=self.run(['docker','inspect','--format','{{.RestartCount}}',name],timeout=20)
        try:return int(r['stdout'].strip())
        except:return -1
    def wait_until(self,label:str,predicate,timeout_s:float,poll_s:float=2.0):
        start=time.monotonic();last=None
        while time.monotonic()-start<timeout_s:
            ok,last=predicate()
            if ok:return last
            time.sleep(poll_s)
        raise RuntimeFailure(f'{label.upper()}_TIMEOUT',f'Timed out waiting for {label}',{'last_observed':last,'elapsed_s':time.monotonic()-start})
    def launch(self,*,build:bool=True,timeout_s:float=900)->dict[str,Any]:
        self.write_state('PREFLIGHT');self.repair();pre=self.preflight()
        if not pre['ok']:
            self.write_state('FAILED',last_error={'code':'PREFLIGHT_FAILED','details':pre});raise RuntimeFailure('PREFLIGHT_FAILED','NETLAB preflight found blocking errors',pre,'Run netlab doctor --repair')
        # Start Mission Control first so progress is visible.
        mc=self.run([str(self.root/'scripts/netlab_mission_control.sh'),'start'],timeout=30)
        self.write_state('BUILDING' if build else 'STARTING_SIONNA')
        args=['up','-d']
        if build:args.append('--build')
        args+=['sionna-engine']
        up=self.compose(*args,timeout=timeout_s)
        if not up['ok']:
            self.write_state('FAILED',last_error={'code':'COMPOSE_UP_FAILED','details':up});raise RuntimeFailure('COMPOSE_UP_FAILED','Failed to start Sionna',up)
        self.write_state('WAITING_FOR_SIONNA')
        self.wait_until('sionna',lambda:(self.http_json('http://127.0.0.1:8090/health').get('ok'),self.http_json('http://127.0.0.1:8090/health')),180)
        self.write_state('STARTING_ROS');up_ros=self.compose('up','-d',*(['--build'] if build else []),'ros2-core',timeout=timeout_s)
        if not up_ros['ok']:raise RuntimeFailure('ROS_COMPOSE_FAILED','Failed to start ROS 2',up_ros)
        self.write_state('WAITING_FOR_ROS_CONTAINER')
        self.wait_until('ros container',lambda:((s:=self.container_state('ros2-core')).get('running') and s.get('restart_count',0)==0,s),180)
        self.write_state('WAITING_FOR_PACKET_RUNTIME')
        self.wait_until('packet runtime',lambda:((f:=freshness(self.results/'snaas_packet_runtime_heartbeat.json',max_age_s=8)).get('fresh'),f),240)
        self.write_state('STARTING_ISAAC');up_i=self.compose('up','-d',*(['--build'] if build else []),'isaac',timeout=timeout_s)
        if not up_i['ok']:raise RuntimeFailure('ISAAC_COMPOSE_FAILED','Failed to start Isaac Sim',up_i)
        self.write_state('WAITING_FOR_ISAAC_PROCESS')
        self.wait_until('isaac process',lambda:((s:=self.container_state('isaac')).get('running'),s),180)
        self.write_state('WAITING_FOR_ISAAC_SCENE')
        self.wait_until('isaac scene',lambda:((f:=freshness(self.results/'snaas_isaac_heartbeat.json',max_age_s=20)).get('fresh') and bool((read_json(self.results/'snaas_isaac_heartbeat.json',{}) or {}).get('scene_ready',True)),f),420)
        self.write_state('SYNCHRONIZING')
        # Existing integration consumes the sync signal; bootstrap waits for matching revision when present.
        signal=read_json(self.results/'snaas_isaac_sync_signal.json',{}) or read_json(self.shared/'snaas_isaac_sync_signal.json',{}) or {}
        revision=signal.get('revision') or signal.get('revision_id')
        if revision:
            self.wait_until('isaac acknowledgement',lambda:((a:=read_json(self.results/'snaas_isaac_sync_ack.json',{}) or {}).get('revision')==revision or a.get('revision_id')==revision,a),180)
        self.write_state('SMOKE_TESTING')
        smoke=self.smoke_test(require_live=True)
        if not smoke['ok']:raise RuntimeFailure('SMOKE_TEST_FAILED','The live startup smoke test failed',smoke)
        state=self.status();self.write_state('READY',readiness=state.get('readiness'),telemetry_source=state.get('telemetry_source','LIVE'))
        return {'ok':True,'mission_control':mc,'state':read_json(self.state_path,{}),'status':self.status()}
    def status(self)->dict[str,Any]:
        services={s:self.container_state(s) for s in ('sionna-engine','ros2-core','isaac')}
        sionna=self.http_json('http://127.0.0.1:8090/health')
        ph=freshness(self.results/'snaas_packet_runtime_heartbeat.json',max_age_s=8);ih=freshness(self.results/'snaas_isaac_heartbeat.json',max_age_s=20)
        ack=read_json(self.results/'snaas_isaac_sync_ack.json',{}) or {}; signal=read_json(self.results/'snaas_isaac_sync_signal.json',{}) or read_json(self.shared/'snaas_isaac_sync_signal.json',{}) or {}
        sr=signal.get('revision') or signal.get('revision_id'); ar=ack.get('revision') or ack.get('revision_id')
        observed={'docker_ready':self.run(['docker','info'],timeout=10)['ok'],'gpu_ready':self.run(['nvidia-smi'],timeout=10)['ok'],
          'compose_ready':self.compose('config','--quiet',timeout=20)['ok'],'sionna_ready':bool(sionna.get('ok') and (sionna.get('data') or {}).get('ready',True)),
          'ros_container_ready':services['ros2-core'].get('running',False) and services['ros2-core'].get('restart_count',0)==0,
          'ros_graph_ready':ph.get('fresh',False),'packet_runtime_ready':ph.get('fresh',False),
          'isaac_process_ready':services['isaac'].get('running',False),'isaac_scene_ready':ih.get('fresh',False),
          'isaac_scenario_acknowledged':bool(ar and (not sr or ar==sr)),'telemetry_ready':ph.get('fresh',False),
          'telemetry_seen':ph.get('exists',False),'evidence_ready':os.access(self.results,os.W_OK),
          'synchronized':bool(ar and (not sr or ar==sr))}
        return aggregate_readiness(observed)|{'services':services,'sionna_api':sionna,'packet_heartbeat':ph,'isaac_heartbeat':ih,'sync_signal':signal,'sync_ack':ack,'runtime_state':read_json(self.state_path,{})}
    def smoke_test(self,*,require_live:bool=False)->dict[str,Any]:
        status=self.status();checks={'sionna':status['readiness']['sionna_ready'],'ros':status['readiness']['ros_graph_ready'],
          'packet':status['readiness']['packet_runtime_ready'],'isaac':status['readiness']['isaac_scene_ready'],
          'sync':status['readiness']['synchronized']}
        if not require_live: checks={k:v for k,v in checks.items() if k in {'sionna','ros','packet'}}
        return {'ok':all(checks.values()),'checks':checks,'status':status}
    def stop(self)->dict[str,Any]:
        self.write_state('STOPPING');down=self.compose('down','--remove-orphans',timeout=180)
        mc=self.run([str(self.root/'scripts/netlab_mission_control.sh'),'stop'],timeout=30)
        self.write_state('STOPPED');return {'ok':down['ok'],'compose':down,'mission_control':mc}
