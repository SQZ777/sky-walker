"""Route Playback sequencing — the pure, device-free seam (ticket 01).

`route_points` turns an ordered list of Waypoints plus a Movement Speed into the
stream of Coordinates the device should occupy over time: it expands the
Waypoints into out-and-back Round Trips (A->B->C->B->A), interpolates intermediate
points so successive points are one tick apart at the given speed, lands exactly
on each Waypoint, and repeats for the requested number of Round Trips (or forever
when loops is None).

It imports nothing device-related and never sleeps, so the whole movement model
is unit-testable by asserting the emitted sequence. The driver (a background
thread) is the only part that adds real time and a device.
"""

from __future__ import annotations

import math
import threading
from typing import Callable, Iterable, Iterator, List, NamedTuple, Optional, Sequence

from sky_walker.config import Coordinate


class Step(NamedTuple):
    """One tick of Route Playback: where to be, and progress metadata.

    trip is 1-based; total is the loop count (None when infinite); leg is a
    human label like "A→B" (None for the very first point, which just sits on
    the start Waypoint).
    """

    coord: Coordinate
    trip: int
    total: Optional[int]
    leg: Optional[str]

_EARTH_RADIUS_M = 6_371_000.0


def _wrap_longitude(lng: float) -> float:
    """Fold a longitude back into [-180, 180) across the antimeridian."""
    return (lng + 180.0) % 360.0 - 180.0


def step_by(coord: Coordinate, north: float, east: float, meters: float) -> Coordinate:
    """Advance `coord` by `meters` of ground along the heading (north, east).

    (north, east) is a direction vector of any magnitude: its components are
    normalized, so a diagonal heading (e.g. north=1, east=1) still covers
    `meters`, not meters*√2. A zero heading — or zero distance — means "stay put"
    and returns `coord` unchanged. Latitude is clamped to [-90, 90]; longitude
    wraps across the antimeridian into [-180, 180). A local equirectangular step
    is exact enough at the few-metres-per-tick scale of Joystick movement.
    """
    norm = math.hypot(north, east)
    if norm == 0.0 or meters == 0.0:
        return coord
    north_m = meters * north / norm
    east_m = meters * east / norm

    new_lat = coord.latitude + math.degrees(north_m / _EARTH_RADIUS_M)
    new_lat = max(-90.0, min(90.0, new_lat))

    cos_lat = math.cos(math.radians(coord.latitude))
    if abs(cos_lat) < 1e-12:
        new_lng = coord.longitude  # longitude is degenerate at a pole
    else:
        dlng = math.degrees(east_m / (_EARTH_RADIUS_M * cos_lat))
        new_lng = _wrap_longitude(coord.longitude + dlng)
    return Coordinate(new_lat, new_lng)


def _haversine_m(a: Coordinate, b: Coordinate) -> float:
    lat1, lon1, lat2, lon2 = map(
        math.radians, (a.latitude, a.longitude, b.latitude, b.longitude)
    )
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _leg(start: Coordinate, end: Coordinate, step_m: float) -> Iterator[Coordinate]:
    """Yield points from just after `start` up to and INCLUDING `end`.

    The final point is `end` itself (not an interpolated near-miss) so Waypoints
    are always hit exactly.
    """
    distance = _haversine_m(start, end)
    if distance == 0:
        yield end
        return
    steps = max(1, math.ceil(distance / step_m))
    for i in range(1, steps + 1):
        if i == steps:
            yield end
        else:
            f = i / steps
            yield Coordinate(
                start.latitude + (end.latitude - start.latitude) * f,
                start.longitude + (end.longitude - start.longitude) * f,
            )


def route_stream(
    waypoints: Sequence[Coordinate],
    speed_kmh: float,
    hz: float = 1.0,
    loops: Optional[int] = 1,
) -> Iterator[Step]:
    """Yield the Step stream (coord + progress) for Route Playback.

    waypoints: 2 or 3 ordered points.
    speed_kmh: ground speed between Waypoints.
    hz:        updates per second (spacing = speed per tick).
    loops:     number of Round Trips, or None for infinite.

    Validation is eager (raises at call time, not on first iteration) so a
    caller starting a driver thread gets bad input reported synchronously.
    """
    if len(waypoints) < 2:
        raise ValueError("route needs at least two waypoints")
    if speed_kmh <= 0:
        raise ValueError("speed must be positive")
    if hz <= 0:
        raise ValueError("update rate must be positive")
    return _emit(list(waypoints), speed_kmh, hz, loops)


def route_points(
    waypoints: Sequence[Coordinate],
    speed_kmh: float,
    hz: float = 1.0,
    loops: Optional[int] = 1,
) -> Iterator[Coordinate]:
    """The bare Coordinate stream — route_stream without the progress metadata."""
    return (step.coord for step in route_stream(waypoints, speed_kmh, hz, loops))


def _emit(
    waypoints: List[Coordinate], speed_kmh: float, hz: float, loops: Optional[int]
) -> Iterator[Step]:
    step_m = speed_kmh * 1000.0 / 3600.0 / hz
    n = len(waypoints)
    # Waypoint visit order for one Round Trip: out then back (0..n-1, n-2..0)
    visit_order = list(range(n)) + list(range(n - 2, -1, -1))
    labels = [chr(ord("A") + i) for i in range(n)]

    yield Step(waypoints[0], 1, loops, None)  # start sits on the first Waypoint

    trip = 1
    while loops is None or trip <= loops:
        for i in range(len(visit_order) - 1):
            a, b = visit_order[i], visit_order[i + 1]
            leg = f"{labels[a]}→{labels[b]}"
            for point in _leg(waypoints[a], waypoints[b], step_m):
                yield Step(point, trip, loops, leg)
        trip += 1


class _DriverThread:
    """Shared lifecycle for the background driver threads (RoutePlayer, Walker).

    Owns the stop Event, the thread handle, and the injected waiter; subclasses
    add their own state and implement `_drive`. `_spawn` (re)starts the thread;
    `stop()` is prompt — it interrupts the inter-tick wait — and is safe to call
    from inside the sink (it won't try to join its own thread).
    """

    def __init__(self, *, waiter: Optional[Callable[[float], bool]] = None) -> None:
        # waiter(timeout) -> stop_requested. Defaults to the stop Event's wait
        # (an interruptible sleep); tests inject their own to run without a clock.
        self._waiter = waiter
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _spawn(self, target: Callable[[], None], name: str) -> None:
        self.stop()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=target, name=name, daemon=True)
        self._thread.start()

    def _drive(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        # Self-stop (called from inside the sink): just signal; the loop exits on
        # its own. Only an external caller joins and clears the handle.
        if t is not None and t is not threading.current_thread():
            if t.is_alive():
                t.join(timeout=2.0)
            self._thread = None

    @property
    def running(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()


class RoutePlayer(_DriverThread):
    """Plays an item stream against a sink on a background thread.

    The stream is any iterable (Route Playback passes a route_stream of Steps).
    sink is called once per tick with the current item (it drives the held
    Session); on_progress fires per tick with (index, item); on_finish fires
    when a bounded stream completes (never on stop). All the movement/sequencing
    logic lives in route_stream; this wrapper only adds real time and a thread.
    """

    def __init__(
        self,
        sink: Callable[[object], None],
        *,
        hz: float = 1.0,
        on_progress: Optional[Callable[[int, object], None]] = None,
        on_finish: Optional[Callable[[], None]] = None,
        waiter: Optional[Callable[[float], bool]] = None,
    ) -> None:
        super().__init__(waiter=waiter)
        self._sink = sink
        self._hz = hz
        self._on_progress = on_progress or (lambda i, item: None)
        self._on_finish = on_finish or (lambda: None)

    def start(self, items: Iterable[object]) -> None:
        item_iter = iter(items)
        self._spawn(lambda: self._drive(item_iter), "sky-walker-route")

    def _drive(self, items: Iterator[object]) -> None:
        wait = self._waiter or self._stop.wait
        for i, item in enumerate(items):
            if self._stop.is_set():
                return
            self._sink(item)
            self._on_progress(i, item)
            if wait(1.0 / self._hz):
                return
        self._on_finish()


class Walker(_DriverThread):
    """Drives a device along a live, mutable Heading on a background thread.

    Unlike RoutePlayer — which plays a fixed Step stream — the Walker generates
    its own point each tick from the *current* Heading and Movement Speed via
    step_by, so both direction (set_heading) and speed (set_speed) can change
    mid-run without restarting the thread. A zero Heading holds position: the
    sink is not called, so the device stays exactly where it is. All the movement
    math lives in step_by; this wrapper only adds a clock and a thread.
    """

    def __init__(
        self,
        sink: Callable[[Coordinate], None],
        origin: Coordinate,
        *,
        hz: float = 5.0,
        speed_kmh: float = 0.0,
        waiter: Optional[Callable[[float], bool]] = None,
    ) -> None:
        super().__init__(waiter=waiter)
        self._sink = sink
        self._pos = origin
        self._hz = hz
        self._speed_kmh = speed_kmh
        self._heading = (0.0, 0.0)  # (north, east); zero means hold position

    def set_heading(self, north: float, east: float) -> None:
        """Change the live Heading; takes effect on the next tick."""
        self._heading = (north, east)

    def set_speed(self, speed_kmh: float) -> None:
        """Change the live Movement Speed; takes effect on the next tick."""
        self._speed_kmh = speed_kmh

    def start(self) -> None:
        self._spawn(self._drive, "sky-walker-joystick")

    def _drive(self) -> None:
        wait = self._waiter or self._stop.wait
        while not self._stop.is_set():
            north, east = self._heading
            if north != 0.0 or east != 0.0:
                meters = self._speed_kmh * 1000.0 / 3600.0 / self._hz
                self._pos = step_by(self._pos, north, east, meters)
                self._sink(self._pos)
            if wait(1.0 / self._hz):
                return
