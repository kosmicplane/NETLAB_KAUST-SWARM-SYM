from __future__ import annotations
from pathlib import Path
from typing import Any
import time
from .contracts import ReadinessState, Phase, TelemetrySource
from .io import freshness, read_json

def aggregate_readiness(observed:dict[str,Any])->dict[str,Any]:
    r=ReadinessState(
      docker_ready=bool(observed.get('docker_ready')),gpu_ready=bool(observed.get('gpu_ready')),
      compose_ready=bool(observed.get('compose_ready')),sionna_ready=bool(observed.get('sionna_ready')),
      ros_container_ready=bool(observed.get('ros_container_ready')),ros_graph_ready=bool(observed.get('ros_graph_ready')),
      packet_runtime_ready=bool(observed.get('packet_runtime_ready')),isaac_process_ready=bool(observed.get('isaac_process_ready')),
      isaac_scene_ready=bool(observed.get('isaac_scene_ready')),
      isaac_scenario_acknowledged=bool(observed.get('isaac_scenario_acknowledged')),
      telemetry_ready=bool(observed.get('telemetry_ready')),evidence_ready=bool(observed.get('evidence_ready',True)),
      synchronized=bool(observed.get('synchronized')))
    phase=Phase.READY if r.ready() else Phase.DEGRADED if any(r.to_dict().values()) else Phase.STOPPED
    source=TelemetrySource.LIVE if r.telemetry_ready and r.packet_runtime_ready else TelemetrySource.STALE if observed.get('telemetry_seen') else TelemetrySource.OFFLINE
    return {'phase':phase.value,'readiness':r.to_dict(),'telemetry_source':source.value,'generated_at':time.time()}

def observe_files(results_dir:str|Path,timeout_s:float=10.0)->dict[str,Any]:
    root=Path(results_dir)
    files={'sionna':'snaas_sionna_heartbeat.json','packet':'snaas_packet_runtime_heartbeat.json',
           'isaac':'snaas_isaac_heartbeat.json','isaac_ack':'snaas_isaac_sync_ack.json'}
    out={k:freshness(root/v,max_age_s=timeout_s) for k,v in files.items()}
    out['payloads']={k:read_json(root/v,{}) for k,v in files.items()}
    return out
