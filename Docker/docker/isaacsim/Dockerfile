FROM nvcr.io/nvidia/isaac-sim:5.1.0

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive
ENV ACCEPT_EULA=Y
ENV PRIVACY_CONSENT=Y
ENV OMNI_KIT_ALLOW_ROOT=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=all

ENV ROS_DISTRO=jazzy
ENV ROS_VERSION=2
ENV ROS_PYTHON_VERSION=3
ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp

# Base system dependencies only.
# Do NOT install python3-colcon-common-extensions here.
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
    software-properties-common \
    gnupg \
    lsb-release \
    ca-certificates \
    && locale-gen en_US en_US.UTF-8 \
    && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# ROS 2 Jazzy repository for Ubuntu 24.04 Noble
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu noble main" \
    > /etc/apt/sources.list.d/ros2.list

# ROS 2 Jazzy packages, including colcon extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions \
    ros-jazzy-ros-base \
    ros-jazzy-rmw-fastrtps-cpp \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-vision-msgs \
    ros-jazzy-tf2-ros \
    ros-jazzy-tf-transformations \
    ros-jazzy-geometry-msgs \
    ros-jazzy-sensor-msgs \
    ros-jazzy-nav-msgs \
    ros-jazzy-std-msgs \
    ros-jazzy-rosgraph-msgs \
    ros-jazzy-rosbridge-suite \
    && rm -rf /var/lib/apt/lists/*

# Python packages for experiment scripts
RUN python3 -m pip install --upgrade pip --break-system-packages && \
    python3 -m pip install --break-system-packages \
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

RUN mkdir -p /workspace/project \
    /workspace/isaac \
    /workspace/ros2_ws/src \
    /workspace/pegasus \
    /workspace/results \
    /workspace/scripts

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc && \
    echo "if [ -f /workspace/ros2_ws/install/setup.bash ]; then source /workspace/ros2_ws/install/setup.bash; fi" >> /root/.bashrc

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]