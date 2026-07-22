"""Data-Driven Connectivity Controller NETLAB reference plugin."""
from netlab.algorithm_baselines import data_driven_connectivity as _implementation

from netlab.algorithm_baselines import (
    common_initialize as initialize,
    common_validate as validate,
    common_reset as reset,
    common_on_state_update as on_state_update,
    common_on_state_update as on_topology_update,
    common_on_state_update as on_link_update,
    common_on_failure as on_failure,
    common_select_standby as select_standby,
    common_recompute_topology as recompute_topology,
    common_compute_metric as compute_metric,
    common_shutdown as shutdown,
)

def plan_positions(snapshot, parameters=None):
    result = step(snapshot, parameters or {})
    return result.get("desired_positions", {})

def plan_velocities(snapshot, parameters=None):
    return step(snapshot, parameters or {}).get("desired_velocities", {})

def plan_trajectories(snapshot, parameters=None):
    return step(snapshot, parameters or {}).get("desired_trajectories", {})

def step(snapshot, parameters=None):
    return _implementation(snapshot, parameters or {})
