#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../compose"
docker compose --env-file .env -f docker-compose.yml up -d isaac
docker logs -f isaac-sim
