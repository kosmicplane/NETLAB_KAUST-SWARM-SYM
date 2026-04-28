#!/usr/bin/env bash
set -euo pipefail

echo "[1/4] Host GPU check"
nvidia-smi

echo "[2/4] Docker version"
docker --version
docker compose version

echo "[3/4] NVIDIA container runtime check"
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu24.04 nvidia-smi

echo "[4/4] Done. Docker can access the GPU."
