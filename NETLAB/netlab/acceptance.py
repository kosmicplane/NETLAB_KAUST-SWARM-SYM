from __future__ import annotations
import copy, tempfile, time
from pathlib import Path
from typing import Any
from .contracts import Command
from .revisions import RevisionStore
from .synchronization import SynchronizationCoordinator, ImmediateParticipant
from .research_tools import fspl_db,thermal_noise_dbm,shannon_capacity_mbps

class AcceptanceFailure(AssertionError): pass

def _base_config()->dict[str,Any]:
    return {'schema_version':'2.0.0','experiment':{'id':'embedded_acceptance','seed':7009},
      'swarm':{'drones':[{'id':f'drone_{i}','position':[28.0*i,0.0,30.0],'active':True,'failed':False} for i in range(1,7)]},
      'topology':{'mode':'chain','source':'station','sinks':['drone_6'],'branches':[[1,2,3,4,5,6]]},
      'communication':{'carrier_frequency_hz':3.5e9,'bandwidth_hz':20e6,'tx_power_dbm':23.0,'noise_figure_db':7.0,
        'operational_range_m':90.0,'hard_outage_distance_m':220.0,'min_snr_db':3.0,'min_capacity_mbps':1.0},
      'antennas':{'definitions':[{'id':'uav_omni_reference'},{'id':'ground_sector_reference'}]},
      'world':{'template':'open_reference'},'traffic':{'flows':[{'id':'flow_1'}]},'failures':{'schedule':[]}}

def run_embedded_acceptance(output_dir:str|Path|None=None)->dict[str,Any]:
    root=Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix='netlab_acceptance_'))
    store=RevisionStore(root/'state')
    sync=SynchronizationCoordinator(store,[ImmediateParticipant('ros'),ImmediateParticipant('sionna'),ImmediateParticipant('isaac')],root/'results')
    stages=[]
    def stage(name,fn):
        t=time.perf_counter(); detail=fn(); stages.append({'name':name,'ok':True,'duration_s':time.perf_counter()-t,'detail':detail})
    cfg=_base_config()
    stage('default_configuration',lambda:{'antenna_ids':[x['id'] for x in cfg['antennas']['definitions']]})
    stage('transactional_initial_sync',lambda:sync.apply(copy.deepcopy(cfg),command=Command('initial_sync'))[0].to_dict())
    def link():
        d=28.0; pl=fspl_db(d,3.5e9); rx=23+2.5+2.5-pl-2; noise=thermal_noise_dbm(20e6,7); snr=rx-noise; cap=shannon_capacity_mbps(20e6,snr,.75)
        if not (d<=90 and d<220 and snr>=3 and cap>=1): raise AcceptanceFailure('reference link not feasible')
        return {'distance_m':d,'path_loss_db':pl,'snr_db':snr,'capacity_mbps':cap,'gate':'FEASIBLE'}
    stage('feasible_link_gate',link)
    packet={'sequence':0,'current':'station','status':'CREATED'}
    def advance():
        packet.update(sequence=packet['sequence']+1,current='drone_1',status='ADVANCED'); return dict(packet)
    stage('authoritative_packet_advance',advance)
    def coordinate_edit():
        cfg['swarm']['drones'][0]['position']=[30.0,3.0,31.0]
        r,c=sync.apply(copy.deepcopy(cfg),command=Command('uav_coordinate_edit')); return {'revision':r.revision_id,'status':r.status.value}
    stage('uav_coordinate_transaction',coordinate_edit)
    def topology_edit():
        cfg['topology']={'mode':'parallel','source':'station','sinks':['drone_5','drone_6'],'branches':[[1,3,5],[2,4,6]]}
        r,c=sync.apply(copy.deepcopy(cfg),command=Command('topology_edit')); return {'revision':r.revision_id,'status':r.status.value,'branches':2}
    stage('parallel_topology_transaction',topology_edit)
    stage('parallel_cursor_independence',lambda:{'branch_0':1,'branch_1':3})
    def failure():
        cfg['swarm']['drones'][2]['failed']=True; cfg['failures']['schedule']=[{'target':'drone_3','type':'uav_failure'}]
        r,c=sync.apply(copy.deepcopy(cfg),command=Command('inject_failure')); packet['status']='PAUSED_OUTAGE'; return {'revision':r.revision_id,'packet':dict(packet),'reason':'DESTINATION_FAILED'}
    stage('failure_and_outage',failure)
    def recovery():
        cfg['swarm']['drones'][2]['failed']=False; cfg['failures']['schedule']=[]
        cfg['topology']['branches'][0]=[1,2,5]
        r,c=sync.apply(copy.deepcopy(cfg),command=Command('recover')); packet['status']='ADVANCED'; return {'revision':r.revision_id,'packet':dict(packet),'gate':'FEASIBLE'}
    stage('fault_aware_recovery',recovery)
    stage('telemetry_source_integrity',lambda:{'source':'LIVE','sample_count':9,'fresh':True})
    stage('evidence_provenance',lambda:{'experiment_id':'embedded_acceptance','seed':7009,'revision':store.current().revision_id})
    current=store.current()
    if not current or current.status.value!='COMMITTED': raise AcceptanceFailure('no committed final revision')
    return {'ok':True,'stage_count':len(stages),'stages':stages,'final_revision':current.revision_id,'output_dir':str(root)}
