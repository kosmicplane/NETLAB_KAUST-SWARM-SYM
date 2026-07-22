from __future__ import annotations

import json
import mimetypes
import os
import shutil
import unittest
from pathlib import Path
from urllib.parse import urlparse

from netlab.config import default_experiment

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - environment-dependent
    sync_playwright = None


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "apps" / "mission_control" / "frontend"
SCREENSHOTS = ROOT / "reports" / "validation" / "screenshots"


class MissionControlBrowserTests(unittest.TestCase):
    @unittest.skipUnless(sync_playwright and shutil.which("chromium"), "Playwright/Chromium unavailable")
    def test_all_primary_views_render_without_blank_screen_or_javascript_errors(self):
        configuration = default_experiment()
        status = {
            "ok": True,
            "state": {"phase": "STOPPED", "telemetry_source": "OFFLINE"},
            "readiness": {
                "docker_ready": False,
                "gpu_ready": False,
                "compose_ready": False,
                "sionna_ready": False,
                "ros_container_ready": False,
                "ros_graph_ready": False,
                "packet_runtime_ready": False,
                "isaac_process_ready": False,
                "isaac_scene_ready": False,
                "isaac_scenario_acknowledged": False,
                "telemetry_ready": False,
                "evidence_ready": True,
                "critical_ready": False,
            },
            "services": {},
            "findings": [],
        }
        telemetry = {
            "ok": True,
            "source": {"source": "OFFLINE", "fresh": False, "age_s": None},
            "latest": {},
            "analytics": {},
            "recent_links": [],
            "recent_events": [],
            "samples": [],
        }
        topology_validation = {
            "ok": True,
            "structurally_valid": True,
            "physically_valid": True,
            "communication_feasible": None,
            "operational": False,
            "errors": [],
            "warnings": [],
            "link_preview": [],
        }
        guide_steps = [
            {"id": "welcome", "title": "Welcome", "description": "Understand the SNaaS execution loop.", "automatic": False},
            {"id": "preflight", "title": "Run preflight", "description": "Validate the runtime environment.", "automatic": True},
        ]
        algorithm_manifest = json.loads((ROOT / "plugins" / "research" / "connectivity_aware_formation" / "manifest.json").read_text(encoding="utf-8"))
        algorithm_package = {
            "manifest": algorithm_manifest,
            "package_dir": "plugins/research/connectivity_aware_formation",
            "manifest_path": "plugins/research/connectivity_aware_formation/manifest.json",
            "entrypoint": "plugins/research/connectivity_aware_formation/algorithm.py",
            "valid": True,
            "errors": [],
            "warnings": [],
        }

        def payload(path: str, method: str) -> dict:
            if path == "/api/health":
                return {"ok": True, "service": "NETLAB Mission Control", "version": "9.0.0", "api_version": "v1"}
            if path in {"/api/readiness", "/api/status"}:
                return status
            if path == "/api/telemetry":
                return telemetry
            if path == "/api/jobs":
                return {"ok": True, "jobs": []}
            if path == "/api/config":
                return {"ok": True, "config": configuration, "validation": {"ok": True, "errors": [], "warnings": []}, "config_hash": "test"}
            if path == "/api/topology":
                return {"ok": True, "topology": configuration["topology"], "validation": topology_validation}
            if path == "/api/scenarios":
                return {"ok": True, "scenarios": [{"name": "First Feasible Relay Chain", "path": "scenarios/examples/first_feasible_relay_chain.json"}]}
            if path == "/api/plugins":
                return {"ok": True, "api_version": "1.0", "plugins": []}
            if path == "/api/algorithms":
                return {"ok": True, "api_version": "2.0", "count": 1, "valid_count": 1, "categories": ["formation_controller"], "algorithms": [algorithm_package]}
            if path == "/api/algorithms/connectivity_aware_formation":
                return {"ok": True, "algorithm": algorithm_package}
            if path == "/api/algorithm/source":
                return {"ok": True, "algorithm_id": "connectivity_aware_formation", "source": "def step(snapshot, parameters):\n    return {\"desired_positions\": {}}\n", "source_hash": "browser-source"}
            if path == "/api/algorithm/selection":
                return {"ok": True, "selection": {}}
            if path == "/api/algorithm/runs":
                return {"ok": True, "runs": []}
            if path == "/api/evidence":
                return {"ok": True, "files": [], "index": []}
            if path in {"/api/guide", "/api/guided-demo"}:
                return {"ok": True, "steps": guide_steps}
            if path == "/api/synchronization":
                return {"ok": True, "synchronization": {"state": "NO_REVISION", "participants": {}, "in_sync": False}, "revisions": []}
            if path == "/api/revisions":
                return {"ok": True, "revisions": []}
            if path == "/api/diagnostics":
                return status
            if path == "/api/packet-doctor":
                return {"ok": False, "findings": [], "heartbeat": {}, "latest_gate": {}}
            if path == "/api/events":
                return {"ok": True, "events": []}
            if path.startswith("/api/logs/"):
                return {"ok": True, "logs": ""}
            if path.startswith("/api/") and method == "POST":
                return {
                    "ok": True,
                    "durable_saved": True,
                    "committed": False,
                    "config": configuration,
                    "topology_validation": topology_validation,
                    "synchronization": {"state": "PENDING_ROS", "participants": {"ros": {"state": "PENDING"}}},
                    "command": {"status": "PARTIALLY_APPLIED"},
                    "job": {"job_id": "browser-job", "name": "test", "status": "QUEUED", "progress": []},
                }
            return {"ok": True}

        errors: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                executable_path=shutil.which("chromium"),
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.on("pageerror", lambda error: errors.append(f"pageerror:{error}"))
            page.on("console", lambda message: errors.append(f"console:{message.type}:{message.text}") if message.type == "error" else None)

            def route_handler(route, request):
                path = urlparse(request.url).path
                if path == "/api/telemetry/stream":
                    body = f"event: telemetry\ndata: {json.dumps(telemetry)}\n\n".encode()
                    route.fulfill(status=200, body=body, headers={"Content-Type": "text/event-stream", "Cache-Control": "no-store"})
                    return
                if path.startswith("/api/"):
                    route.fulfill(status=200, body=json.dumps(payload(path, request.method)).encode(), headers={"Content-Type": "application/json", "Cache-Control": "no-store"})
                    return
                relative = "index.html" if path == "/" else path.lstrip("/")
                target = (FRONTEND / relative).resolve()
                if FRONTEND.resolve() not in target.parents and target != FRONTEND.resolve():
                    route.fulfill(status=403, body="forbidden")
                    return
                if not target.is_file():
                    target = FRONTEND / "index.html"
                content_type = {".js": "text/javascript", ".css": "text/css", ".html": "text/html"}.get(target.suffix, mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                route.fulfill(status=200, body=target.read_bytes(), headers={"Content-Type": content_type, "Cache-Control": "no-store"})

            page.route("http://netlab.test/**", route_handler)
            html = (FRONTEND / "index.html").read_text(encoding="utf-8").replace("<head>", '<head><base href="http://netlab.test/">', 1)
            page.set_content(html, wait_until="domcontentloaded")
            page.wait_for_function("window.__NETLAB_APP_READY__ === true", timeout=15_000)
            self.assertEqual(page.locator("#primary-nav button").count(), 17)
            self.assertGreater(page.locator("#view-root").bounding_box()["height"], 100)

            labels = [page.locator("#primary-nav button").nth(index).inner_text() for index in range(page.locator("#primary-nav button").count())]
            SCREENSHOTS.mkdir(parents=True, exist_ok=True)
            for label in labels:
                page.get_by_role("button", name=label, exact=True).click()
                page.wait_for_timeout(75)
                self.assertEqual(page.get_by_text("The view could not be rendered", exact=True).count(), 0, label)
                self.assertGreater(len(page.locator("#view-root").inner_text().strip()), 15, label)
                if os.environ.get("NETLAB_CAPTURE_SCREENSHOTS") == "1" and label in {"Overview", "Guided Demo", "Mission Designer", "Topology Studio", "Algorithm Lab", "Live Telemetry", "Synchronization"}:
                    filename = label.lower().replace(" ", "_").replace("&", "and") + ".png"
                    page.screenshot(path=str(SCREENSHOTS / filename), full_page=True)
            browser.close()

        self.assertEqual(errors, [], "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
