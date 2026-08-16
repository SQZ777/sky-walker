"""Doctor — preflight self-check (see CONTEXT.md).

Verifies every prerequisite for a Session and prints plain-language fixes for
whatever is missing, so first-run failures don't surface as opaque errors.

Each check is independent and returns a Check; the runner prints them in order
and stops the report from being one big traceback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""


def _check_backend() -> Check:
    """pymobiledevice3 importable, and new enough."""
    try:
        import pymobiledevice3  # noqa: F401
    except ImportError:
        return Check(
            "backend (pymobiledevice3)",
            False,
            "not installed",
            "pip install -U pymobiledevice3",
        )
    try:
        from importlib.metadata import version
        installed = version("pymobiledevice3")
    except Exception:
        installed = "unknown"
    return Check("backend (pymobiledevice3)", True, f"installed ({installed})")


def _check_usbmux() -> Check:
    """Apple's USB stack (usbmux) is reachable — needs iTunes / Apple Devices on Windows."""
    try:
        from sky_walker import backend
    except Exception as exc:  # pragma: no cover - defensive
        return Check("apple usb driver (usbmux)", False, str(exc))
    try:
        reachable = backend.usbmux_reachable()
    except Exception as exc:
        return Check(
            "apple usb driver (usbmux)",
            False,
            f"usbmux not reachable: {exc}",
            "Install Apple's USB driver (iTunes or the Apple Devices app on Windows).",
        )
    return Check("apple usb driver (usbmux)", reachable,
                 "reachable" if reachable else "not reachable",
                 "" if reachable else
                 "Install iTunes / Apple Devices so usbmux is running.")


def _check_device(udid: Optional[str]) -> Check:
    """Exactly one usable device (or the requested --udid) is present and paired."""
    from sky_walker import backend
    from sky_walker.errors import SkyWalkerError
    try:
        dev = backend.find_device(udid)
    except SkyWalkerError as exc:
        return Check("device", False, str(exc), exc.hint)
    return Check("device", True, f"{dev.udid} (iOS {dev.ios_version})")


def _check_supported(udid: Optional[str]) -> Check:
    """iOS version is inside the supported 17.4+ band (docs/adr/0001)."""
    from sky_walker import backend
    from sky_walker.errors import SkyWalkerError
    try:
        dev = backend.find_device(udid)
    except SkyWalkerError as exc:
        return Check("ios version supported", False, str(exc), exc.hint)
    supported, reason = dev.check_supported()
    return Check("ios version supported", supported, reason,
                 "" if supported else
                 "This iOS band is out of scope; see docs/adr/0001.")


def run(udid: Optional[str] = None) -> int:
    """Run all checks, print a report, return 0 if all passed else 1."""
    checks: List[Callable[[], Check]] = [
        _check_backend,
        _check_usbmux,
        lambda: _check_device(udid),
        lambda: _check_supported(udid),
    ]

    print("sky-walker doctor\n")
    all_ok = True
    for run_check in checks:
        c = run_check()
        mark = "OK  " if c.ok else "FAIL"
        print(f"[{mark}] {c.name}: {c.detail}")
        if not c.ok:
            all_ok = False
            if c.fix:
                print(f"        fix: {c.fix}")
            # Later checks depend on earlier ones — stop at the first failure.
            break

    print("\nAll good — sky-walker is ready." if all_ok
          else "\nResolve the issue above and re-run `sky-walker doctor`.")
    return 0 if all_ok else 1
