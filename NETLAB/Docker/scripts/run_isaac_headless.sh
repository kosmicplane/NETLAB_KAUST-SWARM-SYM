#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../compose"
make up-isaac
docker logs -f isaac-sim
