"""The Python API the webview's JavaScript calls (the GUI's testable seam).

pywebview exposes an instance of Bridge to the page as `window.pywebview.api`;
each method's return value comes back to JS as a resolved Promise. Bridge owns
the GUI's session lifecycle — preflight, device selection, opening/closing the
held LocationOverride, teleporting, and reporting status — so the launcher
(app.py) only has to create the window and tear down on exit.

It imports neither pywebview nor pymobiledevice3, and every device-touching
collaborator (device selection, override creation, preflight) is injectable, so
the whole surface is unit-testable with fakes. The real collaborators are wired
in by default.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from sky_walker import doctor
from sky_walker.config import Coordinate, parse_coordinate
from sky_walker.device import Device
from sky_walker.errors import SkyWalkerError


class Bridge:
    def __init__(
        self,
        default_location: Coordinate,
        udid: Optional[str] = None,
        *,
        preflight: Optional[Callable[[Optional[str]], "doctor.DoctorReport"]] = None,
        device_lister: Optional[Callable[[], List[Device]]] = None,
        device_selector: Optional[Callable[[Optional[str]], Device]] = None,
        override_factory: Optional[Callable[[Device], Any]] = None,
        on_device_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._default = default_location
        self._udid = udid

        self._preflight = preflight or (lambda u: doctor.collect(u))
        self._list = device_lister or _default_lister
        self._select = device_selector or _default_selector
        self._make_override = override_factory or _default_override
        self._on_device_change = on_device_change or (lambda udid: None)

        self._device: Optional[Device] = None
        self._override = None          # the entered LocationOverride, or None
        self._active: Optional[Coordinate] = None   # currently LIVE override, or None
        self._last: Optional[Coordinate] = None     # last coord, kept for reapply

    # --- preflight & device discovery (tickets 05, 06, 07) ------------------

    def preflight(self) -> Dict[str, Any]:
        """Run the Doctor checks; used by the startup gate and the 🩺 panel."""
        return self._preflight(self._udid).as_dict()

    def list_devices(self) -> List[Dict[str, str]]:
        """Every attached device, for the picker. Empty list if none/errored."""
        try:
            return [{"udid": d.udid, "ios": d.ios_version} for d in self._list()]
        except SkyWalkerError:
            return []

    # --- session lifecycle (tickets 05, 07, 08) -----------------------------

    def begin(self, udid: Optional[str] = None) -> Dict[str, Any]:
        """Open (or re-open) the held Session for a device.

        Called after the startup gate passes, when the user picks a device, and
        on reconnect. Closes any existing session first so re-begin is safe.
        """
        self._teardown()
        target = udid if udid is not None else self._udid
        try:
            device = self._select(target)
            supported, reason = device.check_supported()
            if not supported:
                return {"ok": False, "error": reason, "hint": ""}
            override = self._make_override(device)
            override.__enter__()
        except SkyWalkerError as exc:
            return {"ok": False, "error": str(exc), "hint": exc.hint}

        self._device = device
        self._override = override
        self._udid = device.udid
        self._on_device_change(device.udid)  # keep the hot-plug monitor in sync
        return {"ok": True, "device": device.udid, "ios": device.ios_version}

    def shutdown(self) -> None:
        """Tear down on window close; the device reverts to its real GPS."""
        self._teardown()

    def on_lost(self) -> None:
        """Device unplugged: drop the (now-dead) session, keeping last_active.

        The tunnel is gone, so the override is already void; we tear the session
        down so status reads disconnected and clear the live override, but keep
        `_last` so reconnect can offer to reapply it (ticket 08).
        """
        self._teardown()
        self._active = None  # nothing is live once the cable is out

    def last_active(self) -> Optional[Dict[str, float]]:
        """The last coordinate teleported to, even across a disconnect."""
        if self._last is None:
            return None
        return {"lat": self._last.latitude, "lng": self._last.longitude}

    def reapply(self) -> Dict[str, Any]:
        """Re-teleport the last override (used after a reconnect)."""
        if self._last is None:
            return {"ok": False, "error": "Nothing to reapply.", "hint": ""}
        return self.teleport(self._last.latitude, self._last.longitude)

    def _teardown(self) -> None:
        if self._override is not None:
            self._override.__exit__(None, None, None)
        self._override = None

    # --- override actions ---------------------------------------------------

    def default_location(self) -> Dict[str, float]:
        """The coordinate the map should center on at startup."""
        return {"lat": self._default.latitude, "lng": self._default.longitude}

    def teleport(self, lat: Any, lng: Any) -> Dict[str, Any]:
        """Validate a coordinate and drive the held override.

        Returns {ok: True, lat, lng} on success, or {ok: False, error, hint} so
        the front-end can show the same plain-language hint the CLI shows.
        """
        try:
            coord = parse_coordinate(f"{lat}, {lng}")
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "hint": ""}

        if self._override is None:
            return {"ok": False, "error": "No active session.", "hint": ""}

        try:
            self._override.teleport(coord)
        except SkyWalkerError as exc:
            return {"ok": False, "error": str(exc), "hint": exc.hint}

        self._active = coord
        self._last = coord
        return {"ok": True, "lat": coord.latitude, "lng": coord.longitude}

    def clear(self) -> Dict[str, Any]:
        """Release the override; the device returns to its real GPS."""
        if self._override is None:
            return {"ok": False, "error": "No active session.", "hint": ""}
        try:
            self._override.clear()
        except SkyWalkerError as exc:
            return {"ok": False, "error": str(exc), "hint": exc.hint}
        self._active = None
        return {"ok": True}

    def status(self) -> Dict[str, Any]:
        """Current state for the status bar: device, iOS, and the live override."""
        connected = self._override is not None
        return {
            "device": self._device.udid if self._device else None,
            "ios": self._device.ios_version if self._device else None,
            "connected": connected,
            "override": (
                {"lat": self._active.latitude, "lng": self._active.longitude}
                if (connected and self._active is not None)
                else None
            ),
        }


# --- default (real) collaborators -------------------------------------------

def _default_selector(udid: Optional[str]) -> Device:
    from sky_walker.device import select_device

    return select_device(udid)


def _default_lister() -> List[Device]:
    from sky_walker.device import list_devices

    return list_devices()


def _default_override(device: Device):
    from sky_walker.location import LocationOverride

    return LocationOverride(device)
