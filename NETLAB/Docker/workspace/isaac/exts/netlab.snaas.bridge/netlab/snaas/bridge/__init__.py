from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

try:
    import omni.ext  # type: ignore
    import omni.kit.app  # type: ignore
except Exception:  # Allows source inspection outside Isaac Sim.
    omni = None  # type: ignore


class Extension((omni.ext.IExt if omni is not None else object)):  # type: ignore[misc]
    def on_startup(self, ext_id):
        script = Path("/workspace/isaac/scripts/netlab_snaas_bridge.py")
        spec = importlib.util.spec_from_file_location("netlab_snaas_bridge_runtime", script)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load NETLAB bridge from {script}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self._module = module
        self._subscription = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            lambda _event: self._module.tick(), name="NETLAB SNaaS bridge update"
        )
        self._module.tick()

    def on_shutdown(self):
        self._subscription = None
        self._module = None
