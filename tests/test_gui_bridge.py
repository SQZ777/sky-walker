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


def make_bridge(*, device=None, override=None, preflight=None, devices=None,
                select_error=None):
    device = device or Device("ABC123", "17.4")
    override = override if override is not None else FakeOverride()

    def selector(udid):
        if select_error is not None:
            raise select_error
        return device

    return Bridge(
        DEFAULT_LOCATION,
        preflight=preflight or (lambda u: DoctorReport([Check("x", True, "ok")])),
        device_lister=lambda: devices if devices is not None else [device],
        device_selector=selector,
        override_factory=lambda d: override,
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
