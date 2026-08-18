"""Tests for the GUI bridge seam (tickets 02-07).

The bridge is the Python API exposed to the webview's JavaScript. It is the
testable seam: every device-touching collaborator is injectable, so we exercise
the whole lifecycle (preflight, device pick, begin, teleport, clear, status,
shutdown) with fakes — no pywebview and no device.
"""

from sky_walker.config import DEFAULT_LOCATION, Coordinate
from sky_walker.device import Device
from sky_walker.doctor import Check, DoctorReport
from sky_walker.errors import NoDeviceError, TunnelError
from sky_walker.gui.bridge import Bridge
from sky_walker.gui.route import Step


class FakeOverride:
    def __init__(self, fail_with=None):
        self.teleports = []
        self.cleared = 0
        self.entered = False
        self.exited = False
        self._fail_with = fail_with

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *a):
        self.exited = True

    def teleport(self, coord):
        if self._fail_with is not None:
            raise self._fail_with
        self.teleports.append(coord)

    def clear(self):
        self.cleared += 1


class FakePlayer:
    def __init__(self, sink, on_progress, on_finish):
        self.sink = sink
        self.on_progress = on_progress
        self.on_finish = on_finish
        self.items = None         # the Step stream the bridge built
        self.started = False
        self.stopped = 0
        self.running = False

    def start(self, items):
        self.items = items
        self.started = True
        self.running = True

    def stop(self):
        self.stopped += 1
        self.running = False


class FakeWalker:
    def __init__(self, sink, origin, speed_kmh, hz):
        self.sink = sink
        self.origin = origin
        self.speed_kmh = speed_kmh
        self.hz = hz
        self.heading = None
        self.started = False
        self.stopped = 0
        self.running = False

    def set_heading(self, north, east):
        self.heading = (north, east)

    def set_speed(self, speed_kmh):
        self.speed_kmh = speed_kmh

    def start(self):
        self.started = True
        self.running = True

    def stop(self):
        self.stopped += 1
        self.running = False


# players and walkers created by the bridge under test are captured here
_players = []
_walkers = []


class FakeStore:
    def __init__(self):
        self.data = {}

    def names(self):
        return sorted(self.data)

    def save(self, name, waypoints):
        self.data[name] = waypoints

    def load(self, name):
        return self.data.get(name)

    def delete(self, name):
        self.data.pop(name, None)


def make_bridge(*, device=None, override=None, preflight=None, devices=None,
                select_error=None, path_store=None):
    device = device or Device("ABC123", "17.4")
    override = override if override is not None else FakeOverride()
    _players.clear()
    _walkers.clear()

    def selector(udid):
        if select_error is not None:
            raise select_error
        return device

    def player_factory(sink, on_progress, on_finish):
        p = FakePlayer(sink, on_progress, on_finish)
        _players.append(p)
        return p

    def walker_factory(sink, origin, speed_kmh, hz):
        w = FakeWalker(sink, origin, speed_kmh, hz)
        _walkers.append(w)
        return w

    return Bridge(
        DEFAULT_LOCATION,
        preflight=preflight or (lambda u: DoctorReport([Check("x", True, "ok")])),
        device_lister=lambda: devices if devices is not None else [device],
        device_selector=selector,
        override_factory=lambda d: override,
        player_factory=player_factory,
        walker_factory=walker_factory,
        path_store=path_store or FakeStore(),
    ), override, device


def started(**kw):
    bridge, override, device = make_bridge(**kw)
    bridge.begin()
    return bridge, override, device


# --- default location & preflight -------------------------------------------

def test_default_location():
    bridge, _, _ = make_bridge()
    assert bridge.default_location() == {
        "lat": DEFAULT_LOCATION.latitude,
        "lng": DEFAULT_LOCATION.longitude,
    }


def test_preflight_returns_report_dict():
    report = DoctorReport([Check("backend", True, "ok"), Check("device", False, "none", "plug in")])
    bridge, _, _ = make_bridge(preflight=lambda u: report)
    pf = bridge.preflight()
    assert pf["ok"] is False
    assert pf["checks"][1] == {"name": "device", "ok": False, "detail": "none", "fix": "plug in"}


# --- begin / session lifecycle ----------------------------------------------

def test_begin_opens_session():
    bridge, override, device = make_bridge()
    res = bridge.begin()
    assert res["ok"] is True
    assert res["device"] == device.udid
    assert override.entered is True


def test_begin_rejects_unsupported_ios_without_opening():
    bridge, override, _ = make_bridge(device=Device("OLD", "17.2"))
    res = bridge.begin()
    assert res["ok"] is False
    assert override.entered is False


def test_begin_surfaces_no_device_hint():
    bridge, _, _ = make_bridge(select_error=NoDeviceError("no iPhone"))
    res = bridge.begin()
    assert res["ok"] is False
    assert res["hint"] == NoDeviceError.hint


def test_begin_is_repeatable_closing_the_previous_session():
    first = FakeOverride()
    bridge, _, _ = make_bridge(override=first)
    bridge.begin()
    # re-begin should tear the first session down (reconnect path, ticket 08)
    bridge.begin()
    assert first.exited is True


def test_shutdown_reverts():
    bridge, override, _ = started()
    bridge.shutdown()
    assert override.exited is True


# --- teleport / clear -------------------------------------------------------

def test_teleport_valid_drives_override():
    bridge, override, _ = started()
    result = bridge.teleport(25.0, 121.0)
    assert result["ok"] is True
    assert override.teleports == [Coordinate(25.0, 121.0)]


def test_teleport_before_begin_is_rejected():
    bridge, override, _ = make_bridge()
    result = bridge.teleport(25.0, 121.0)
    assert result["ok"] is False
    assert override.teleports == []


def test_teleport_out_of_range_rejected_without_driving_device():
    bridge, override, _ = started()
    result = bridge.teleport(200.0, 0.0)
    assert result["ok"] is False
    assert override.teleports == []


def test_teleport_surfaces_backend_hint():
    bridge, _, _ = started(override=FakeOverride(fail_with=TunnelError("boom")))
    result = bridge.teleport(25.0, 121.0)
    assert result["ok"] is False
    assert result["hint"] == TunnelError.hint


def test_clear_drives_override():
    bridge, override, _ = started()
    assert bridge.clear()["ok"] is True
    assert override.cleared == 1


# --- status -----------------------------------------------------------------

def test_status_reports_device_and_no_override_initially():
    bridge, _, device = started()
    s = bridge.status()
    assert s["device"] == device.udid
    assert s["ios"] == device.ios_version
    assert s["connected"] is True
    assert s["override"] is None


def test_status_tracks_active_override_across_teleport_and_clear():
    bridge, _, _ = started()
    bridge.teleport(10.0, 20.0)
    assert bridge.status()["override"] == {"lat": 10.0, "lng": 20.0}
    bridge.clear()
    assert bridge.status()["override"] is None


def test_status_disconnected_before_begin():
    bridge, _, _ = make_bridge()
    assert bridge.status()["connected"] is False


# --- device picker (ticket 07) ----------------------------------------------

def test_list_devices():
    devs = [Device("A", "17.4"), Device("B", "18.0")]
    bridge, _, _ = make_bridge(devices=devs)
    assert bridge.list_devices() == [
        {"udid": "A", "ios": "17.4"},
        {"udid": "B", "ios": "18.0"},
    ]


# --- hot-plug reconnect (ticket 08) -----------------------------------------

def test_on_lost_marks_disconnected_but_remembers_last_override():
    bridge, override, _ = started()
    bridge.teleport(10.0, 20.0)
    bridge.on_lost()
    s = bridge.status()
    assert s["connected"] is False
    assert override.exited is True
    # the coordinate survives the disconnect so it can be offered for reapply
    assert bridge.last_active() == {"lat": 10.0, "lng": 20.0}


def test_reapply_reteleports_last_after_reconnect():
    override = FakeOverride()
    bridge, _, _ = make_bridge(override=override)
    bridge.begin()
    bridge.teleport(10.0, 20.0)
    bridge.on_lost()
    # reconnect + reapply
    bridge.begin()
    res = bridge.reapply()
    assert res["ok"] is True
    assert override.teleports[-1] == Coordinate(10.0, 20.0)


def test_reapply_with_nothing_to_reapply():
    bridge, _, _ = started()
    assert bridge.reapply()["ok"] is False


# --- coordinate validation without teleporting (ticket 03) ------------------

def test_validate_coordinate_ok_does_not_touch_device():
    bridge, override, _ = started()
    res = bridge.validate_coordinate(25.0, 121.0)
    assert res == {"ok": True, "lat": 25.0, "lng": 121.0}
    assert override.teleports == []  # validation must NOT drive the device


def test_validate_coordinate_enforces_range():
    bridge, _, _ = started()
    res = bridge.validate_coordinate(999.0, 0.0)
    assert res["ok"] is False
    assert res["error"]


# --- Route Playback (ticket 02) ---------------------------------------------

def _wps(*pairs):
    return [{"lat": la, "lng": ln} for la, ln in pairs]


def test_start_route_requires_session():
    bridge, _, _ = make_bridge()  # not begun
    assert bridge.start_route(_wps((0, 0), (0, 1)), 50, 1)["ok"] is False


def test_start_route_needs_two_waypoints():
    bridge, _, _ = started()
    assert bridge.start_route(_wps((0, 0)), 50, 1)["ok"] is False
    assert not _players  # no player created for invalid input


def test_start_route_rejects_nonpositive_speed():
    bridge, _, _ = started()
    assert bridge.start_route(_wps((0, 0), (0, 1)), 0, 1)["ok"] is False


def test_start_route_rejects_more_than_three_waypoints():
    bridge, _, _ = started()
    res = bridge.start_route(_wps((0, 0), (0, 1), (1, 1), (1, 0)), 50, 1)
    assert res["ok"] is False
    assert not _players  # never started


def test_start_route_rejects_non_integer_loops():
    bridge, _, _ = started()
    res = bridge.start_route(_wps((0, 0), (0, 1)), 50, "lots")
    assert res["ok"] is False        # clean failure, not an exception
    assert not _players


def test_start_route_starts_player_and_marks_playing():
    bridge, _, _ = started()
    res = bridge.start_route(_wps((1, 2), (3, 4), (5, 6)), 50, 3)
    assert res["ok"] is True
    player = _players[-1]
    first = next(iter(player.items))            # the stream starts on waypoint A
    assert first.coord == Coordinate(1, 2)
    assert first.total == 3                     # loop count carried into the stream
    assert bridge.status()["playing"] is True


def test_infinite_loops_passed_as_none():
    bridge, _, _ = started()
    bridge.start_route(_wps((0, 0), (0, 1)), 50, None)
    assert next(iter(_players[-1].items)).total is None


def test_teleport_refused_while_playing():
    bridge, override, _ = started()
    bridge.start_route(_wps((0, 0), (0, 1)), 50, 1)
    res = bridge.teleport(10, 20)
    assert res["ok"] is False
    assert Coordinate(10, 20) not in override.teleports


def test_clear_stops_running_route():
    bridge, _, _ = started()
    bridge.start_route(_wps((0, 0), (0, 1)), 50, 1)
    bridge.clear()
    assert _players[-1].stopped >= 1
    assert bridge.status()["playing"] is False


def test_stop_route_stops_player():
    bridge, _, _ = started()
    bridge.start_route(_wps((0, 0), (0, 1)), 50, 1)
    bridge.stop_route()
    assert _players[-1].stopped >= 1


def test_shutdown_stops_running_route():
    bridge, _, _ = started()
    bridge.start_route(_wps((0, 0), (0, 1)), 50, 1)
    bridge.shutdown()
    assert _players[-1].stopped >= 1


def test_driver_sink_moves_device_and_updates_position():
    bridge, override, _ = started()
    bridge.start_route(_wps((0, 0), (0, 1)), 50, 1)
    player = _players[-1]
    step = Step(Coordinate(7.0, 8.0), trip=2, total=5, leg="B→C")
    player.sink(step)                     # simulate one driver tick
    player.on_progress(0, step)
    assert override.teleports[-1] == Coordinate(7.0, 8.0)
    s = bridge.status()
    assert s["route_position"] == {"lat": 7.0, "lng": 8.0}
    assert s["progress"] == {"trip": 2, "total": 5, "leg": "B→C"}


# --- Saved Paths (ticket 04) ------------------------------------------------

def test_save_then_list_and_load_path():
    bridge, _, _ = started()
    res = bridge.save_path("home", _wps((1, 2), (3, 4)))
    assert res["ok"] is True and res["paths"] == ["home"]
    assert bridge.list_paths() == ["home"]
    loaded = bridge.load_path("home")
    assert loaded["ok"] is True
    assert loaded["waypoints"] == [{"lat": 1.0, "lng": 2.0}, {"lat": 3.0, "lng": 4.0}]


def test_save_path_rejects_blank_name():
    bridge, _, _ = started()
    assert bridge.save_path("  ", _wps((1, 2), (3, 4)))["ok"] is False


def test_save_path_needs_two_waypoints():
    bridge, _, _ = started()
    assert bridge.save_path("x", _wps((1, 2)))["ok"] is False


def test_load_missing_path_fails():
    bridge, _, _ = started()
    assert bridge.load_path("ghost")["ok"] is False


def test_delete_path():
    bridge, _, _ = started()
    bridge.save_path("home", _wps((1, 2), (3, 4)))
    res = bridge.delete_path("home")
    assert res["ok"] is True and res["paths"] == []


# --- Joystick (joystick-mode ticket 03) -------------------------------------

def test_start_joystick_requires_session():
    bridge, _, _ = make_bridge()  # not begun
    assert bridge.start_joystick(50)["ok"] is False
    assert not _walkers


def test_start_joystick_rejects_nonpositive_speed():
    bridge, _, _ = started()
    assert bridge.start_joystick(0)["ok"] is False
    assert not _walkers


def test_start_joystick_starts_walker_from_current_position():
    bridge, _, _ = started()
    bridge.teleport(10.0, 20.0)
    res = bridge.start_joystick(50)
    assert res["ok"] is True
    walker = _walkers[-1]
    assert walker.started is True
    assert walker.origin == Coordinate(10.0, 20.0)  # started where the device is
    assert walker.speed_kmh == 50.0
    s = bridge.status()
    assert s["walking"] is True
    assert s["joystick_position"] == {"lat": 10.0, "lng": 20.0}


def test_start_joystick_falls_back_to_default_when_no_active():
    bridge, _, _ = started()  # begun but never teleported, no candidate given
    bridge.start_joystick(50)
    assert _walkers[-1].origin == DEFAULT_LOCATION


def test_start_joystick_uses_candidate_when_no_active():
    bridge, _, _ = started()  # begun, never teleported -> no active override
    bridge.start_joystick(50, 10.0, 20.0)  # map candidate passed in
    assert _walkers[-1].origin == Coordinate(10.0, 20.0)


def test_start_joystick_prefers_active_over_candidate():
    bridge, _, _ = started()
    bridge.teleport(1.0, 2.0)
    bridge.start_joystick(50, 10.0, 20.0)
    assert _walkers[-1].origin == Coordinate(1.0, 2.0)  # active wins over candidate


def test_start_joystick_refused_while_route_playing():
    bridge, _, _ = started()
    bridge.start_route(_wps((0, 0), (0, 1)), 50, 1)
    res = bridge.start_joystick(50)
    assert res["ok"] is False
    assert not _walkers  # never started


def test_start_route_refused_while_walking():
    bridge, _, _ = started()
    bridge.start_joystick(50)
    res = bridge.start_route(_wps((0, 0), (0, 1)), 50, 1)
    assert res["ok"] is False
    assert not _players  # route never started


def test_set_heading_updates_walker():
    bridge, _, _ = started()
    bridge.start_joystick(50)
    assert bridge.set_heading(1.0, 0.0)["ok"] is True
    assert _walkers[-1].heading == (1.0, 0.0)


def test_set_heading_without_joystick_fails():
    bridge, _, _ = started()
    assert bridge.set_heading(1.0, 0.0)["ok"] is False


def test_set_joystick_speed_updates_walker_live():
    bridge, _, _ = started()
    bridge.start_joystick(50)
    assert bridge.set_joystick_speed(80)["ok"] is True
    assert _walkers[-1].speed_kmh == 80.0


def test_walker_sink_moves_device_and_tracks_position():
    bridge, override, _ = started()
    bridge.start_joystick(50)
    walker = _walkers[-1]
    walker.sink(Coordinate(7.0, 8.0))  # simulate one Walker tick
    assert override.teleports[-1] == Coordinate(7.0, 8.0)
    s = bridge.status()
    assert s["joystick_position"] == {"lat": 7.0, "lng": 8.0}
    assert s["override"] == {"lat": 7.0, "lng": 8.0}


def test_teleport_refused_while_walking():
    bridge, override, _ = started()
    bridge.start_joystick(50)
    res = bridge.teleport(30.0, 40.0)
    assert res["ok"] is False
    assert Coordinate(30.0, 40.0) not in override.teleports


def test_stop_joystick_stops_walker():
    bridge, _, _ = started()
    bridge.start_joystick(50)
    assert bridge.stop_joystick()["ok"] is True
    assert _walkers[-1].stopped >= 1
    assert bridge.status()["walking"] is False


def test_clear_stops_walker():
    bridge, _, _ = started()
    bridge.start_joystick(50)
    bridge.clear()
    assert _walkers[-1].stopped >= 1
    assert bridge.status()["walking"] is False


def test_shutdown_stops_walker():
    bridge, _, _ = started()
    bridge.start_joystick(50)
    bridge.shutdown()
    assert _walkers[-1].stopped >= 1
