from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
import time, uuid

class Phase(str,Enum):
    STOPPED='STOPPED'; PREFLIGHT='PREFLIGHT'; REPAIRING='REPAIRING'; BUILDING='BUILDING'
    STARTING_SIONNA='STARTING_SIONNA'; WAITING_FOR_SIONNA='WAITING_FOR_SIONNA'
    STARTING_ROS='STARTING_ROS'; WAITING_FOR_ROS_CONTAINER='WAITING_FOR_ROS_CONTAINER'
    WAITING_FOR_ROS_GRAPH='WAITING_FOR_ROS_GRAPH'; WAITING_FOR_PACKET_RUNTIME='WAITING_FOR_PACKET_RUNTIME'
    STARTING_ISAAC='STARTING_ISAAC'; WAITING_FOR_ISAAC_PROCESS='WAITING_FOR_ISAAC_PROCESS'
    WAITING_FOR_ISAAC_SCENE='WAITING_FOR_ISAAC_SCENE'; SYNCHRONIZING='SYNCHRONIZING'
    SMOKE_TESTING='SMOKE_TESTING'; READY='READY'; RUNNING='RUNNING'; DEGRADED='DEGRADED'
    FAILED='FAILED'; STOPPING='STOPPING'

class CommandStatus(str,Enum):
    CREATED='CREATED'; VALIDATING='VALIDATING'; REJECTED='REJECTED'; ACCEPTED='ACCEPTED'
    DISPATCHING='DISPATCHING'; WAITING_FOR_ACK='WAITING_FOR_ACK'; PARTIALLY_APPLIED='PARTIALLY_APPLIED'
    COMPLETED='COMPLETED'; FAILED='FAILED'; ROLLING_BACK='ROLLING_BACK'; ROLLED_BACK='ROLLED_BACK'; CANCELLED='CANCELLED'

class RevisionStatus(str,Enum):
    DRAFT_SAVED='DRAFT_SAVED'; VALIDATED='VALIDATED'; PENDING_RUNTIME_APPLY='PENDING_RUNTIME_APPLY'
    PENDING_ROS='PENDING_ROS'; PENDING_SIONNA='PENDING_SIONNA'; PENDING_ISAAC='PENDING_ISAAC'
    APPLIED_TO_ROS='APPLIED_TO_ROS'; APPLIED_TO_SIONNA='APPLIED_TO_SIONNA'; APPLIED_TO_ISAAC='APPLIED_TO_ISAAC'
    DRIFT_DETECTED='DRIFT_DETECTED'; RECONCILING='RECONCILING'; IN_SYNC='IN_SYNC'; COMMITTED='COMMITTED'
    DEGRADED='DEGRADED'; FAILED='FAILED'; ROLLED_BACK='ROLLED_BACK'

class TelemetrySource(str,Enum):
    LIVE='LIVE'; STALE='STALE'; REPLAY='REPLAY'; PREVIEW='PREVIEW'; OFFLINE='OFFLINE'; DEGRADED='DEGRADED'; UNAVAILABLE='UNAVAILABLE'

@dataclass
class ParticipantAck:
    participant:str; revision_id:str; accepted:bool; observed_hashes:dict[str,str]=field(default_factory=dict)
    timestamp:float=field(default_factory=time.time); message:str=''; details:dict[str,Any]=field(default_factory=dict)

@dataclass
class Command:
    command_type:str; payload:dict[str,Any]=field(default_factory=dict); initiator:str='operator'
    command_id:str=field(default_factory=lambda:str(uuid.uuid4())); idempotency_key:str=field(default_factory=lambda:str(uuid.uuid4()))
    requested_revision:str=''; status:CommandStatus=CommandStatus.CREATED; created_at:float=field(default_factory=time.time)
    updated_at:float=field(default_factory=time.time); acknowledgements:dict[str,dict[str,Any]]=field(default_factory=dict)
    error:dict[str,Any]|None=None; resulting_revision:str=''; evidence:list[str]=field(default_factory=list)
    def to_dict(self):
        d=asdict(self); d['status']=self.status.value; return d

@dataclass
class Revision:
    revision_id:str; parent_revision_id:str; command_id:str; idempotency_key:str; hashes:dict[str,str]
    candidate:dict[str,Any]; status:RevisionStatus=RevisionStatus.DRAFT_SAVED; initiator:str='operator'
    created_at:float=field(default_factory=time.time); updated_at:float=field(default_factory=time.time)
    acknowledgements:dict[str,dict[str,Any]]=field(default_factory=dict); error:dict[str,Any]|None=None
    retry_count:int=0; scene_checksum:str=''
    def to_dict(self):
        d=asdict(self); d['status']=self.status.value; return d

@dataclass
class ServiceState:
    name:str; process_alive:bool=False; container_running:bool=False; container_health:str='unknown'
    api_ready:bool=False; application_ready:bool=False; heartbeat_fresh:bool=False; last_seen:float|None=None
    revision_id:str=''; error:dict[str,Any]|None=None

@dataclass
class ReadinessState:
    docker_ready:bool=False; gpu_ready:bool=False; compose_ready:bool=False; sionna_ready:bool=False
    ros_container_ready:bool=False; ros_graph_ready:bool=False; packet_runtime_ready:bool=False
    isaac_process_ready:bool=False; isaac_scene_ready:bool=False; isaac_heartbeat_ready:bool=False; isaac_scenario_acknowledged:bool=False
    telemetry_ready:bool=False; evidence_ready:bool=False; synchronized:bool=False
    def ready(self)->bool:
        return all((self.docker_ready,self.compose_ready,self.sionna_ready,self.ros_container_ready,
                    self.ros_graph_ready,self.packet_runtime_ready,self.isaac_process_ready,
                    self.isaac_scene_ready,self.isaac_heartbeat_ready,self.isaac_scenario_acknowledged,self.telemetry_ready,self.synchronized))
    def to_dict(self): return asdict(self)|{'ready':self.ready(),'critical_ready':self.ready()}
    def as_dict(self): return self.to_dict()
