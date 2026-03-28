# Pegasus is designed to run on top of Isaac Sim's Python/runtime.
FROM nvcr.io/nvidia/isaac-sim:5.1.0

ENV ACCEPT_EULA=Y \
    PRIVACY_CONSENT=Y \
    OMNI_KIT_ACCEPT_EULA=YES \
    PEGASUS_ROOT=/opt/PegasusSimulator

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    wget \
    curl \
    unzip \
    vim \
    nano \
    tmux \
    python3-pip \
    iputils-ping \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/PegasusSimulator/PegasusSimulator.git ${PEGASUS_ROOT}

# Install Python-side dependencies into Isaac Sim's bundled Python.
RUN ./python.sh -m pip install --upgrade pip && \
    if [ -f ${PEGASUS_ROOT}/requirements.txt ]; then ./python.sh -m pip install -r ${PEGASUS_ROOT}/requirements.txt; fi && \
    ./python.sh -m pip install empy transforms3d numpy scipy pyyaml

WORKDIR /opt/PegasusSimulator
CMD ["bash"]
