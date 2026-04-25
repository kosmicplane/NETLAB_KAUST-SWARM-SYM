FROM nvcr.io/nvidia/isaac-sim:5.1.0

SHELL ["/bin/bash", "-c"]
USER root

RUN mkdir -p /var/lib/apt/lists/partial && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        wget \
        curl \
        vim \
        nano \
        tmux \
        make \
        cmake \
        ninja-build \
        build-essential \
        gcc \
        g++ \
        python3-pip \
        iputils-ping \
        net-tools && \
    rm -rf /var/lib/apt/lists/*

ENV ISAACSIM_PATH=/isaac-sim
ENV ISAACSIM_PYTHON=/isaac-sim/python.sh
ENV ISAACSIM=/isaac-sim/isaac-sim.sh

RUN cat <<'EOF' >> /root/.bashrc

# ---------------------------
# ISAAC SIM SETUP
# ---------------------------
export ISAACSIM_PATH=/isaac-sim
export ISAACSIM_PYTHON=${ISAACSIM_PATH}/python.sh
export ISAACSIM=${ISAACSIM_PATH}/isaac-sim.sh

isaac_run() {
    if [ ! -x "$ISAACSIM_PYTHON" ]; then
        echo "IsaacSim python.sh not found at: $ISAACSIM_PYTHON"
        return 1
    fi

    if [ ! -x "$ISAACSIM" ]; then
        echo "IsaacSim launcher not found at: $ISAACSIM"
        return 1
    fi

    unset ROS_VERSION ROS_PYTHON_VERSION ROS_DISTRO AMENT_PREFIX_PATH COLCON_PREFIX_PATH PYTHONPATH CMAKE_PREFIX_PATH

    local ros_paths=("/opt/ros/humble" "/opt/ros/jazzy" "/opt/ros/iron" "/opt/ros/kilted")
    for ros_path in "${ros_paths[@]}"; do
        export LD_LIBRARY_PATH=$(echo "$LD_LIBRARY_PATH" | tr ':' '\n' | grep -v "^${ros_path}" | paste -sd':' -)
    done

    if [ -f /etc/os-release ]; then
        UBUNTU_VERSION=$(grep "^VERSION_ID=" /etc/os-release | cut -d'"' -f2)
    fi

    if [[ "$UBUNTU_VERSION" == "24.04" ]]; then
        export ROS_DISTRO=jazzy
        export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
        export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${ISAACSIM_PATH}/exts/isaacsim.ros2.bridge/jazzy/lib"
        echo "Detected Ubuntu 24.04 -> Using ROS_DISTRO=jazzy"
    else
        export ROS_DISTRO=humble
        export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
        export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${ISAACSIM_PATH}/exts/isaacsim.ros2.bridge/humble/lib"
        echo "Detected Ubuntu ${UBUNTU_VERSION:-unknown} -> Using ROS_DISTRO=humble"
    fi

    if [ $# -eq 0 ]; then
        echo "Launching Isaac Sim GUI..."
        "${ISAACSIM}"
    elif [[ "$1" == --* ]]; then
        echo "Launching Isaac Sim with options: $*"
        "${ISAACSIM}" "$@"
    elif [ -f "$1" ]; then
        local SCRIPT_PATH="$1"
        shift
        echo "Running Python script with Isaac Sim: $SCRIPT_PATH"
        "${ISAACSIM_PYTHON}" "$SCRIPT_PATH" "$@"
    else
        echo "Unknown argument or file not found: '$1'"
        echo "Usage:"
        echo "  isaac_run                 -> launch GUI"
        echo "  isaac_run my_script.py    -> run script with IsaacSim Python"
        echo "  isaac_run --headless ...  -> launch IsaacSim with CLI flags"
        return 1
    fi
}
EOF

WORKDIR /workspace

# Pegasus
RUN git clone https://github.com/PegasusSimulator/PegasusSimulator.git && \
    cd /workspace/PegasusSimulator/extensions && \
    ${ISAACSIM_PYTHON} -m pip install --editable pegasus.simulator

CMD ["/bin/bash"]