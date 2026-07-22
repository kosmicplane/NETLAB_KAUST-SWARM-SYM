FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    TF_FORCE_GPU_ALLOW_GROWTH=true

COPY requirements/sionna-requirements.txt /tmp/sionna-requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    build-essential \
    pkg-config \
    vim \
    nano \
    tmux \
    iputils-ping \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv $VIRTUAL_ENV && \
    pip install --upgrade pip setuptools wheel && \
    pip install -r /tmp/sionna-requirements.txt

WORKDIR /workspace/sionna
CMD ["/bin/bash"]
