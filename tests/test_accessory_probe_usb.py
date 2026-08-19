"""Windows Apple USB evidence boundary tests."""

from __future__ import annotations

import subprocess

import pytest

from sky_walker.accessory_probe import usb


def test_usb_detector_rejects_negative_device_count(monkeypatch):
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="-1\n", stderr=""
    )
    monkeypatch.setattr(usb.subprocess, "run", lambda *args, **kwargs: completed)

    assert usb.detect_apple_usb() == usb.AppleUsbEvidence(
        status="error", device_count=0
    )


@pytest.mark.parametrize(
    "returncode,stdout,expected",
    [
        (0, "0\n", usb.AppleUsbEvidence(status="absent", device_count=0)),
        (0, "2\n", usb.AppleUsbEvidence(status="present", device_count=2)),
        (1, "", usb.AppleUsbEvidence(status="error", device_count=0)),
        (0, "not-a-number", usb.AppleUsbEvidence(status="error", device_count=0)),
    ],
)
def test_usb_detector_classifies_powershell_result(
    monkeypatch, returncode, stdout, expected
):
    completed = subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=""
    )
    monkeypatch.setattr(usb.subprocess, "run", lambda *args, **kwargs: completed)

    assert usb.detect_apple_usb() == expected


@pytest.mark.parametrize("error", [OSError(), subprocess.TimeoutExpired("pwsh", 10)])
def test_usb_detector_reports_process_failure_without_identifiers(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(usb.subprocess, "run", fail)

    evidence = usb.detect_apple_usb()
    assert evidence == usb.AppleUsbEvidence(status="error", device_count=0)
    assert not hasattr(evidence, "device_ids")
