"""Constants and coordinate parsing.

Kept implementation-free of pymobiledevice3 so it can be imported anywhere,
including by the CLI's --help path, without a device attached.
"""

from __future__ import annotations

from typing import NamedTuple


class Coordinate(NamedTuple):
    latitude: float
    longitude: float

    def __str__(self) -> str:
        return f"{self.latitude}, {self.longitude}"


# The Default Location the interactive prompt pre-fills (see CONTEXT.md).
DEFAULT_LOCATION = Coordinate(25.073944586589487, 121.51104972333346)

# Supported iOS band. See docs/adr/0001: only the 17.4+ userspace-tunnel path
# is supported; 17.0–17.3.1 is deliberately out of scope.
MIN_SUPPORTED_IOS = (17, 4)
UNSUPPORTED_BAND = ((17, 0), (17, 3, 1))  # inclusive range that we refuse


def parse_coordinate(text: str) -> Coordinate:
    """Parse "lat, lng" (or "lat lng") into a Coordinate.

    Raises ValueError with a human-readable message on bad input.
    """
    cleaned = text.replace(",", " ").split()
    if len(cleaned) != 2:
        raise ValueError(
            f"expected two numbers 'lat, lng', got {text!r}"
        )
    try:
        lat, lng = float(cleaned[0]), float(cleaned[1])
    except ValueError:
        raise ValueError(f"coordinates must be numbers, got {text!r}") from None
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"latitude {lat} out of range [-90, 90]")
    if not -180.0 <= lng <= 180.0:
        raise ValueError(f"longitude {lng} out of range [-180, 180]")
    return Coordinate(lat, lng)
