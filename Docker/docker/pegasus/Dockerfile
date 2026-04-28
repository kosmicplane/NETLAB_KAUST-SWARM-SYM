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
ENV ROS_DISTRO=jazzy
ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp

RUN cat <<'EOS' >> /root/.bashrc

# ---------------------------
# ISAAC SIM + PEGASUS SETUP - JAZZY ONLY
# ---------------------------
export ISAACSIM_PATH=/isaac-sim
export ISAACSIM_PYTHON=${ISAACSIM_PATH}/python.sh
export ISAACSIM=${ISAACSIM_PATH}/isaac-sim.sh
export ROS_DISTRO=jazzy
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

isaac_run() {
    if [ ! -x "$ISAACSIM_PYTHON" ]; then
        echo "IsaacSim python.sh not found at: $ISAACSIM_PYTHON"
        return 1
    fi

    if [ ! -x "$ISAACSIM" ]; then
        echo "IsaacSim launcher not found at: $ISAACSIM"
        return 1
    fi

    local jazzy_bridge_lib="${ISAACSIM_PATH}/exts/isaacsim.ros2.bridge/jazzy/lib"
    if [ -d "$jazzy_bridge_lib" ]; then
        case ":${LD_LIBRARY_PATH:-}:" in
            *":${jazzy_bridge_lib}:"*) ;;
            *) export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+${LD_LIBRARY_PATH}:}${jazzy_bridge_lib}" ;;
        esac
    fi

    if [ $# -eq 0 ]; then
        echo "Launching Isaac Sim GUI with ROS_DISTRO=jazzy..."
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
EOS

WORKDIR /workspace

# Pegasus is optional and should be integrated after Isaac + ROS 2 Jazzy + Sionna are stable.
RUN git clone https://github.com/PegasusSimulator/PegasusSimulator.git && \
    cd /workspace/PegasusSimulator/extensions && \
    ${ISAACSIM_PYTHON} -m pip install --editable pegasus.simulator

CMD ["/bin/bash"]
