#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'TXT'
Usage:
  migrate_from_v4.sh SOURCE_NETLAB [TARGET_NETLAB]

Imports operator-owned configuration, environment settings, controller plugins,
and user assets from an existing NETLAB v4/v4.1 tree into this the current NETLAB repository.
The target defaults to the repository containing this script.

The script never deletes the source. It creates a timestamped target backup and
writes a migration manifest under reports/migration/.
TXT
}

[[ ${1:-} == "-h" || ${1:-} == "--help" ]] && { usage; exit 0; }
[[ $# -ge 1 ]] || { usage >&2; exit 2; }

SOURCE="$(cd "$1" && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_TARGET="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET="${2:-$DEFAULT_TARGET}"
TARGET="$(cd "$TARGET" && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${TARGET}_pre_migration_${STAMP}"
REPORT_DIR="$TARGET/reports/migration"
MANIFEST="$REPORT_DIR/migration_${STAMP}.txt"

[[ -f "$SOURCE/Docker/compose/docker-compose.yml" ]] || { echo "[ERROR] Source does not look like NETLAB: $SOURCE" >&2; exit 1; }
[[ -f "$TARGET/scripts/netlab" ]] || { echo "[ERROR] Target does not contain the NETLAB CLI: $TARGET" >&2; exit 1; }
[[ "$SOURCE" != "$TARGET" ]] || { echo "[ERROR] Source and target must be different directories." >&2; exit 1; }

mkdir -p "$REPORT_DIR"
cp -a "$TARGET" "$BACKUP"
{
  echo "NETLAB brownfield migration"
  echo "timestamp_utc=$STAMP"
  echo "source=$SOURCE"
  echo "target=$TARGET"
  echo "target_backup=$BACKUP"
} > "$MANIFEST"

copy_if_present() {
  local source_path="$1" target_path="$2" label="$3"
  if [[ -e "$source_path" ]]; then
    mkdir -p "$(dirname "$target_path")"
    cp -a "$source_path" "$target_path"
    echo "copied:$label:$source_path:$target_path" >> "$MANIFEST"
  else
    echo "absent:$label:$source_path" >> "$MANIFEST"
  fi
}

# Preserve the release defaults and import deployment-specific values.
if [[ -f "$TARGET/Docker/compose/.env" ]]; then
  cp -a "$TARGET/Docker/compose/.env" "$TARGET/Docker/compose/.env.release-default"
fi
copy_if_present "$SOURCE/Docker/compose/.env" "$TARGET/Docker/compose/.env" "compose_environment"

# Preserve the original configuration as forensic evidence, then migrate it.
LEGACY_CONFIG="$SOURCE/Docker/workspace/shared/snaas_relay_config.json"
if [[ -f "$LEGACY_CONFIG" ]]; then
  copy_if_present "$LEGACY_CONFIG" "$TARGET/Docker/workspace/shared/snaas_relay_config.pre-v5.json" "legacy_configuration"
  NETLAB_ROOT="$TARGET" PYTHONPATH="$TARGET${PYTHONPATH:+:$PYTHONPATH}" \
    "$TARGET/scripts/netlab" migrate-config \
    "$TARGET/Docker/workspace/shared/snaas_relay_config.pre-v5.json" \
    --output "$TARGET/Docker/workspace/shared/snaas_relay_config.json" \
    >> "$MANIFEST"
fi

# Controller plugins and user-provided Isaac assets are operator-owned content.
if [[ -d "$SOURCE/plugins/controllers" ]]; then
  mkdir -p "$TARGET/plugins/controllers"
  rsync -a --exclude='__pycache__/' --exclude='*.pyc' "$SOURCE/plugins/controllers/" "$TARGET/plugins/controllers/"
  echo "merged:controller_plugins" >> "$MANIFEST"
fi
if [[ -d "$SOURCE/Docker/workspace/plugins" ]]; then
  mkdir -p "$TARGET/Docker/workspace/plugins"
  rsync -a --exclude='__pycache__/' --exclude='*.pyc' "$SOURCE/Docker/workspace/plugins/" "$TARGET/Docker/workspace/plugins/"
  echo "merged:runtime_plugins" >> "$MANIFEST"
fi
if [[ -d "$SOURCE/Docker/workspace/isaac/local_assets" ]]; then
  mkdir -p "$TARGET/Docker/workspace/isaac/local_assets"
  rsync -a "$SOURCE/Docker/workspace/isaac/local_assets/" "$TARGET/Docker/workspace/isaac/local_assets/"
  echo "merged:isaac_local_assets" >> "$MANIFEST"
fi

# Runtime output is not imported into the active results directory. Preserve an
# evidence copy so stale samples cannot be mislabeled LIVE after migration.
if [[ -d "$SOURCE/Docker/workspace/results" ]]; then
  mkdir -p "$TARGET/reports/migration/imported_runtime_evidence_${STAMP}"
  rsync -a --exclude='__pycache__/' "$SOURCE/Docker/workspace/results/" "$TARGET/reports/migration/imported_runtime_evidence_${STAMP}/"
  echo "archived:runtime_evidence:reports/migration/imported_runtime_evidence_${STAMP}" >> "$MANIFEST"
fi

chmod +x "$TARGET/scripts/netlab" "$TARGET/scripts/"*.sh "$TARGET/scripts/migration/"*.sh 2>/dev/null || true
NETLAB_ROOT="$TARGET" PYTHONPATH="$TARGET${PYTHONPATH:+:$PYTHONPATH}" "$TARGET/scripts/netlab" validate >> "$MANIFEST"
NETLAB_ROOT="$TARGET" PYTHONPATH="$TARGET${PYTHONPATH:+:$PYTHONPATH}" "$TARGET/scripts/netlab" verify >> "$MANIFEST"

echo "[OK] Migration completed."
echo "[INFO] Target backup: $BACKUP"
echo "[INFO] Manifest: $MANIFEST"
