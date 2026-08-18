"""Privacy-preserving Windows evidence for physical Apple USB devices."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AppleUsbEvidence:
    status: str
    device_count: int


_COUNT_APPLE_USB = (
    "@(Get-CimInstance Win32_PnPEntity | "
    "Where-Object { $_.PNPDeviceID -like 'USB\\VID_05AC*' }).Count"
)


def detect_apple_usb() -> AppleUsbEvidence:
    """Report only presence and count; never retain PnP identifiers or UDIDs."""
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _COUNT_APPLE_USB,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return AppleUsbEvidence(status="error", device_count=0)

    if completed.returncode != 0:
        return AppleUsbEvidence(status="error", device_count=0)
    try:
        count = int(completed.stdout.strip())
    except ValueError:
        return AppleUsbEvidence(status="error", device_count=0)
    if count < 0:
        return AppleUsbEvidence(status="error", device_count=0)
    return AppleUsbEvidence(
        status="present" if count else "absent",
        device_count=count,
    )
