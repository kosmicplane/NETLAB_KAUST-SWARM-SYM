from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .hashing import component_hashes

class ConfigurationValidationError(ValueError):
    def __init__(self,errors:list[dict[str,str]]):
        self.errors=errors; super().__init__(f'Experiment configuration contains {len(errors)} validation error(s)')

def load_configuration(path:str|Path)->dict[str,Any]:
    with Path(path).open('r',encoding='utf-8') as f: data=json.load(f)
    if not isinstance(data,dict): raise ConfigurationValidationError([{'path':'$','code':'TYPE','message':'root must be an object'}])
    return data

def validate_configuration(c:dict[str,Any])->dict[str,Any]:
    errors=[];warnings=[]
    def err(path,code,msg):errors.append({'path':path,'code':code,'message':msg})
    for key in ('experiment','swarm','topology','communication','antennas','world','traffic','failures'):
        if key not in c: err(f'$.{key}','MISSING_SECTION',f'missing required section {key}')
    swarm=c.get('swarm',{}); drones=swarm.get('drones',[])
    if not isinstance(drones,list) or not drones: err('$.swarm.drones','EMPTY_FLEET','at least one UAV is required')
    ids=[]
    for i,d in enumerate(drones if isinstance(drones,list) else []):
        did=d.get('id') if isinstance(d,dict) else None
        if not did: err(f'$.swarm.drones[{i}].id','MISSING_ID','UAV ID is required')
        elif did in ids: err(f'$.swarm.drones[{i}].id','DUPLICATE_ID',f'duplicate UAV ID {did}')
        else: ids.append(did)
        pos=d.get('position') if isinstance(d,dict) else None
        if not isinstance(pos,list) or len(pos)!=3 or not all(isinstance(x,(int,float)) for x in pos):
            err(f'$.swarm.drones[{i}].position','INVALID_POSITION','position must be [x,y,z] in metres')
    defs=c.get('antennas',{}).get('definitions',[]); ant_ids={d.get('id') for d in defs if isinstance(d,dict) and d.get('id')}
    assignments=c.get('antennas',{}).get('assignments',{})
    for entity,aid in assignments.items() if isinstance(assignments,dict) else []:
        if aid not in ant_ids: err(f'$.antennas.assignments.{entity}','UNKNOWN_ANTENNA',f'antenna {aid} is not registered')
    for i,d in enumerate(drones if isinstance(drones,list) else []):
        aid=d.get('antenna_id') if isinstance(d,dict) else None
        if aid and aid not in ant_ids: err(f'$.swarm.drones[{i}].antenna_id','UNKNOWN_ANTENNA',f'antenna {aid} is not registered')
    comm=c.get('communication',{})
    for key in ('bandwidth_hz','carrier_frequency_hz','operational_range_m','hard_outage_distance_m'):
        if key in comm and (not isinstance(comm[key],(int,float)) or comm[key]<=0): err(f'$.communication.{key}','INVALID_VALUE','must be positive')
    if comm.get('hard_outage_distance_m',1)<comm.get('operational_range_m',0):
        err('$.communication.hard_outage_distance_m','INVALID_THRESHOLD_ORDER','hard outage distance must be >= operational range')
    topo=c.get('topology',{}); mode=topo.get('mode','chain')
    if mode not in {'chain','parallel','forest','manual','mesh','star','cluster','hierarchical'}: err('$.topology.mode','UNSUPPORTED_MODE',f'unsupported topology mode {mode}')
    branches=topo.get('branches',[])
    if mode in {'chain','parallel','forest'} and not branches: err('$.topology.branches','EMPTY_BRANCHES','at least one branch is required')
    for bi,b in enumerate(branches if isinstance(branches,list) else []):
        if not isinstance(b,list) or not b: err(f'$.topology.branches[{bi}]','INVALID_BRANCH','branch must be a non-empty list')
    scale=swarm.get('visual_asset_scale',c.get('visualization',{}).get('visual_asset_scale',0.2))
    if not isinstance(scale,(int,float)) or scale<=0: err('$.swarm.visual_asset_scale','INVALID_SCALE','visual scale must be positive')
    elif scale>2: warnings.append({'path':'$.swarm.visual_asset_scale','code':'LARGE_VISUAL_SCALE','message':'visual scale is unusually large'})
    return {'ok':not errors,'errors':errors,'warnings':warnings,'hashes':component_hashes(c),'config':c}

def validate_file(path:str|Path)->dict[str,Any]: return validate_configuration(load_configuration(path))
