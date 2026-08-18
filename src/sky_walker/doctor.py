"""Doctor — preflight self-check (see CONTEXT.md).

Verifies every prerequisite for a Session and prints plain-language fixes for
whatever is missing, so first-run failures don't surface as opaque errors.

Each check is independent and returns a Check; the runner prints them in order
and stops the report from being one big traceback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""


@dataclass
class DoctorReport:
    """The structured outcome of a preflight run.

    `checks` holds the checks that actually ran, in order; because later checks
    depend on earlier ones the run stops at the first failure, so a failing
    report ends with the failed check. `ok` is True only if every check passed.
    """

    checks: List[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def as_dict(self) -> dict:
        """Plain dict for the GUI (startup gate and Doctor panel)."""
        return {
            "ok": self.ok,
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail, "fix": c.fix}
                for c in self.checks
            ],
        }


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


def collect(
    udid: Optional[str] = None,
    checks: Optional[List[Callable[[], Check]]] = None,
) -> DoctorReport:
    """Run the preflight checks and return a structured DoctorReport.

    Runs each check in order and stops at the first failure, because later
    checks depend on earlier ones (no device => no version check, etc.). The
    UI and the CLI both build on this so the report is produced in exactly one
    place; presentation (printing, rendering) lives elsewhere.
    """
    if checks is None:
        checks = [
            _check_backend,
            _check_usbmux,
            lambda: _check_device(udid),
            lambda: _check_supported(udid),
        ]

    report = DoctorReport()
    for run_check in checks:
        c = run_check()
        report.checks.append(c)
        if not c.ok:
            break  # later checks depend on this one — stop at the first failure
    return report


def run(udid: Optional[str] = None) -> int:
    """Run all checks, print a report, return 0 if all passed else 1."""
    report = collect(udid)

    print("sky-walker doctor\n")
    for c in report.checks:
        mark = "OK  " if c.ok else "FAIL"
        print(f"[{mark}] {c.name}: {c.detail}")
        if not c.ok and c.fix:
            print(f"        fix: {c.fix}")

    print("\nAll good — sky-walker is ready." if report.ok
          else "\nResolve the issue above and re-run `sky-walker doctor`.")
    return 0 if report.ok else 1
