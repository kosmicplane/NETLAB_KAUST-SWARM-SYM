ARG ISAACSIM_TAG=5.1.0
FROM nvcr.io/nvidia/isaac-sim:${ISAACSIM_TAG}

SHELL ["/bin/bash", "-c"]
USER root

ENV DEBIAN_FRONTEND=noninteractive \
    ACCEPT_EULA=Y \
    PRIVACY_CONSENT=Y \
    OMNI_KIT_ALLOW_ROOT=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=all \
    ROS_DISTRO=humble \
    ROS_VERSION=2 \
    ROS_PYTHON_VERSION=3 \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    ISAACSIM_PATH=/isaac-sim

RUN apt-get update && apt-get install -y --no-install-recommends \
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
    python3-colcon-common-extensions \
    software-properties-common \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu jammy main" \
    > /etc/apt/sources.list.d/ros2.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-humble-ros-base \
    ros-humble-rmw-fastrtps-cpp \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-vision-msgs \
    ros-humble-tf2-ros \
    ros-humble-tf-transformations \
    ros-humble-geometry-msgs \
    ros-humble-sensor-msgs \
    ros-humble-nav-msgs \
    ros-humble-std-msgs \
    ros-humble-rosgraph-msgs \
    ros-humble-rosbridge-suite \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install \
    numpy \
    scipy \
    pandas \
    matplotlib \
    pyyaml \
    rospkg \
    empy==3.3.4 \
    catkin_pkg \
    lark

WORKDIR /workspace

RUN mkdir -p \
    /workspace/isaac/scripts \
    /workspace/ros2/src \
    /workspace/results \
    /workspace/shared \
    /workspace/data

COPY docker/isaacsim/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN echo 'source /opt/ros/humble/setup.bash' >> /root/.bashrc && \
    echo 'if [ -f /workspace/ros2/install/setup.bash ]; then source /workspace/ros2/install/setup.bash; fi' >> /root/.bashrc && \
    echo 'alias isaac_headless="/isaac-sim/runheadless.sh -v"' >> /root/.bashrc && \
    echo 'alias isaac_python="/isaac-sim/python.sh"' >> /root/.bashrc

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
