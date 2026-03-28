# NOTE:
# Replace the base image tag with the exact NGC Isaac Sim container tag you plan to use.
# Example tags are published on NVIDIA NGC and require GPU runtime plus NGC access.
FROM nvcr.io/nvidia/isaac-sim:5.1.0

ENV ACCEPT_EULA=Y \
    PRIVACY_CONSENT=Y \
    OMNI_KIT_ACCEPT_EULA=YES

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    wget \
    curl \
    vim \
    nano \
    tmux \
    python3-pip \
    iputils-ping \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Helpful Python packages for bridge / scripting extensions
RUN ./python.sh -m pip install --upgrade pip && \
    ./python.sh -m pip install \
      numpy \
      scipy \
      pandas \
      pyyaml

WORKDIR /isaac-sim
CMD ["bash"]
