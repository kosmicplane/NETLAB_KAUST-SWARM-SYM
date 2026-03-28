FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
    curl \
    gnupg2 \
    lsb-release \
    ca-certificates \
    software-properties-common \
    build-essential \
    git \
    wget \
    vim \
    nano \
    tmux \
    python3-pip \
    python3-argcomplete \
    iputils-ping \
    net-tools \
    && locale-gen en_US en_US.UTF-8 \
    && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

RUN add-apt-repository universe && \
    apt-get update && apt-get install -y curl && \
    export ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F "tag_name" | awk -F'"' '{print $4}') && \
    curl -L -o /tmp/ros2-apt-source.deb \
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.noble_all.deb" && \
    dpkg -i /tmp/ros2-apt-source.deb && \
    apt-get update && \
    apt-get install -y \
    ros-kilted-ros-base \
    ros-dev-tools \
    && rm -rf /var/lib/apt/lists/*

RUN rosdep init || true && rosdep update

RUN echo "source /opt/ros/kilted/setup.bash" >> /root/.bashrc

WORKDIR /workspace

CMD ["/bin/bash"]