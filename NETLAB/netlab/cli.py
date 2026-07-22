"""NETLAB authoritative command-line interface.

Mission Control and the CLI delegate to the same :class:`Orchestrator`; there
is no second startup path. Every command emits machine-readable JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .acceptance import run_embedded_acceptance
from .bootstrap import Bootstrapper
from .config import default_experiment, load_experiment, migrate_legacy_config, save_experiment, validate_experiment
from .orchestrator import Orchestrator
from .plugins import discover, template
from .version import __version__


def repository_root() -> Path:
    return Path(os.environ.get("NETLAB_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()


def emit(payload: Any) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if isinstance(payload, dict) and payload.get("ok", False) else 1


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="netlab", description="NETLAB Swarm Network-as-a-Service control plane")
    p.add_argument("--root", type=Path, default=repository_root())
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap", help="Prepare the host and optionally start the complete stack.")
    bootstrap.add_argument("--no-build", action="store_true")
    bootstrap.add_argument("--prepare-only", action="store_true")
    bootstrap.add_argument("--non-interactive", action="store_true")

    for name in ("start", "launch"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--no-build", action="store_true")

    sub.add_parser("status")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--repair", action="store_true")
    sub.add_parser("packet-doctor")
    sub.add_parser("sync-doctor")
    sub.add_parser("smoke-test")
    sync = sub.add_parser("sync")
    sync.add_argument("--reason", default="operator_request")
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--revision-id", default="")
    sub.add_parser("revision-status")
    rollback = sub.add_parser("rollback-revision")
    rollback.add_argument("revision_id")
    rollback.add_argument("--reason", default="operator_rollback")

    sub.add_parser("stop")
    restart = sub.add_parser("restart")
    restart.add_argument("--no-build", action="store_true")
    logs = sub.add_parser("logs")
    logs.add_argument("service", nargs="?", default="")
    logs.add_argument("--tail", type=int, default=500)

    sub.add_parser("reset-experiment")
    validate = sub.add_parser("validate")
    validate.add_argument("path", nargs="?", type=Path)
    migrate = sub.add_parser("migrate-config")
    migrate.add_argument("input", nargs="?", type=Path)
    migrate.add_argument("--output", type=Path)

    verify = sub.add_parser("verify")
    verify.add_argument("--embedded", action="store_true")
    target = sub.add_parser("target-acceptance")
    target.add_argument("--embedded", action="store_true")
    target.add_argument("--output", type=Path)

    support = sub.add_parser("support-bundle")
    support.add_argument("--reason", default="operator_request")
    clean = sub.add_parser("clean")
    clean.add_argument("--runtime", action="store_true")

    serve = sub.add_parser("serve")
    serve.add_argument("--host", default=os.environ.get("NETLAB_MISSION_HOST", "0.0.0.0"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("NETLAB_MISSION_PORT", "8765")))

    plugins = sub.add_parser("plugins")
    plugins.add_argument("--directory", type=Path)
    plugin_template = sub.add_parser("plugin-template")
    plugin_template.add_argument("path", type=Path)

    for control in ("fail", "heal", "standby", "promote"):
        ctl = sub.add_parser(control)
        ctl.add_argument("index", type=int)
    sub.add_parser("reset-chain")
    sub.add_parser("recompute-topology")
    sub.add_parser("start-experiment")
    return p


def _clean_runtime(orchestrator: Orchestrator) -> dict[str, Any]:
    removed: list[str] = []
    results = orchestrator.store.paths.results
    for path in list(results.iterdir()) if results.exists() else []:
        if path.name == ".gitkeep":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        removed.append(str(path))
    results.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "removed": removed}


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    orchestrator = Orchestrator(root)
    bootstrapper = Bootstrapper(root, orchestrator.compose)

    try:
        if args.command == "bootstrap":
            return emit(bootstrapper.bootstrap(build=not args.no_build, start=not args.prepare_only, non_interactive=args.non_interactive))
        if args.command == "launch":
            mission = bootstrapper._start_mission_control()
            stack = orchestrator.start_stack(build=not args.no_build)
            return emit({"ok": bool(mission.get("ok") and stack.get("ok")), "mission_control": mission, "stack": stack, "url": "http://127.0.0.1:8765"})
        if args.command == "start":
            return emit(orchestrator.start_stack(build=not args.no_build))
        if args.command == "status":
            return emit({"ok": True, **orchestrator.status()})
        if args.command == "doctor":
            return emit(orchestrator.preflight(repair=args.repair))
        if args.command == "packet-doctor":
            return emit(orchestrator.packet_doctor())
        if args.command == "sync-doctor":
            return emit(orchestrator.sync_doctor())
        if args.command == "smoke-test":
            return emit(orchestrator.smoke_test())
        if args.command == "sync":
            return emit(orchestrator.synchronize(args.reason))
        if args.command == "reconcile":
            return emit(orchestrator.reconcile(args.revision_id))
        if args.command == "revision-status":
            return emit({"ok": True, "synchronization": orchestrator.revisions.status(), "desired": orchestrator.revisions.desired(), "committed": orchestrator.revisions.committed()})
        if args.command == "rollback-revision":
            record = orchestrator.revisions.rollback(args.revision_id, reason=args.reason)
            return emit({"ok": True, "committed": False, "revision": record, "synchronization": orchestrator.revisions.status(record["revision_id"])})
        if args.command == "stop":
            return emit(orchestrator.stop_stack())
        if args.command == "restart":
            return emit(orchestrator.restart_stack(build=not args.no_build))
        if args.command == "logs":
            return emit(orchestrator.logs(args.service, args.tail))
        if args.command == "reset-experiment":
            config = default_experiment()
            save_experiment(orchestrator.store.paths.config, config, emit_legacy=True)
            revision = orchestrator.revisions.create(config, reason="experiment_reset", command_id="cli-reset", initiator="cli")
            return emit({"ok": True, "config": config, "revision": revision, "committed": False})
        if args.command == "validate":
            path = (args.path or orchestrator.store.paths.config).expanduser().resolve()
            result = validate_experiment(load_experiment(path), strict=False)
            return emit({"path": str(path), **result})
        if args.command == "migrate-config":
            source = (args.input or orchestrator.store.paths.config).expanduser().resolve()
            target = (args.output or orchestrator.store.paths.config).expanduser().resolve()
            raw = json.loads(source.read_text(encoding="utf-8"))
            migrated = validate_experiment(migrate_legacy_config(raw), strict=True)["config"]
            save_experiment(target, migrated, emit_legacy=True)
            return emit({"ok": True, "input": str(source), "output": str(target), "config": migrated})
        if args.command == "verify":
            if args.embedded:
                return emit(run_embedded_acceptance(orchestrator.store.paths.results / "embedded_acceptance"))
            completed = subprocess.run([sys.executable, str(root / "tests" / "run_all.py")], cwd=str(root), text=True, capture_output=True, check=False)
            return emit({"ok": completed.returncode == 0, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr})
        if args.command == "target-acceptance":
            output = args.output or orchestrator.store.paths.results / "target_acceptance"
            if args.embedded:
                return emit(run_embedded_acceptance(output))
            launch = orchestrator.start_stack(build=False)
            smoke = orchestrator.smoke_test() if launch.get("ok") else {"ok": False, "skipped": True}
            return emit({"ok": bool(launch.get("ok") and smoke.get("ok")), "launch": launch, "smoke": smoke})
        if args.command == "support-bundle":
            return emit(orchestrator.support_bundle(args.reason))
        if args.command == "clean":
            return emit(_clean_runtime(orchestrator) if args.runtime else {"ok": False, "error": {"code": "CLEAN_SCOPE_REQUIRED", "message": "Use --runtime."}})
        if args.command == "serve":
            from apps.mission_control.backend.server import serve
            serve(root=root, host=args.host, port=args.port)
            return 0
        if args.command == "plugins":
            directory = args.directory or root / "plugins" / "controllers"
            return emit({"ok": True, "plugins": discover(directory)})
        if args.command == "plugin-template":
            args.path.parent.mkdir(parents=True, exist_ok=True)
            args.path.write_text(template(), encoding="utf-8")
            return emit({"ok": True, "path": str(args.path)})
        if args.command in {"fail", "heal", "standby", "promote", "reset-chain", "recompute-topology", "start-experiment"}:
            from apps.mission_control.backend.server import MissionControlApplication
            app = MissionControlApplication(root)
            mapping = {
                "fail": "fail_uav", "heal": "heal_uav", "standby": "standby_uav", "promote": "promote_standby",
                "reset-chain": "reset_chain", "recompute-topology": "recompute_topology", "start-experiment": "start_experiment",
            }
            payload = {"index": args.index} if hasattr(args, "index") else {}
            return emit(app.command(mapping[args.command], payload))
    except Exception as exc:
        return emit({"ok": False, "error": {"code": "CLI_COMMAND_FAILED", "type": type(exc).__name__, "message": str(exc)}})
    return emit({"ok": False, "error": {"code": "UNKNOWN_COMMAND", "message": str(args.command)}})


if __name__ == "__main__":
    raise SystemExit(main())
