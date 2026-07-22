# Rollback and Recovery

NETLAB is delivered as one complete repository. The safest software rollback is directory-level and must be performed only after stopping the current stack.

## Clean-install rollback

Assume the active installation is `~/NETLAB` and a known-good archive or directory is available.

```bash
cd "$HOME/NETLAB"
./scripts/netlab stop || true
./scripts/netlab_mission_control.sh stop || true

cd "$HOME"
mv NETLAB "NETLAB_failed_$(date +%Y%m%d_%H%M%S)"
unzip /path/to/KNOWN_GOOD_NETLAB.zip
cd NETLAB
./scripts/netlab bootstrap --non-interactive --no-start
./scripts/netlab launch --no-build
```

Do not reuse generated ROS `build/`, `install/`, or `log/` directories from another release. Rebuild them in the target environment.

## Revision rollback

For an experiment edit that has not committed correctly, prefer a runtime revision rollback rather than replacing the repository:

```bash
cd ~/NETLAB
./scripts/netlab revision-status
./scripts/netlab rollback-revision <REVISION_ID> --reason operator_rollback
./scripts/netlab reconcile
./scripts/netlab sync-doctor
```

A rollback is complete only when required ROS, Sionna, and Isaac participants acknowledge the rollback revision and observed hashes match.

## Configuration-only recovery

To restore a validated scenario:

```bash
cd ~/NETLAB
cp scenarios/templates/default_reference_experiment.json \
   Docker/workspace/shared/snaas_relay_config.json
./scripts/netlab validate
./scripts/netlab sync
```

Use Mission Designer import when preserving a user-authored run history is important.

## Runtime-state recovery

Generated runtime output may be cleared without deleting source/scenarios:

```bash
cd ~/NETLAB
./scripts/netlab stop || true
./scripts/netlab clean --runtime
./scripts/netlab doctor --repair
./scripts/netlab launch --no-build
```

## Evidence preservation

Before destructive rollback, preserve the support bundle and any run evidence needed for diagnosis:

```bash
cd ~/NETLAB
./scripts/netlab support-bundle --reason pre_rollback
```

Do not copy old heartbeat/status files into a new installation because stale data could be misinterpreted. Completed run directories and structured evidence may be archived separately.

## Scripted directory rollback

When a timestamped repository backup exists, use the bounded rollback helper:

```bash
./scripts/migration/rollback_installation.sh \
  "$HOME/NETLAB_backup_YYYYMMDD_HHMMSS" \
  "$HOME/NETLAB"
```

The helper stops the active stack, moves the failed installation aside, restores the selected backup, and prints the required preparation command. It does not merge generated runtime state across releases.
