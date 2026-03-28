FROM nvidia/cuda:13.2.0-cudnn-devel-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
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
    && locale-gen en_US en_US.UTF-8 \
    && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv $VIRTUAL_ENV && \
    $VIRTUAL_ENV/bin/pip install --upgrade pip setuptools wheel

RUN pip install \
    tensorflow==2.19.* \
    sionna \
    jupyterlab \
    numpy \
    scipy \
    matplotlib \
    pandas \
    seaborn \
    plotly \
    ipykernel

WORKDIR /workspace

CMD ["/bin/bash"]