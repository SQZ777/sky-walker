"""Tests for the Walker joystick driver (ticket 02).

The Walker is a thin thread over step_by with a *mutable* heading — direction
and speed can change mid-run. An injected `waiter` that signals stop after N
calls replaces the inter-tick sleep, so the driver runs with no wall-clock and a
bounded number of ticks (unlike a route, a Walker has no natural end).
"""

import math

import pytest

from sky_walker.config import Coordinate
from sky_walker.gui.route import Walker

ORIGIN = Coordinate(0.0, 0.0)


def _haversine_m(p, q):
    lat1, lon1, lat2, lon2 = map(
        math.radians, (p.latitude, p.longitude, q.latitude, q.longitude)
    )
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371000.0 * math.asin(math.sqrt(h))


def stop_after(n):
    """A waiter that never sleeps and signals stop on its n-th call."""
    calls = {"n": 0}

    def w(_timeout):
        calls["n"] += 1
        return calls["n"] >= n

    return w


def _join(w):
    if w._thread is not None:
        w._thread.join(2.0)


# --- movement ---------------------------------------------------------------

def test_advances_north_at_speed_each_tick():
    seen = []
    # 36 km/h = 10 m/s; at 1 Hz that is 10 m per tick.
    w = Walker(seen.append, ORIGIN, hz=1.0, speed_kmh=36.0, waiter=stop_after(3))
    w.set_heading(1.0, 0.0)
    w.start()
    _join(w)
    assert len(seen) == 3
    # marches steadily north, ~10 m per tick
    assert seen[0].latitude < seen[1].latitude < seen[2].latitude
    assert _haversine_m(ORIGIN, seen[0]) == pytest.approx(10.0, rel=1e-2)


def test_zero_heading_holds_position_no_sink():
    seen = []
    w = Walker(seen.append, ORIGIN, hz=1.0, speed_kmh=36.0, waiter=stop_after(3))
    # heading defaults to zero — the device must stay put
    w.start()
    _join(w)
    assert seen == []


def test_set_heading_mid_run_changes_direction():
    seen = []

    def sink(c):
        seen.append(c)
        if len(seen) == 2:
            w.set_heading(0.0, 1.0)  # switch north -> east

    w = Walker(sink, ORIGIN, hz=1.0, speed_kmh=36.0, waiter=stop_after(4))
    w.set_heading(1.0, 0.0)
    w.start()
    _join(w)
    assert len(seen) == 4
    # first two went north (longitude ~0), last two went east (longitude grows)
    assert seen[1].longitude == pytest.approx(0.0, abs=1e-9)
    assert seen[2].longitude > seen[1].longitude
    assert seen[3].longitude > seen[2].longitude


def test_set_speed_mid_run_changes_step_distance():
    seen = []

    def sink(c):
        seen.append(c)
        if len(seen) == 2:
            w.set_speed(72.0)  # double the speed

    w = Walker(sink, ORIGIN, hz=1.0, speed_kmh=36.0, waiter=stop_after(4))
    w.set_heading(1.0, 0.0)
    w.start()
    _join(w)
    slow_gap = _haversine_m(seen[0], seen[1])
    fast_gap = _haversine_m(seen[2], seen[3])
    assert fast_gap == pytest.approx(2 * slow_gap, rel=1e-2)


# --- stop / lifecycle -------------------------------------------------------

def test_stop_from_within_sink_halts_promptly():
    seen = []
    w = Walker(lambda c: (seen.append(c), w.stop()), ORIGIN, hz=1000.0, speed_kmh=36.0)
    w.set_heading(1.0, 0.0)
    w.start()
    _join(w)
    assert len(seen) == 1
    assert w.running is False


def test_running_is_false_after_stop():
    w = Walker(lambda c: None, ORIGIN, hz=1000.0, speed_kmh=36.0, waiter=stop_after(1))
    w.set_heading(1.0, 0.0)
    w.start()
    _join(w)
    assert w.running is False
