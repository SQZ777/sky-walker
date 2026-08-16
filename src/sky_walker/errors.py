"""Typed errors, so the CLI can turn each into a plain-language message.

Every error carries a `.hint` — the human-readable fix shown to the user.
"""

from __future__ import annotations


class SkyWalkerError(Exception):
    """Base class. `hint` is the actionable next step for the user."""

    hint: str = ""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        if hint:
            self.hint = hint


class NoDeviceError(SkyWalkerError):
    hint = "Plug in the iPhone over USB and unlock it. Check `sky-walker doctor`."


class MultipleDevicesError(SkyWalkerError):
    hint = "More than one device is connected. Pass --udid <UDID> to pick one."


class NotPairedError(SkyWalkerError):
    hint = "Unlock the iPhone and tap 'Trust This Computer', then retry."


class DeveloperModeError(SkyWalkerError):
    hint = (
        "Enable Developer Mode: Settings > Privacy & Security > Developer Mode, "
        "then reboot the iPhone."
    )


class UnsupportedIOSError(SkyWalkerError):
    """iOS version falls outside the supported band (see docs/adr/0001)."""


class TunnelError(SkyWalkerError):
    hint = (
        "Could not establish the USB tunnel. Ensure Apple's USB driver is "
        "installed (iTunes / Apple Devices) and run `sky-walker doctor`."
    )


class BackendUnavailableError(SkyWalkerError):
    hint = "Install the backend: pip install -U pymobiledevice3"
