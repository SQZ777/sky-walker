"""Public command-surface tests for Accessory Probe."""

from __future__ import annotations

import json
import re
from pathlib import Path

from sky_walker.cli import main
from sky_walker.config import DEFAULT_LOCATION


FIXTURES = Path(__file__).parent / "fixtures" / "accessory_probe"


def test_probe_new_creates_versioned_manifest_and_prints_steps(tmp_path, capsys):
    exit_code = main([
        "probe",
        "new",
        "real-gps",
        "--ios-version",
        "26.4",
        "--probe-build",
        "1",
        "--output-dir",
        str(tmp_path),
    ])

    assert exit_code == 0
    manifests = list(tmp_path.glob("*.manifest.json"))
    assert len(manifests) == 1

    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert re.fullmatch(r"[A-Z2-9]{8}", manifest["session_id"])
    assert manifest["scenario"] == "real-gps"
    assert manifest["expected_location"] == {
        "latitude": DEFAULT_LOCATION.latitude,
        "longitude": DEFAULT_LOCATION.longitude,
        "horizontal_tolerance_m": 25.0,
    }
    assert manifest["timing"] == {
        "stabilization_seconds": 10,
        "maximum_capture_seconds": 120,
        "minimum_post_stabilization_callbacks": 10,
    }
    assert manifest["stimulus"]["primary"] == {
        "kind": "static",
        "latitude": DEFAULT_LOCATION.latitude,
        "longitude": DEFAULT_LOCATION.longitude,
    }
    assert manifest["stimulus"]["fallback"]["kind"] == "two-point-route"
    assert manifest["stimulus"]["fallback"]["update_frequency_hz"] == 1.0
    assert manifest["stimulus"]["fallback"]["movement_speed_kmh"] == 5.0
    assert len(manifest["stimulus"]["fallback"]["waypoints"]) == 2
    assert manifest["environment"]["ios_version"] == "26.4"
    assert manifest["environment"]["source_probe_build"] == "1"

    output = capsys.readouterr().out
    assert manifest["session_id"] in output
    assert "Source Probe" in output
    assert "120 seconds" in output


def test_probe_new_bluetooth_records_independent_usb_evidence(
    tmp_path, capsys, monkeypatch
):
    from sky_walker.accessory_probe import cli as probe_cli
    from sky_walker.accessory_probe.usb import AppleUsbEvidence

    monkeypatch.setattr(
        probe_cli,
        "detect_apple_usb",
        lambda: AppleUsbEvidence(status="absent", device_count=0),
    )

    exit_code = main([
        "probe",
        "new",
        "ianygo-bluetooth",
        "--ios-version",
        "26.4",
        "--probe-build",
        "1",
        "--location-product-version",
        "4.11.11",
        "--bluetooth-adapter",
        "Intel Wireless Bluetooth",
        "--confirm-usb-disconnected",
        "--output-dir",
        str(tmp_path),
    ])

    assert exit_code == 0
    manifest_path = next(tmp_path.glob("*.manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenario"] == "ianygo-bluetooth"
    assert manifest["environment"]["location_product_version"] == "4.11.11"
    assert manifest["environment"]["bluetooth_adapter"] == "Intel Wireless Bluetooth"
    assert manifest["connection_evidence"] == {
        "user_confirmed_usb_disconnected": True,
        "windows_apple_usb_status": "absent",
        "windows_apple_usb_device_count": 0,
    }
    assert "unplugged" in capsys.readouterr().out.lower()


def test_probe_new_bluetooth_requires_reproducibility_metadata(
    tmp_path, capsys, monkeypatch
):
    from sky_walker.accessory_probe import cli as probe_cli
    from sky_walker.accessory_probe.usb import AppleUsbEvidence

    monkeypatch.setattr(
        probe_cli,
        "detect_apple_usb",
        lambda: AppleUsbEvidence(status="absent", device_count=0),
    )

    exit_code = main([
        "probe",
        "new",
        "ianygo-bluetooth",
        "--ios-version",
        "26.4",
        "--probe-build",
        "1",
        "--output-dir",
        str(tmp_path),
    ])

    assert exit_code == 3
    assert list(tmp_path.glob("*.manifest.json")) == []
    error = capsys.readouterr().err
    assert "--location-product-version" in error
    assert "--bluetooth-adapter" in error
    assert "--confirm-usb-disconnected" in error


def test_probe_new_rejects_out_of_range_coordinate(tmp_path, capsys):
    exit_code = main([
        "probe",
        "new",
        "real-gps",
        "--ios-version",
        "26.4",
        "--probe-build",
        "1",
        "--latitude",
        "200",
        "--output-dir",
        str(tmp_path),
    ])

    assert exit_code == 3
    assert list(tmp_path.glob("*.manifest.json")) == []
    assert "latitude" in capsys.readouterr().err


def test_probe_validate_emits_machine_and_human_pass_result(capsys, monkeypatch):
    from sky_walker.accessory_probe import cli as probe_cli
    from sky_walker.accessory_probe.usb import AppleUsbEvidence

    monkeypatch.setattr(
        probe_cli,
        "detect_apple_usb",
        lambda: AppleUsbEvidence(status="absent", device_count=0),
    )
    exit_code = main([
        "probe",
        "validate",
        str(FIXTURES / "pass.manifest.json"),
        str(FIXTURES / "pass.jsonl"),
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result == {
        "schema_version": 1,
        "session_id": "ABCD2345",
        "scenario": "ianygo-bluetooth",
        "verdict": "pass",
        "reason_codes": ["accessory-attribution-confirmed"],
        "total_location_records": 10,
        "eligible_location_records": 10,
        "total_callback_count": 10,
        "eligible_callback_count": 10,
        "validation_apple_usb_status": "absent",
        "validation_apple_usb_device_count": 0,
    }
    assert "PASS" in captured.err
    assert "10 eligible callbacks" in captured.err


def test_probe_validate_uses_distinct_exit_statuses(tmp_path, capsys, monkeypatch):
    from sky_walker.accessory_probe import cli as probe_cli
    from sky_walker.accessory_probe.usb import AppleUsbEvidence

    monkeypatch.setattr(
        probe_cli,
        "detect_apple_usb",
        lambda: AppleUsbEvidence(status="absent", device_count=0),
    )
    manifest = FIXTURES / "pass.manifest.json"
    lines = (FIXTURES / "pass.jsonl").read_text(encoding="utf-8").splitlines()

    fail_path = tmp_path / "fail.jsonl"
    fail_path.write_text(
        "\n".join(line.replace(
            '"is_produced_by_accessory":true',
            '"is_produced_by_accessory":false',
        ) for line in lines) + "\n",
        encoding="utf-8",
    )
    assert main(["probe", "validate", str(manifest), str(fail_path)]) == 1
    capsys.readouterr()

    inconclusive_path = tmp_path / "inconclusive.jsonl"
    inconclusive_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    assert main(["probe", "validate", str(manifest), str(inconclusive_path)]) == 2
    capsys.readouterr()

    invalid_path = tmp_path / "invalid.jsonl"
    invalid_path.write_text("not-json\n", encoding="utf-8")
    assert main(["probe", "validate", str(manifest), str(invalid_path)]) == 3
    invalid_output = capsys.readouterr()
    assert json.loads(invalid_output.out)["verdict"] == "invalid"
    assert "INVALID" in invalid_output.err


def test_probe_validate_rechecks_apple_usb_at_validation_time(capsys, monkeypatch):
    from sky_walker.accessory_probe import cli as probe_cli
    from sky_walker.accessory_probe.usb import AppleUsbEvidence

    monkeypatch.setattr(
        probe_cli,
        "detect_apple_usb",
        lambda: AppleUsbEvidence(status="present", device_count=1),
    )

    exit_code = main([
        "probe",
        "validate",
        str(FIXTURES / "pass.manifest.json"),
        str(FIXTURES / "pass.jsonl"),
    ])

    assert exit_code == 2
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "inconclusive"
    assert result["reason_codes"] == ["apple-usb-present"]
    assert result["validation_apple_usb_status"] == "present"
