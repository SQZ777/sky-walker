"""Tests for the pure Route Playback sequencing seam (ticket 01).

route_points expands Waypoints into out-and-back Round Trips and interpolates by
Movement Speed. It is pure — no device, no real clock — so we assert the exact
Coordinate stream it emits.
"""

import math

import pytest

from sky_walker.config import Coordinate
from sky_walker.gui.route import route_points, route_stream

A = Coordinate(0.0, 0.0)
B = Coordinate(0.0, 0.01)
C = Coordinate(0.01, 0.01)

# A huge speed makes each leg a single step, so the stream is exactly the nodes.
FAST = 1_000_000.0


def seq(*args, **kw):
    return list(route_points(*args, **kw))


# --- round-trip order -------------------------------------------------------

def test_two_point_round_trip_nodes():
    assert seq([A, B], FAST, hz=1.0, loops=1) == [A, B, A]


def test_three_point_round_trip_nodes():
    assert seq([A, B, C], FAST, hz=1.0, loops=1) == [A, B, C, B, A]


def test_multiple_round_trips_do_not_double_emit_the_turn():
    # Two loops: A B C B A  then  B C B A  (A at the boundary emitted once).
    assert seq([A, B, C], FAST, hz=1.0, loops=2) == [A, B, C, B, A, B, C, B, A]


def test_starts_on_first_waypoint():
    assert seq([A, B, C], FAST, loops=1)[0] == A


# --- infinite ---------------------------------------------------------------

def test_infinite_stream_is_unbounded():
    gen = route_points([A, B, C], FAST, hz=1.0, loops=None)
    prefix = [next(gen) for _ in range(20)]
    assert len(prefix) == 20
    assert prefix[0] == A


# --- interpolation spacing --------------------------------------------------

def _haversine_m(p, q):
    lat1, lon1, lat2, lon2 = map(math.radians, (p.latitude, p.longitude, q.latitude, q.longitude))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(h))


def test_spacing_matches_speed_over_update_rate():
    # 3600 km/h at 1 Hz => 1000 m per tick. Leg due north so steps are even.
    north = Coordinate(0.05, 0.0)  # ~5.5 km up
    pts = seq([A, north], 3600.0, hz=1.0, loops=1)
    # first point is A (start); gaps between successive points up to the turn
    gaps = [_haversine_m(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    forward = gaps[: len(gaps) // 2]  # the A->north half
    # a leg is split into ceil(d/step) EQUAL sub-steps, so every gap is <= step
    # and they are all the same size (even spacing).
    assert all(g <= 1000.0 + 1e-6 for g in forward)
    assert all(g == pytest.approx(forward[0], rel=1e-6) for g in forward)


def test_waypoints_are_hit_exactly():
    pts = seq([A, B, C], 50.0, hz=1.0, loops=1)
    assert A in pts and B in pts and C in pts
    assert pts[0] == A and pts[-1] == A


# --- validation -------------------------------------------------------------

def test_needs_at_least_two_waypoints():
    with pytest.raises(ValueError):
        seq([A], FAST, loops=1)


def test_speed_must_be_positive():
    with pytest.raises(ValueError):
        seq([A, B], 0.0, loops=1)


# --- progress metadata (ticket 03) ------------------------------------------

def test_stream_labels_legs_and_trips():
    steps = list(route_stream([A, B, C], FAST, hz=1.0, loops=2))
    # first item is the start on A with no leg
    assert steps[0].coord == A and steps[0].leg is None and steps[0].trip == 1
    legs = [s.leg for s in steps[1:]]
    # one round trip of legs, then the second round trip repeats them
    assert legs == ["A→B", "B→C", "C→B", "B→A", "A→B", "B→C", "C→B", "B→A"]
    assert [s.trip for s in steps[1:]] == [1, 1, 1, 1, 2, 2, 2, 2]
    assert all(s.total == 2 for s in steps)


def test_stream_total_is_none_when_infinite():
    gen = route_stream([A, B], FAST, hz=1.0, loops=None)
    first = next(gen)
    assert first.total is None
