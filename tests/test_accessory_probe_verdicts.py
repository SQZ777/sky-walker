"""Probe Verdict behavior through the manifest-plus-JSONL seam."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sky_walker.accessory_probe.usb import AppleUsbEvidence
from sky_walker.accessory_probe.validator import validate_files as validate_artifacts


FIXTURES = Path(__file__).parent / "fixtures" / "accessory_probe"


def validate_files(manifest_path, jsonl_path):
    return validate_artifacts(
        manifest_path,
        jsonl_path,
        usb_detector=lambda: AppleUsbEvidence(status="absent", device_count=0),
    )


def _write_fixture(tmp_path, *, mutate_manifest=None, mutate_records=None):
    manifest = json.loads((FIXTURES / "pass.manifest.json").read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in (FIXTURES / "pass.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    if mutate_manifest is not None:
        mutate_manifest(manifest)
    if mutate_records is not None:
        mutate_records(records)
    manifest_path = tmp_path / "session.manifest.json"
    jsonl_path = tmp_path / "capture.jsonl"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    jsonl_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return manifest_path, jsonl_path


def test_complete_non_accessory_evidence_fails(tmp_path):
    def make_non_accessory(records):
        for record in records[1:]:
            record["is_produced_by_accessory"] = False

    manifest_path, jsonl_path = _write_fixture(
        tmp_path, mutate_records=make_non_accessory
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "fail"
    assert result.reason_codes == ("accessory-attribution-not-observed",)


def test_fewer_than_ten_eligible_callbacks_is_inconclusive(tmp_path):
    def remove_last_location(records):
        records.pop()

    manifest_path, jsonl_path = _write_fixture(
        tmp_path, mutate_records=remove_last_location
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("insufficient-callbacks",)
    assert result.eligible_location_records == 9
    assert result.eligible_callback_count == 9


def test_mixed_accessory_flags_are_inconclusive(tmp_path):
    def mix_flags(records):
        records[-1]["is_produced_by_accessory"] = False

    manifest_path, jsonl_path = _write_fixture(tmp_path, mutate_records=mix_flags)

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("mixed-accessory-flags",)


def test_nil_source_information_is_inconclusive(tmp_path):
    def remove_source_information(records):
        records[-1]["source_information_present"] = False
        records[-1]["is_simulated_by_software"] = None
        records[-1]["is_produced_by_accessory"] = None

    manifest_path, jsonl_path = _write_fixture(
        tmp_path, mutate_records=remove_source_information
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("source-information-missing",)


def test_present_apple_usb_is_inconclusive(tmp_path):
    def mark_usb_present(manifest):
        manifest["connection_evidence"]["windows_apple_usb_status"] = "present"
        manifest["connection_evidence"]["windows_apple_usb_device_count"] = 1

    manifest_path, jsonl_path = _write_fixture(
        tmp_path, mutate_manifest=mark_usb_present
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("apple-usb-present",)


@pytest.mark.parametrize(
    "status,confirmation,reason",
    [
        ("error", True, "apple-usb-status-unknown"),
        ("absent", False, "usb-disconnection-unconfirmed"),
    ],
)
def test_incomplete_bluetooth_connection_evidence_is_inconclusive(
    tmp_path, status, confirmation, reason
):
    def mutate_connection(manifest):
        evidence = manifest["connection_evidence"]
        evidence["windows_apple_usb_status"] = status
        evidence["user_confirmed_usb_disconnected"] = confirmation

    manifest_path, jsonl_path = _write_fixture(
        tmp_path, mutate_manifest=mutate_connection
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == (reason,)


def test_coordinate_mismatch_is_inconclusive(tmp_path):
    def move_far_away(records):
        for record in records[1:]:
            record["latitude"] = 24.0
            record["longitude"] = 120.0

    manifest_path, jsonl_path = _write_fixture(
        tmp_path, mutate_records=move_far_away
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("expected-location-inactive",)


def test_stale_location_timestamps_are_inconclusive(tmp_path):
    def make_stale(records):
        for record in records[1:]:
            record["location_timestamp"] = "2026-08-17T23:59:59Z"

    manifest_path, jsonl_path = _write_fixture(tmp_path, mutate_records=make_stale)

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("stale-samples",)
    assert result.total_location_records == 10
    assert result.eligible_location_records == 0


def test_missing_environment_versions_are_inconclusive(tmp_path):
    def remove_versions(manifest):
        manifest["environment"]["ios_version"] = None

    def remove_capture_versions(records):
        records[0]["ios_version"] = None

    manifest_path, jsonl_path = _write_fixture(
        tmp_path,
        mutate_manifest=remove_versions,
        mutate_records=remove_capture_versions,
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("environment-incomplete",)


def test_stabilization_records_remain_counted_but_do_not_affect_verdict(tmp_path):
    def prepend_transitional_records(records):
        transitional = []
        for second in range(10):
            record = dict(records[1])
            record["callback_sequence"] = second + 11
            record["receipt_timestamp"] = f"2026-08-18T00:00:0{second}Z"
            record["location_timestamp"] = f"2026-08-18T00:00:0{second}Z"
            record["is_produced_by_accessory"] = False
            record["latitude"] = 0.0
            record["longitude"] = 0.0
            transitional.append(record)
        records[1:1] = transitional

    manifest_path, jsonl_path = _write_fixture(
        tmp_path, mutate_records=prepend_transitional_records
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "pass"
    assert result.total_location_records == 20
    assert result.eligible_location_records == 10


def test_ten_locations_from_one_callback_are_insufficient(tmp_path):
    def collapse_into_one_callback(records):
        for location_index, record in enumerate(records[1:]):
            record["callback_sequence"] = 1
            record["location_index"] = location_index

    manifest_path, jsonl_path = _write_fixture(
        tmp_path, mutate_records=collapse_into_one_callback
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("insufficient-callbacks",)
    assert result.eligible_location_records == 10
    assert result.eligible_callback_count == 1
