"""Tests for the pure logic that needs no device or pymobiledevice3.

Run with: python -m pytest   (or just: python tests/test_pure.py)
"""

import pytest

from sky_walker.config import DEFAULT_LOCATION, Coordinate, parse_coordinate
from sky_walker.device import Device


# --- parse_coordinate -------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("25.03, 121.56", Coordinate(25.03, 121.56)),
    ("25.03 121.56", Coordinate(25.03, 121.56)),
    ("  -33.8688 , 151.2093 ", Coordinate(-33.8688, 151.2093)),
    (str(DEFAULT_LOCATION), DEFAULT_LOCATION),
])
def test_parse_coordinate_ok(text, expected):
    assert parse_coordinate(text) == expected


@pytest.mark.parametrize("bad", [
    "", "25.03", "a, b", "1, 2, 3", "200, 0", "0, 200",
])
def test_parse_coordinate_rejects(bad):
    with pytest.raises(ValueError):
        parse_coordinate(bad)


# --- supported-band rule (docs/adr/0001) ------------------------------------

@pytest.mark.parametrize("version,ok", [
    ("26.4", True),     # our target device
    ("18.0", True),
    ("17.4", True),     # lower bound of support
    ("17.5.1", True),
    ("17.3.1", False),  # top of the excluded band
    ("17.2", False),    # inside the excluded band
    ("17.0", False),    # bottom of the excluded band
    ("16.5", False),    # below the tool's scope
])
def test_supported_band(version, ok):
    supported, reason = Device("UDID", version).check_supported()
    assert supported is ok
    assert reason  # always human-readable


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
