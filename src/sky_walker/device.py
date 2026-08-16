"""Device selection and the supported-iOS-band rule.

This module is a thin, pymobiledevice3-free facade: the actual USB/lockdown
calls live in backend.py (isolated per docs/adr/0001). Keeping the version
rule here — and pure — makes it unit-testable without a device.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from sky_walker.config import MIN_SUPPORTED_IOS, UNSUPPORTED_BAND


def _parse_version(text: str) -> Tuple[int, ...]:
    parts = []
    for chunk in text.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            break
    return tuple(parts) or (0,)


@dataclass(frozen=True)
class Device:
    udid: str
    ios_version: str

    def check_supported(self) -> Tuple[bool, str]:
        """Enforce docs/adr/0001: iOS >= 17.4, but reject the 17.0–17.3.1 band.

        Returns (ok, reason). `reason` is human-readable in both cases.
        """
        v = _parse_version(self.ios_version)
        low, high = UNSUPPORTED_BAND
        if low <= v <= high:
            return (
                False,
                f"iOS {self.ios_version} is in the unsupported 17.0–17.3.1 band "
                f"(needs admin tunneld + drivers we don't ship — see docs/adr/0001).",
            )
        if v < MIN_SUPPORTED_IOS:
            # Pre-17 would actually work via the classic path, but this tool is
            # scoped to the 17.4+ userspace tunnel only. Say so plainly.
            return (
                False,
                f"iOS {self.ios_version} is below the supported 17.4+ range "
                f"(this tool only implements the userspace-tunnel path).",
            )
        return True, f"iOS {self.ios_version} is supported"


def select_device(udid: Optional[str] = None) -> Device:
    """Return the one device to act on.

    Delegates discovery to backend.find_device, which raises NoDeviceError /
    MultipleDevicesError / NotPairedError with actionable hints.
    """
    from sky_walker import backend

    return backend.find_device(udid)
