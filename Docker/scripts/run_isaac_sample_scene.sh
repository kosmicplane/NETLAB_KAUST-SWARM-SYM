#!/usr/bin/env bash
set -euo pipefail

if ! docker ps --format '{{.Names}}' | grep -q '^isaac-sim$'; then
    echo "isaac-sim container is not running. Start it first:"
    echo "  cd compose && make up-isaac"
    exit 1
fi

echo "Running Isaac Sim visual validation scene..."
docker exec -it isaac-sim bash -lc 'cd /isaac-sim && ./python.sh /workspace/isaac/scripts/basic_swarm_scene.py'
