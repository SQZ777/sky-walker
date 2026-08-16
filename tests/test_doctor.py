"""Tests for the structured Doctor result (ticket 01).

Pure: uses fake check callables, so no device or pymobiledevice3 is needed.
Run with: python -m pytest tests/test_doctor.py
"""

from sky_walker import doctor
from sky_walker.doctor import Check


def _ok(name):
    return lambda: Check(name, True, "fine")


def _fail(name):
    return lambda: Check(name, False, "broken", fix=f"fix {name}")


def test_collect_all_ok():
    report = doctor.collect(checks=[_ok("a"), _ok("b")])
    assert report.ok is True
    assert [c.name for c in report.checks] == ["a", "b"]


def test_collect_stops_at_first_failure():
    # 'c' must never run, because 'b' failed and later checks depend on earlier.
    ran = []

    def tracked(name, ok):
        def go():
            ran.append(name)
            return Check(name, ok, "d", fix="f")
        return go

    report = doctor.collect(checks=[tracked("a", True), tracked("b", False), tracked("c", True)])
    assert report.ok is False
    assert ran == ["a", "b"]
    assert [c.name for c in report.checks] == ["a", "b"]
    assert report.checks[-1].ok is False


def test_collect_default_checks_shape():
    # The real default checks are wired and callable (they will FAIL fast with
    # no device, but collect must still return a well-formed report).
    report = doctor.collect(udid=None)
    assert isinstance(report.ok, bool)
    assert len(report.checks) >= 1
    assert all(isinstance(c, Check) for c in report.checks)
