"""Launch the desktop GUI: show the map, watch for hot-plug, revert on close.

The window's lifetime IS the Session's lifetime. The front-end runs the startup
gate (Bridge.preflight), then opens the held override (Bridge.begin); while the
window is open the override stays live (the "one tunnel, re-teleport" model of
ADR-0002). Closing the window calls Bridge.shutdown, so the device auto-reverts
to its real GPS — pymobiledevice3 cannot persist an override past the process,
and ADR-0002 treats that auto-revert as a feature.

A DeviceMonitor polls in the background: on unplug it drops the session and tells
the page (skyOnLost); on replug it tells the page (skyOnFound), which reopens the
session and offers to reapply the last override.

pywebview is imported lazily so the rest of the package (and `sky-walker --help`)
works without the optional [gui] dependency installed.
"""

from __future__ import annotations

import threading
from importlib.resources import files
from typing import Optional

from sky_walker.config import DEFAULT_LOCATION
from sky_walker.gui.bridge import Bridge
from sky_walker.gui.monitor import DeviceMonitor

_POLL_INTERVAL_SECONDS = 2.0


def _load_html() -> str:
    return (files("sky_walker.gui") / "web" / "index.html").read_text(encoding="utf-8")


def run_gui(udid: Optional[str] = None) -> int:
    """Entry point for `sky-walker gui`. Returns a process exit code."""
    try:
        import webview
    except ImportError:
        print(
            "The GUI needs the optional 'gui' extra. Install it with:\n"
            "    pip install -e .[gui]"
        )
        return 1

    monitor_holder = {}  # filled once the monitor exists, so begin() can retarget it
    bridge = Bridge(
        DEFAULT_LOCATION,
        udid,
        on_device_change=lambda u: monitor_holder.get("m") and monitor_holder["m"].set_device(u),
    )

    window = webview.create_window(
        "Sky Walker",
        html=_load_html(),
        js_api=bridge,
        width=1000,
        height=720,
        confirm_close=True,  # one confirmation before the window (and override) closes
    )

    def on_lost() -> None:
        bridge.on_lost()
        window.evaluate_js("window.skyOnLost && window.skyOnLost()")

    def on_found(_present) -> None:
        window.evaluate_js("window.skyOnFound && window.skyOnFound()")

    monitor = DeviceMonitor(
        udid=udid,
        poll=lambda: [d["udid"] for d in bridge.list_devices()],
        on_lost=on_lost,
        on_found=on_found,
    )
    monitor_holder["m"] = monitor

    stop = threading.Event()
    watcher = threading.Thread(
        target=monitor.run, args=(_POLL_INTERVAL_SECONDS, stop),
        name="sky-walker-hotplug", daemon=True,
    )
    watcher.start()

    try:
        webview.start()  # blocks until the window is closed
    finally:
        stop.set()
        bridge.shutdown()  # revert the device however we leave

    print("GUI closed; device reverted to its real GPS.")
    return 0
