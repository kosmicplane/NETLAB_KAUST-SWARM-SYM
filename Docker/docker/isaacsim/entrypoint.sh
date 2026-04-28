#!/usr/bin/env bash
set -e

export ACCEPT_EULA=${ACCEPT_EULA:-Y}
export PRIVACY_CONSENT=${PRIVACY_CONSENT:-Y}
export OMNI_KIT_ALLOW_ROOT=${OMNI_KIT_ALLOW_ROOT:-1}
export NVIDIA_VISIBLE_DEVICES=${NVIDIA_VISIBLE_DEVICES:-all}
export NVIDIA_DRIVER_CAPABILITIES=${NVIDIA_DRIVER_CAPABILITIES:-all}

export isaac_sim_package_path=${isaac_sim_package_path:-/isaac-sim}
export ROS_DISTRO=jazzy
export ROS_VERSION=2
export ROS_PYTHON_VERSION=3
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}

JAZZY_BRIDGE_LIB="${isaac_sim_package_path}/exts/isaacsim.ros2.bridge/jazzy/lib"
if [ -d "$JAZZY_BRIDGE_LIB" ]; then
    case ":${LD_LIBRARY_PATH:-}:" in
        *":${JAZZY_BRIDGE_LIB}:"*) ;;
        *) export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+${LD_LIBRARY_PATH}:}${JAZZY_BRIDGE_LIB}" ;;
    esac
fi

# Do not source /opt/ros/* inside Isaac Sim.
# Only source a custom Isaac-compatible workspace if it was built for Isaac Sim Python 3.11.
if [ "${SOURCE_ISAAC_ROS2_WS:-0}" = "1" ] && [ -f /workspace/ros2_ws/install/setup.bash ]; then
    source /workspace/ros2_ws/install/setup.bash
fi

exec "$@"
