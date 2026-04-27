FROM px4io/px4-dev:v1.16.0

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    git-lfs \
    vim \
    nano \
    tmux \
    htop \
    iputils-ping \
    net-tools \
    curl \
    wget \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone --recursive https://github.com/PX4/PX4-Autopilot.git
WORKDIR /opt/PX4-Autopilot
CMD ["/bin/bash"]
