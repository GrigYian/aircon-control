"""pywebview host and asynchronous bridge for the React AirCon interface."""

from __future__ import annotations

import asyncio
import sys
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Coroutine

import webview


APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR if getattr(sys, "frozen", False) else APP_DIR.parent
DIST_DIR = APP_DIR / "dist"
sys.path.insert(0, str(PROJECT_DIR))

from ac_controller import (  # noqa: E402
    ACController,
    ACState,
    configuration_summary,
    save_user_configuration,
)


def state_to_dict(state: ACState) -> dict[str, Any]:
    """Convert the immutable controller state to JSON-safe values."""

    result = asdict(state)
    for key in ("supported_modes", "supported_fan_speeds", "supported_features"):
        result[key] = sorted(result[key])
    return result


class AsyncControllerRuntime:
    """Own one asyncio loop so the Midea controller never changes event loops."""

    def __init__(self) -> None:
        self.controller = ACController()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def execute(self, coroutine: Coroutine[Any, Any, ACState]) -> ACState:
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        return future.result(timeout=45)

    def close(self) -> None:
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread.is_alive():
            self.thread.join(timeout=2)


class AirConApi:
    """Methods exposed as promises under window.pywebview.api in React."""

    def __init__(self, runtime: AsyncControllerRuntime) -> None:
        self.runtime = runtime
        self.call_lock = threading.Lock()

    def _response(self, operation: Coroutine[Any, Any, ACState]) -> dict[str, Any]:
        try:
            with self.call_lock:
                state = self.runtime.execute(operation)
            return {"ok": True, "state": state_to_dict(state)}
        except BaseException as error:
            return {
                "ok": False,
                "error": str(error).strip() or error.__class__.__name__,
            }

    def connect(self) -> dict[str, Any]:
        return self._response(self.runtime.controller.connect())

    def refresh(self) -> dict[str, Any]:
        return self._response(self.runtime.controller.refresh())

    def apply(self, changes: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "power",
            "temperature",
            "mode",
            "fan_speed",
            "vertical_swing",
            "horizontal_swing",
            "eco",
            "turbo",
            "frost_protect",
            "display_on",
            "sleep",
            "comfort",
            "purifier",
            "dryer",
        }
        safe_changes = {key: value for key, value in changes.items() if key in allowed}
        if not safe_changes:
            return {"ok": False, "error": "No valid control change was supplied."}
        return self._response(self.runtime.controller.apply(**safe_changes))

    def get_settings(self) -> dict[str, Any]:
        """Return setup values with every stored secret redacted."""

        try:
            return {"ok": True, "settings": configuration_summary()}
        except BaseException as error:
            return {
                "ok": False,
                "error": str(error).strip() or error.__class__.__name__,
            }

    def save_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        """Persist user setup and reset the controller for the next connect."""

        if not isinstance(values, dict):
            return {"ok": False, "error": "Settings must be an object."}
        try:
            with self.call_lock:
                settings = save_user_configuration(values)
                self.runtime.controller = ACController()
            return {"ok": True, "settings": settings}
        except BaseException as error:
            return {
                "ok": False,
                "error": str(error).strip() or error.__class__.__name__,
            }


def main() -> None:
    entrypoint = DIST_DIR / "index.html"
    if not entrypoint.exists():
        raise SystemExit(
            "React build not found. Run `npm install` and `npm run build` "
            f"inside {APP_DIR}."
        )

    runtime = AsyncControllerRuntime()
    api = AirConApi(runtime)
    webview.create_window(
        "AirCon Control",
        str(entrypoint),
        js_api=api,
        width=650,
        height=900,
        min_size=(650, 900),
        resizable=False,
        background_color="#168cf2",
    )
    try:
        webview.start(gui="edgechromium")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
