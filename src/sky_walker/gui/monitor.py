"""Hot-plug device monitor (ticket 08).

Polls which device UDIDs are attached and fires edge callbacks when the tracked
device disappears (on_lost) or comes back after a loss (on_found). The edge
logic is in `tick()` so it can be unit-tested with a scripted poll; `run` just
calls tick() on an interval from a background thread until stopped.

Why polling rather than a usbmux listen stream: it needs no extra pymobiledevice3
surface, tolerates the poll raising (a hiccup reads as "gone"), and a couple of
seconds of latency is fine for a human-driven tool.
"""

from __future__ import annotations

import threading
from typing import Callable, List, Optional


class DeviceMonitor:
    def __init__(
        self,
        udid: Optional[str],
        poll: Callable[[], List[str]],
        on_lost: Callable[[], None],
        on_found: Callable[[List[str]], None],
    ) -> None:
        self._udid = udid
        self._poll = poll
        self._on_lost = on_lost
        self._on_found = on_found
        self._present = True  # begin() already succeeded, so start "present"

    def set_device(self, udid: Optional[str]) -> None:
        """Track a (possibly new) device and treat it as present right now."""
        self._udid = udid
        self._present = True

    def tick(self) -> None:
        try:
            udids = self._poll()
        except Exception:
            udids = []  # a poll failure means we can't see the device -> gone
        here = (self._udid in udids) if self._udid else bool(udids)
        if here and not self._present:
            self._present = True
            self._on_found(udids)
        elif not here and self._present:
            self._present = False
            self._on_lost()

    def run(self, interval: float, stop: threading.Event) -> None:
        """Poll every `interval` seconds until `stop` is set (background thread)."""
        while not stop.wait(interval):
            self.tick()
