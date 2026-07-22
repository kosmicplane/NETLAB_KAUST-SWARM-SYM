FROM nvcr.io/nvidia/isaac-sim:5.1.0

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    ACCEPT_EULA=Y \
    PRIVACY_CONSENT=Y \
    OMNI_KIT_ALLOW_ROOT=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=all \
    ROS_DISTRO=jazzy \
    ROS_VERSION=2 \
    ROS_PYTHON_VERSION=3 \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    isaac_sim_package_path=/isaac-sim

COPY requirements/isaac-python.txt /tmp/isaac-python.txt

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
    git \
    git-lfs \
    curl \
    wget \
    nano \
    vim \
    tmux \
    htop \
    net-tools \
    iputils-ping \
    build-essential \
    cmake \
    python3-pip \
    python3-venv \
    ca-certificates \
    && locale-gen en_US en_US.UTF-8 \
    && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# Keep Isaac Sim clean: do not apt-install an external ROS 2 distro here.
# Isaac Sim 5.1 uses its internal ROS 2 Jazzy bridge libraries through entrypoint.sh.
RUN \
    python3 -m pip install --break-system-packages -r /tmp/isaac-python.txt

RUN mkdir -p /workspace/project \
    /workspace/isaac \
    /workspace/ros2_ws/src \
    /workspace/results \
    /workspace/scripts \
    /workspace/shared

COPY docker/isaacsim/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /workspace
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
