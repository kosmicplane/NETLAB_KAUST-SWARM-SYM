FROM nvcr.io/nvidia/isaac-sim:5.1.0

SHELL ["/bin/bash", "-c"]

USER root

RUN mkdir -p /var/lib/apt/lists/partial && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        wget \
        curl \
        vim \
        nano \
        tmux \
        python3-pip \
        iputils-ping \
        net-tools && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

CMD ["/bin/bash"]