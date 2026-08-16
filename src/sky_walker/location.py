"""Location Override session — the app-facing facade.

Wraps backend.LocationSession so the interactive loop and CLI never touch
pymobiledevice3 directly (docs/adr/0001). The context manager owns the Session
lifetime and guarantees a clear-on-exit (docs/adr/0002).
"""

from __future__ import annotations

from types import TracebackType
from typing import Optional, Type

from sky_walker.config import Coordinate
from sky_walker.device import Device


class LocationOverride:
    """Context manager holding one live override over a single tunnel."""

    def __init__(self, device: Device) -> None:
        self._device = device
        self._session = None  # backend.LocationSession, opened on __enter__

    def __enter__(self) -> "LocationOverride":
        from sky_walker import backend

        self._session = backend.LocationSession.open(self._device)
        return self

    def teleport(self, coord: Coordinate) -> None:
        assert self._session is not None, "session not opened"
        self._session.set_location(coord)

    def clear(self) -> None:
        if self._session is not None:
            self._session.clear()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        # Always revert and tear down, however we leave (ADR-0002).
        if self._session is not None:
            self._session.close()
            self._session = None


def clear_once(udid: Optional[str] = None) -> None:
    """Emergency `sky-walker clear`: open, clear, tear down.

    Rarely needed — leaving a session already reverts the device — but useful if
    a previous run was killed uncleanly and you want to be sure.
    """
    from sky_walker import backend
    from sky_walker.device import select_device

    device = select_device(udid)
    session = backend.LocationSession.open(device)
    try:
        session.clear()
    finally:
        session.close()
