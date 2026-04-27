FROM ros:humble-ros-base-jammy

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    ROS_DISTRO=humble \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    vim \
    nano \
    tmux \
    htop \
    python3-pip \
    python3-argcomplete \
    python3-colcon-common-extensions \
    iputils-ping \
    net-tools \
    build-essential \
    ros-dev-tools \
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

RUN rosdep init || true && rosdep update || true

RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install numpy scipy pandas matplotlib pyyaml

RUN echo 'source /opt/ros/humble/setup.bash' >> /root/.bashrc && \
    echo 'if [ -f /workspace/ros2/install/setup.bash ]; then source /workspace/ros2/install/setup.bash; fi' >> /root/.bashrc

WORKDIR /workspace/ros2
CMD ["/bin/bash"]
