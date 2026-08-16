"""The one module that talks to pymobiledevice3 (docs/adr/0001).

Everything else codes against device.py / location.py; only this file imports
pymobiledevice3, so the rest of the app imports cleanly with no device attached.

pymobiledevice3 10.x is **async-first**: list_devices, lockdown creation, the
userspace tunnel, and the location service are all coroutines. The rest of Sky
Walker is synchronous (a REPL), so we own a single asyncio event loop on a
background thread and marshal coroutines onto it. A held override is just the
`UserspaceRsdTunnel` async context manager kept open on that loop across many
synchronous `set_location` calls — which is exactly the "one tunnel, re-teleport
repeatedly" model of ADR-0002.

API surface verified against pymobiledevice3 v10.7.4 (and its CLI source):
  - pymobiledevice3.usbmux.list_devices() -> [MuxDevice(serial, connection_type, ...)]
  - pymobiledevice3.lockdown.create_using_usbmux(serial=...).product_version
  - pymobiledevice3.remote.userspace_tunnel.UserspaceRsdTunnel  (async ctx mgr -> rsd)
  - pymobiledevice3.services.dvt.instruments.dvt_provider.DvtProvider(rsd)  (async ctx mgr)
  - pymobiledevice3.services.dvt.instruments.location_simulation.LocationSimulation(dvt)
        (async ctx mgr; .set(lat, lng) / .clear())

Why the DVT path and not the simpler services.simulate_location.DtSimulateLocation:
on iOS 17+ the bare `com.apple.dt.simulatelocation` lockdown service is no longer
published, so DtSimulateLocation fails with "No such service". Location on iOS 17+
is only reachable through the instruments DVT hub, which is exactly what the
`pymobiledevice3 developer dvt simulate-location` CLI uses. Verified on an
iPhone 15 Pro / iOS 26.4: DtSimulateLocation -> InvalidServiceError; DVT path works.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Optional

from sky_walker.config import Coordinate
from sky_walker.device import Device
from sky_walker.errors import (
    BackendUnavailableError,
    DeveloperModeError,
    MultipleDevicesError,
    NoDeviceError,
    NotPairedError,
    SkyWalkerError,
    TunnelError,
)


# --- async event loop on a background thread --------------------------------

class _AsyncRunner:
    """A private event loop running forever on a daemon thread.

    `run(coro)` submits a coroutine and blocks for its result, so synchronous
    callers can drive the async library. A single loop keeps the held tunnel's
    background tasks alive between calls.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="sky-walker-aio", daemon=True
        )
        self._thread.start()

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()


_runner: Optional[_AsyncRunner] = None


def _get_runner() -> _AsyncRunner:
    global _runner
    if _runner is None:
        _runner = _AsyncRunner()
    return _runner


# --- lazy pymobiledevice3 imports -------------------------------------------

class _Pmd:
    """Holds the pieces of pymobiledevice3 we use, imported once, lazily."""

    def __init__(self) -> None:
        try:
            from pymobiledevice3 import exceptions as exc
            from pymobiledevice3.lockdown import create_using_usbmux
            from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
            from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
            from pymobiledevice3.services.dvt.instruments.location_simulation import (
                LocationSimulation,
            )
            from pymobiledevice3.usbmux import list_devices
        except ImportError as e:
            raise BackendUnavailableError(f"pymobiledevice3 not importable: {e}") from e

        self.exc = exc
        self.create_using_usbmux = create_using_usbmux
        self.UserspaceRsdTunnel = UserspaceRsdTunnel
        self.DvtProvider = DvtProvider
        self.LocationSimulation = LocationSimulation
        self.list_devices = list_devices

    def error(self, name: str):
        """Fetch an exception class by name, falling back to the base class.

        Names drift slightly across patch releases, so resolve defensively.
        """
        base = getattr(self.exc, "PyMobileDevice3Exception", Exception)
        return getattr(self.exc, name, base)


_pmd: Optional[_Pmd] = None


def _pmd_mod() -> _Pmd:
    global _pmd
    if _pmd is None:
        _pmd = _Pmd()
    return _pmd


# --- public backend API -----------------------------------------------------

def usbmux_reachable() -> bool:
    """True if Apple's usbmux is answering (driver installed and running)."""
    pmd = _pmd_mod()
    try:
        _get_runner().run(pmd.list_devices())
        return True
    except Exception:
        # ConnectionRefusedError etc. => usbmux not present. Empty list is still
        # "reachable", so only an exception counts as unreachable.
        return False


def find_device(udid: Optional[str] = None) -> Device:
    """Select the target device and read its iOS version (no tunnel needed).

    Auto-selects the sole USB device; errors with the UDID list if several are
    attached; raises NoDeviceError if none. Reading product_version goes over
    plain lockdown, so this is cheap and works before any tunnel is built.
    """
    pmd = _pmd_mod()

    async def _find() -> Device:
        devices = await pmd.list_devices()
        usb = [d for d in devices if getattr(d, "connection_type", "USB") == "USB"]

        if udid:
            match = [d for d in usb if d.serial == udid]
            if not match:
                raise NoDeviceError(f"device {udid} is not connected over USB")
            chosen = match[0]
        elif not usb:
            raise NoDeviceError("no iPhone connected over USB")
        elif len(usb) > 1:
            serials = ", ".join(d.serial for d in usb)
            raise MultipleDevicesError(f"multiple devices connected: {serials}")
        else:
            chosen = usb[0]

        lockdown = await pmd.create_using_usbmux(
            serial=chosen.serial, autopair=True, connection_type="USB"
        )
        return Device(chosen.serial, lockdown.product_version)

    return _run_mapped(_find(), pmd, stage="find-device")


class LocationSession:
    """A held override: one userspace tunnel + the DVT location-simulation channel.

    On iOS 17+, location goes through the instruments DVT hub (see module
    docstring), so we keep three async context managers open on the background
    loop — the tunnel, the DvtProvider, and LocationSimulation — and re-issue
    `set` on the same live channel for each teleport (ADR-0002). `close` clears
    and unwinds all three in reverse order.
    """

    def __init__(self, runner: _AsyncRunner, pmd: _Pmd,
                 tunnel_cm, dvt_cm, loc_cm, loc) -> None:
        self._runner = runner
        self._pmd = pmd
        self._tunnel_cm = tunnel_cm  # UserspaceRsdTunnel (entered)
        self._dvt_cm = dvt_cm        # DvtProvider (entered)
        self._loc_cm = loc_cm        # LocationSimulation (entered)
        self._loc = loc              # the entered LocationSimulation handle

    @classmethod
    def open(cls, device: Device) -> "LocationSession":
        pmd = _pmd_mod()
        runner = _get_runner()

        async def _open_tunnel():
            tunnel_cm = pmd.UserspaceRsdTunnel(serial=device.udid, autopair=True)
            rsd = await tunnel_cm.__aenter__()
            return tunnel_cm, rsd

        tunnel_cm, rsd = _run_mapped(_open_tunnel(), pmd, runner, stage="open-tunnel")

        async def _open_service():
            dvt_cm = pmd.DvtProvider(rsd)
            dvt = await dvt_cm.__aenter__()
            loc_cm = pmd.LocationSimulation(dvt)
            loc = await loc_cm.__aenter__()
            return dvt_cm, loc_cm, loc

        try:
            dvt_cm, loc_cm, loc = _run_mapped(
                _open_service(), pmd, runner, stage="open-location-service")
        except Exception:
            # Don't leak the tunnel if the DVT service fails to open.
            try:
                runner.run(tunnel_cm.__aexit__(None, None, None))
            except Exception:
                pass
            raise

        return cls(runner, pmd, tunnel_cm, dvt_cm, loc_cm, loc)

    def set_location(self, coord: Coordinate) -> None:
        _run_mapped(self._loc.set(coord.latitude, coord.longitude),
                    self._pmd, self._runner, stage="set-location")

    def clear(self) -> None:
        _run_mapped(self._loc.clear(), self._pmd, self._runner, stage="clear-location")

    def close(self) -> None:
        async def _close():
            try:
                await self._loc.clear()
            except Exception:
                pass  # best-effort; unwinding the channel reverts anyway
            for cm in (self._loc_cm, self._dvt_cm, self._tunnel_cm):
                try:
                    await cm.__aexit__(None, None, None)
                except Exception:
                    pass

        try:
            self._runner.run(_close())
        except Exception:
            pass  # never raise from teardown


# --- exception mapping ------------------------------------------------------

def _run_mapped(coro, pmd: _Pmd, runner: Optional[_AsyncRunner] = None,
                stage: str = "operation"):
    """Run a coroutine, translating pymobiledevice3 errors into ours.

    `stage` names the step (find-device / open-tunnel / set-location) so an
    unmapped failure says where it happened instead of a bare message.
    """
    runner = runner or _get_runner()
    try:
        return runner.run(coro)
    except (NoDeviceError, MultipleDevicesError, SkyWalkerError):
        raise
    except pmd.error("NoDeviceConnectedError") as e:
        raise NoDeviceError(str(e)) from e
    except (pmd.error("NotPairedError"), pmd.error("NotTrustedError")) as e:
        raise NotPairedError(str(e)) from e
    except pmd.error("DeveloperModeIsNotEnabledError") as e:
        raise DeveloperModeError(str(e)) from e
    except pmd.error("UserspaceTunnelUnavailableError") as e:
        raise TunnelError(str(e)) from e
    except Exception as e:
        raise SkyWalkerError(
            f"pymobiledevice3 failed during {stage}: {type(e).__name__}: {e}"
        ) from e
