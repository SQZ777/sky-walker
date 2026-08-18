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
from sky_walker.gui.paths import PathStore, default_paths_file
from sky_walker.gui.route import Step, route_stream

_MIN_WAYPOINTS = 2
_MAX_WAYPOINTS = 3


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
        player_factory: Optional[Callable[..., Any]] = None,
        walker_factory: Optional[Callable[..., Any]] = None,
        path_store: Optional[Any] = None,
    ) -> None:
        self._default = default_location
        self._udid = udid

        self._preflight = preflight or (lambda u: doctor.collect(u))
        self._list = device_lister or _default_lister
        self._select = device_selector or _default_selector
        self._make_override = override_factory or _default_override
        self._on_device_change = on_device_change or (lambda udid: None)
        self._make_player = player_factory or _default_player
        self._make_walker = walker_factory or _default_walker
        self._paths = path_store or PathStore(default_paths_file())

        self._device: Optional[Device] = None
        self._override = None          # the entered LocationOverride, or None
        self._active: Optional[Coordinate] = None   # currently LIVE override, or None
        self._last: Optional[Coordinate] = None     # last coord, kept for reapply

        self._player = None                          # RoutePlayer while a route runs
        self._route_pos: Optional[Coordinate] = None # current simulated position
        self._route_progress: Optional[Dict[str, Any]] = None  # trip/total/leg

        self._walker = None                          # Walker while Joystick mode is on
        self._joystick_pos: Optional[Coordinate] = None  # current joystick position

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
        return _coord_dict(self._last) if self._last is not None else None

    def reapply(self) -> Dict[str, Any]:
        """Re-teleport the last override (used after a reconnect)."""
        if self._last is None:
            return {"ok": False, "error": "Nothing to reapply.", "hint": ""}
        return self.teleport(self._last.latitude, self._last.longitude)

    def _teardown(self) -> None:
        if self._player is not None:
            self._player.stop()
        self._player = None
        self._route_pos = None
        self._route_progress = None
        self._stop_walker()
        if self._override is not None:
            self._override.__exit__(None, None, None)
        self._override = None

    # --- override actions ---------------------------------------------------

    def default_location(self) -> Dict[str, float]:
        """The coordinate the map should center on at startup."""
        return _coord_dict(self._default)

    def validate_coordinate(self, lat: Any, lng: Any) -> Dict[str, Any]:
        """Validate a coordinate WITHOUT teleporting (the coord-box Enter path).

        Reuses config.parse_coordinate so the map-move validation is the same
        rule as an actual teleport — no second, looser parser in the front-end.
        """
        try:
            coord = parse_coordinate(f"{lat}, {lng}")
        except ValueError as exc:
            return _err(exc)
        return {"ok": True, **_coord_dict(coord)}

    def teleport(self, lat: Any, lng: Any) -> Dict[str, Any]:
        """Validate a coordinate and drive the held override.

        Returns {ok: True, lat, lng} on success, or {ok: False, error, hint} so
        the front-end can show the same plain-language hint the CLI shows.
        """
        try:
            coord = parse_coordinate(f"{lat}, {lng}")
        except ValueError as exc:
            return _err(exc)

        if self._override is None:
            return _fail("No active session.")
        if self._is_playing():
            return _fail("Stop the route before teleporting.")
        if self._is_walking():
            return _fail("Leave the joystick before teleporting.")

        try:
            self._override.teleport(coord)
        except SkyWalkerError as exc:
            return _err(exc)

        self._active = coord
        self._last = coord
        return {"ok": True, **_coord_dict(coord)}

    def clear(self) -> Dict[str, Any]:
        """Release the override; the device returns to its real GPS.

        Also stops any running route — Clear is the one control that always
        returns the device to a clean state.
        """
        if self._override is None:
            return _fail("No active session.")
        if self._player is not None:
            self._player.stop()
            self._route_pos = None
            self._route_progress = None
        self._stop_walker()
        try:
            self._override.clear()
        except SkyWalkerError as exc:
            return _err(exc)
        self._active = None
        return {"ok": True}

    # --- Route Playback (tickets 02, 03) ------------------------------------

    def start_route(
        self, waypoints: Any, speed_kmh: Any, loops: Any = 1
    ) -> Dict[str, Any]:
        """Begin Route Playback over the held Session.

        waypoints: list of {lat, lng}; speed_kmh: number > 0; loops: int >= 1
        or None for infinite. Validates before moving so bad input is reported
        rather than crashing the driver thread.
        """
        if self._override is None:
            return _fail("No active session.")
        if self._is_walking():
            return _fail("Leave the joystick before starting a route.")
        try:
            points = [parse_coordinate(f"{w['lat']}, {w['lng']}") for w in waypoints]
        except (ValueError, TypeError, KeyError) as exc:
            return _err(exc) if isinstance(exc, ValueError) else _fail("Bad waypoint.")
        if not _MIN_WAYPOINTS <= len(points) <= _MAX_WAYPOINTS:
            return _fail(f"A route takes {_MIN_WAYPOINTS}–{_MAX_WAYPOINTS} waypoints.")
        speed = _positive_speed(speed_kmh)
        if speed is None:
            return _fail("Speed must be a positive number.")
        try:
            loops_val = None if loops is None else int(loops)
        except (TypeError, ValueError):
            return _fail("Round trips must be a whole number.")
        if loops_val is not None and loops_val < 1:
            return _fail("Round trips must be at least 1.")

        try:
            stream = route_stream(points, speed, _ROUTE_HZ, loops_val)
        except (ValueError, SkyWalkerError) as exc:
            return _err(exc)

        self._player = self._make_player(
            sink=self._drive_point,
            on_progress=self._on_route_progress,
            on_finish=self._on_route_finish,
        )
        self._route_pos = points[0]
        self._route_progress = {"trip": 1, "total": loops_val, "leg": None}
        self._player.start(stream)
        return {"ok": True}

    def stop_route(self) -> Dict[str, Any]:
        """Stop Route Playback; the device stays at the current position."""
        if self._player is not None:
            self._player.stop()
        return {"ok": True}

    # --- Joystick (joystick-mode ticket 03) ---------------------------------

    def start_joystick(
        self, speed_kmh: Any, cand_lat: Any = None, cand_lng: Any = None
    ) -> Dict[str, Any]:
        """Enter Joystick mode: hold at the start point, ready for arrow keys.

        Spins the Walker with a zero Heading (so the device stays put) starting
        from the current override position; if there is none yet, from the map's
        candidate point (cand_lat/cand_lng), else the Default Location. Arrow
        keys then drive it live via set_heading. Refused while a route plays —
        the two modes are exclusive.
        """
        if self._override is None:
            return _fail("No active session.")
        if self._is_playing():
            return _fail("Stop the route before using the joystick.")
        speed = _positive_speed(speed_kmh)
        if speed is None:
            return _fail("Speed must be a positive number.")
        origin = self._active
        if origin is None and cand_lat is not None and cand_lng is not None:
            try:
                origin = parse_coordinate(f"{cand_lat}, {cand_lng}")
            except ValueError:
                origin = None
        if origin is None:
            origin = self._default
        self._stop_walker()
        self._walker = self._make_walker(
            sink=self._drive_joystick_point,
            origin=origin,
            speed_kmh=speed,
            hz=_JOYSTICK_HZ,
        )
        self._joystick_pos = origin
        self._walker.start()
        return {"ok": True, **_coord_dict(origin)}

    def set_heading(self, north: Any, east: Any) -> Dict[str, Any]:
        """Set the live Heading (north/east vector); zero holds position."""
        if self._walker is None:
            return _fail("Joystick is not active.")
        try:
            n, e = float(north), float(east)
        except (TypeError, ValueError):
            return _fail("Heading must be numbers.")
        self._walker.set_heading(n, e)
        return {"ok": True}

    def set_joystick_speed(self, speed_kmh: Any) -> Dict[str, Any]:
        """Change the live Movement Speed while walking (takes effect next tick)."""
        if self._walker is None:
            return _fail("Joystick is not active.")
        speed = _positive_speed(speed_kmh)
        if speed is None:
            return _fail("Speed must be a positive number.")
        self._walker.set_speed(speed)
        return {"ok": True}

    def stop_joystick(self) -> Dict[str, Any]:
        """Leave Joystick mode; the device holds its current position."""
        self._stop_walker()
        return {"ok": True}

    def _stop_walker(self) -> None:
        if self._walker is not None:
            self._walker.stop()
        self._walker = None
        self._joystick_pos = None

    def _drive_joystick_point(self, coord: "Coordinate") -> None:
        """Walker sink, called each tick: move the device and track position."""
        self._apply(coord)
        self._joystick_pos = coord

    def _is_walking(self) -> bool:
        return self._walker is not None and self._walker.running

    # --- Saved Paths (ticket 04) --------------------------------------------

    def save_path(self, name: Any, waypoints: Any) -> Dict[str, Any]:
        """Persist the current Waypoints under a name."""
        name = (name or "").strip()
        if not name:
            return _fail("Name the path first.")
        try:
            pts = [{"lat": float(w["lat"]), "lng": float(w["lng"])} for w in waypoints]
        except (TypeError, KeyError, ValueError):
            return _fail("Bad waypoints.")
        if not _MIN_WAYPOINTS <= len(pts) <= _MAX_WAYPOINTS:
            return _fail(f"A saved path takes {_MIN_WAYPOINTS}–{_MAX_WAYPOINTS} waypoints.")
        self._paths.save(name, pts)
        return {"ok": True, "paths": self._paths.names()}

    def list_paths(self) -> List[str]:
        """Names of all Saved Paths."""
        return self._paths.names()

    def load_path(self, name: Any) -> Dict[str, Any]:
        """Return a Saved Path's Waypoints so the map can be repopulated."""
        waypoints = self._paths.load(name)
        if waypoints is None:
            return _fail("No such saved path.")
        return {"ok": True, "waypoints": waypoints}

    def delete_path(self, name: Any) -> Dict[str, Any]:
        """Remove a Saved Path."""
        self._paths.delete(name)
        return {"ok": True, "paths": self._paths.names()}

    def _apply(self, coord: "Coordinate") -> None:
        """Move the device to `coord` and record it as the active/last override."""
        self._override.teleport(coord)
        self._active = coord
        self._last = coord

    def _drive_point(self, step: "Step") -> None:
        """Sink the driver calls each tick: move the device, track position."""
        self._apply(step.coord)
        self._route_pos = step.coord

    def _on_route_progress(self, index: int, step: "Step") -> None:
        self._route_pos = step.coord
        self._route_progress = {"trip": step.trip, "total": step.total, "leg": step.leg}

    def _on_route_finish(self) -> None:
        # A finished route holds its final point (no revert); nothing to do.
        pass

    def _is_playing(self) -> bool:
        return self._player is not None and self._player.running

    def status(self) -> Dict[str, Any]:
        """Current state for the status bar: device, iOS, override, route."""
        connected = self._override is not None
        playing = self._is_playing()
        walking = self._is_walking()
        return {
            "device": self._device.udid if self._device else None,
            "ios": self._device.ios_version if self._device else None,
            "connected": connected,
            "override": (
                _coord_dict(self._active)
                if (connected and self._active is not None)
                else None
            ),
            "playing": playing,
            "route_position": (
                _coord_dict(self._route_pos)
                if (playing and self._route_pos is not None)
                else None
            ),
            "progress": self._route_progress if playing else None,
            "walking": walking,
            "joystick_position": (
                _coord_dict(self._joystick_pos)
                if (walking and self._joystick_pos is not None)
                else None
            ),
        }


# --- small result shapers ---------------------------------------------------

def _coord_dict(coord: Coordinate) -> Dict[str, float]:
    return {"lat": coord.latitude, "lng": coord.longitude}


def _err(exc: Exception) -> Dict[str, Any]:
    """Failure dict from an exception, reusing its .hint when it has one."""
    return {"ok": False, "error": str(exc), "hint": getattr(exc, "hint", "")}


def _fail(message: str) -> Dict[str, Any]:
    return {"ok": False, "error": message, "hint": ""}


def _positive_speed(value: Any) -> Optional[float]:
    """Coerce a Movement Speed to a positive float, or None if invalid."""
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return None
    return speed if speed > 0 else None


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


_ROUTE_HZ = 1.0  # Route Playback update rate (see spec: fixed 1 Hz)
_JOYSTICK_HZ = 5.0  # Joystick update rate (see joystick-mode spec: ~5 Hz)


def _default_player(sink, on_progress, on_finish):
    from sky_walker.gui.route import RoutePlayer

    return RoutePlayer(
        sink, hz=_ROUTE_HZ, on_progress=on_progress, on_finish=on_finish
    )


def _default_walker(sink, origin, speed_kmh, hz):
    from sky_walker.gui.route import Walker

    return Walker(sink, origin, hz=hz, speed_kmh=speed_kmh)
