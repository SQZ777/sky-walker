"""Tests for the RoutePlayer driver (ticket 02).

The player is a thin thread over route_points. An injected `waiter` replaces the
inter-tick sleep so the driver runs with no wall-clock; we join the (now
instantaneous) thread to await completion.
"""

from sky_walker.config import Coordinate
from sky_walker.gui.route import RoutePlayer, route_points

A = Coordinate(0.0, 0.0)
B = Coordinate(0.0, 0.01)
C = Coordinate(0.01, 0.01)
FAST = 1_000_000.0

NO_WAIT = lambda _timeout: False  # never sleeps, never signals stop


def test_plays_the_whole_route_then_finishes():
    seen, finished = [], []
    player = RoutePlayer(seen.append, on_finish=lambda: finished.append(True), waiter=NO_WAIT)
    player.start(route_points([A, B, C], FAST, loops=1))
    player._thread.join(2.0)
    assert seen[0] == A and seen[-1] == A       # started and returned to start
    assert B in seen and C in seen
    assert finished == [True]
    assert player.running is False


def test_stop_from_within_sink_halts_promptly():
    seen = []
    player = RoutePlayer(lambda c: (seen.append(c), player.stop()), hz=1000.0)
    player.start(route_points([A, B, C], FAST, loops=None))  # infinite unless stopped
    player._thread.join(2.0)
    assert seen == [A]                          # stopped after the first point
    assert player.running is False


def test_on_progress_fires_per_tick():
    idxs = []
    player = RoutePlayer(lambda c: None, on_progress=lambda i, c: idxs.append(i), waiter=NO_WAIT)
    player.start(route_points([A, B], FAST, loops=1))
    player._thread.join(2.0)
    assert idxs == list(range(len(idxs)))       # contiguous indices from 0
    assert len(idxs) >= 3                        # A, B, A
