FROM ros:jazzy-perception-noble

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
    git \
    curl \
    wget \
    vim \
    nano \
    tmux \
    python3-pip \
    python3-argcomplete \
    python3-colcon-common-extensions \
    iputils-ping \
    net-tools \
    build-essential \
    ros-dev-tools \
    && locale-gen en_US en_US.UTF-8 \
    && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

RUN rosdep init || true && rosdep update

WORKDIR /opt/uxrce_ws/src
RUN git clone -b v2.4.3 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git

WORKDIR /opt/uxrce_ws
RUN bash -lc "source /opt/ros/jazzy/setup.bash && colcon build"

RUN echo 'source /opt/ros/jazzy/setup.bash' >> /root/.bashrc && \
    echo 'source /opt/uxrce_ws/install/local_setup.bash' >> /root/.bashrc

WORKDIR /workspace
ENTRYPOINT ["/bin/bash", "-lc"]
CMD ["source /opt/ros/jazzy/setup.bash && source /opt/uxrce_ws/install/local_setup.bash && exec MicroXRCEAgent udp4 -p 8888"]