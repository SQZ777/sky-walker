"""Bluetooth SIG Location and Speed wire-contract tests."""

from sky_walker.config import Coordinate


def test_static_coordinate_encodes_as_position_ok_location_and_speed_value():
    from sky_walker.ble_lns.codec import encode_location_and_speed

    # Bluetooth SIG GSS: flags are little-endian; bit 2 means Location Present,
    # bits 7-8 value 1 mean Position OK. Latitude/longitude are signed 1e-7
    # degree integers, also little-endian.
    assert encode_location_and_speed(Coordinate(1.0, -1.0)) == bytes.fromhex(
        "84 00 80 96 98 00 80 69 67 ff"
    )
