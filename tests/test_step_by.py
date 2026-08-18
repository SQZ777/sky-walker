"""Tests for the pure joystick movement primitive `step_by` (ticket 01).

step_by advances a Coordinate by a distance along a heading vector. It is pure —
no device, no clock — so we assert the coordinate it returns, checking the ground
distance with the same haversine the route math uses.
"""

import math

import pytest

from sky_walker.config import Coordinate
from sky_walker.gui.route import step_by

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


# --- direction & distance ---------------------------------------------------

def test_due_north_only_increases_latitude():
    out = step_by(ORIGIN, north=1.0, east=0.0, meters=1000.0)
    assert out.latitude > 0.0
    assert out.longitude == pytest.approx(0.0, abs=1e-9)
    assert _haversine_m(ORIGIN, out) == pytest.approx(1000.0, rel=1e-3)


def test_due_east_only_increases_longitude():
    out = step_by(ORIGIN, north=0.0, east=1.0, meters=1000.0)
    assert out.longitude > 0.0
    assert out.latitude == pytest.approx(0.0, abs=1e-9)
    assert _haversine_m(ORIGIN, out) == pytest.approx(1000.0, rel=1e-3)


def test_south_and_west_are_negative():
    south = step_by(ORIGIN, north=-1.0, east=0.0, meters=1000.0)
    west = step_by(ORIGIN, north=0.0, east=-1.0, meters=1000.0)
    assert south.latitude < 0.0
    assert west.longitude < 0.0


def test_diagonal_covers_meters_not_root_two_times():
    # A 45° heading must still travel `meters` of ground, not meters*sqrt(2).
    out = step_by(ORIGIN, north=1.0, east=1.0, meters=1000.0)
    assert _haversine_m(ORIGIN, out) == pytest.approx(1000.0, rel=1e-3)


def test_heading_magnitude_does_not_matter():
    # (5, 0) and (1, 0) are the same direction, so they land on the same point.
    big = step_by(ORIGIN, north=5.0, east=0.0, meters=1000.0)
    unit = step_by(ORIGIN, north=1.0, east=0.0, meters=1000.0)
    assert big == unit


# --- degenerate & bounds ----------------------------------------------------

def test_zero_heading_stays_put():
    assert step_by(ORIGIN, north=0.0, east=0.0, meters=1000.0) == ORIGIN


def test_zero_distance_stays_put():
    assert step_by(ORIGIN, north=1.0, east=1.0, meters=0.0) == ORIGIN


def test_latitude_clamps_at_the_pole():
    # A huge northward step from high latitude must not exceed +90.
    out = step_by(Coordinate(89.0, 0.0), north=1.0, east=0.0, meters=500_000.0)
    assert out.latitude == 90.0


def test_longitude_wraps_across_the_antimeridian():
    # Just east of +180 wraps to the negative side, staying within [-180, 180).
    out = step_by(Coordinate(0.0, 179.99), north=0.0, east=1.0, meters=5000.0)
    assert -180.0 <= out.longitude < 180.0
    assert out.longitude < 0.0  # wrapped past +180
