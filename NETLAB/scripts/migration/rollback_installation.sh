#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <backup-directory> [active-directory]" >&2
  echo "Example: $0 ~/NETLAB_backup_20260715_120000 ~/NETLAB" >&2
}

BACKUP="${1:-}"
ACTIVE="${2:-$HOME/NETLAB}"
[[ -n "$BACKUP" ]] || { usage; exit 2; }
BACKUP="$(realpath -e "$BACKUP")"
ACTIVE="$(realpath -m "$ACTIVE")"
[[ -d "$BACKUP" ]] || { echo "[ERROR] Backup directory does not exist: $BACKUP" >&2; exit 1; }
[[ "$BACKUP" != "$ACTIVE" ]] || { echo "[ERROR] Backup and active paths are identical." >&2; exit 1; }

if [[ -x "$ACTIVE/scripts/netlab" ]]; then
  "$ACTIVE/scripts/netlab" stop || true
fi
if [[ -x "$ACTIVE/scripts/netlab_mission_control.sh" ]]; then
  "$ACTIVE/scripts/netlab_mission_control.sh" stop || true
fi

FAILED="${ACTIVE}_failed_$(date +%Y%m%d_%H%M%S)"
if [[ -e "$ACTIVE" ]]; then
  mv "$ACTIVE" "$FAILED"
  echo "[INFO] Previous active directory moved to: $FAILED"
fi
mv "$BACKUP" "$ACTIVE"
echo "[OK] Restored NETLAB directory: $ACTIVE"
echo "[ACTION] Run: cd '$ACTIVE' && ./scripts/netlab bootstrap --non-interactive --no-start"
