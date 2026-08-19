"""Bluetooth SIG Location and Speed characteristic encoding."""

from __future__ import annotations

import struct

from sky_walker.config import Coordinate


_LOCATION_PRESENT = 1 << 2
_POSITION_OK = 1 << 7
_DEGREES_SCALE = 10_000_000


def encode_location_and_speed(coordinate: Coordinate) -> bytes:
    """Encode a static WGS-84 position for characteristic UUID 0x2A67."""

    flags = _LOCATION_PRESENT | _POSITION_OK
    latitude = round(coordinate.latitude * _DEGREES_SCALE)
    longitude = round(coordinate.longitude * _DEGREES_SCALE)
    return struct.pack("<Hii", flags, latitude, longitude)
