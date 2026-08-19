"""Probe Verdict behavior through the manifest-plus-JSONL seam."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from sky_walker.accessory_probe.usb import AppleUsbEvidence
from sky_walker.accessory_probe.errors import ProbeInputError
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


def _write_ble_fixture(tmp_path, *, mutate_trace=None):
    def use_ble_scenario(manifest):
        manifest["scenario"] = "sky-walker-ble-lns"
        manifest["environment"]["location_product_version"] = "sky-walker 0.1.0"
        manifest["environment"]["bluetooth_adapter"] = "TP-Link Bluetooth 5.4"

    def use_ble_scenario_in_records(records):
        for record in records:
            record["scenario"] = "sky-walker-ble-lns"

    manifest_path, jsonl_path = _write_fixture(
        tmp_path,
        mutate_manifest=use_ble_scenario,
        mutate_records=use_ble_scenario_in_records,
    )
    records = [
        {
            "schema_version": 1,
            "session_id": "ABCD2345",
            "record_type": "peripheral",
            "observed_at": "2026-08-18T00:00:00Z",
            "status": "advertising",
        },
        {
            "schema_version": 1,
            "session_id": "ABCD2345",
            "record_type": "peripheral",
            "observed_at": "2026-08-18T00:00:01Z",
            "status": "subscribed",
        },
    ]
    for second in range(22):
        observed_at = f"2026-08-18T00:00:{second:02d}Z"
        records.append({
            "schema_version": 1,
            "session_id": "ABCD2345",
            "record_type": "usb",
            "observed_at": observed_at,
            "status": "absent",
            "device_count": 0,
        })
        if second:
            records.append({
                "schema_version": 1,
                "session_id": "ABCD2345",
                "record_type": "sample",
                "observed_at": observed_at,
                "latitude": 25.073944586589487,
                "longitude": 121.51104972333346,
                "subscribed_clients": 1,
            })
    records.append({
        "schema_version": 1,
        "session_id": "ABCD2345",
        "record_type": "peripheral",
        "observed_at": "2026-08-18T00:00:22Z",
        "status": "stopped",
    })
    if mutate_trace is not None:
        mutate_trace(records)
    records.sort(
        key=lambda record: datetime.fromisoformat(
            record["observed_at"].replace("Z", "+00:00")
        )
    )
    trace_path = tmp_path / "ABCD2345.ble-trace.jsonl"
    trace_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return manifest_path, jsonl_path, trace_path


def test_ble_lns_requires_complete_transport_trace_for_pass(tmp_path):
    manifest_path, jsonl_path, trace_path = _write_ble_fixture(tmp_path)

    result = validate_artifacts(
        manifest_path,
        jsonl_path,
        ble_trace_path=trace_path,
        # Reconnecting after capture must not rewrite historical USB evidence.
        usb_detector=lambda: AppleUsbEvidence(status="present", device_count=1),
    )

    assert result.verdict == "pass"
    assert result.reason_codes == ("accessory-attribution-confirmed",)
    assert result.validation_apple_usb_status == "absent"


def test_ble_lns_without_transport_trace_is_inconclusive(tmp_path):
    manifest_path, jsonl_path, _trace_path = _write_ble_fixture(tmp_path)

    result = validate_artifacts(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("ble-trace-missing",)


def test_ble_lns_trace_rejects_usb_presence_during_capture(tmp_path):
    def connect_usb(records):
        next(
            record
            for record in records
            if record["record_type"] == "usb"
            and record["observed_at"] == "2026-08-18T00:00:15Z"
        )["status"] = "present"
        next(
            record
            for record in records
            if record["record_type"] == "usb"
            and record["observed_at"] == "2026-08-18T00:00:15Z"
        )["device_count"] = 1

    manifest_path, jsonl_path, trace_path = _write_ble_fixture(
        tmp_path, mutate_trace=connect_usb
    )

    result = validate_artifacts(
        manifest_path, jsonl_path, ble_trace_path=trace_path
    )

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("apple-usb-present",)


def test_ble_lns_trace_rejects_disconnect_during_capture(tmp_path):
    def disconnect(records):
        records.append({
            "schema_version": 1,
            "session_id": "ABCD2345",
            "record_type": "peripheral",
            "observed_at": "2026-08-18T00:00:15Z",
            "status": "disconnected",
        })

    manifest_path, jsonl_path, trace_path = _write_ble_fixture(
        tmp_path, mutate_trace=disconnect
    )

    result = validate_artifacts(
        manifest_path, jsonl_path, ble_trace_path=trace_path
    )

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("ble-disconnected",)


def test_ble_lns_trace_rejects_feed_stop_during_capture(tmp_path):
    def stop_during_capture(records):
        records.append({
            "schema_version": 1,
            "session_id": "ABCD2345",
            "record_type": "peripheral",
            "observed_at": "2026-08-18T00:00:15Z",
            "status": "stopped",
        })

    manifest_path, jsonl_path, trace_path = _write_ble_fixture(
        tmp_path, mutate_trace=stop_during_capture
    )

    result = validate_artifacts(
        manifest_path, jsonl_path, ble_trace_path=trace_path
    )

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("ble-disconnected",)


def test_ble_lns_trace_rejects_interruption_during_capture(tmp_path):
    def interrupt(records):
        records.append({
            "schema_version": 1,
            "session_id": "ABCD2345",
            "record_type": "interrupted",
            "observed_at": "2026-08-18T00:00:15Z",
        })

    manifest_path, jsonl_path, trace_path = _write_ble_fixture(
        tmp_path, mutate_trace=interrupt
    )

    result = validate_artifacts(
        manifest_path, jsonl_path, ble_trace_path=trace_path
    )

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("ble-transport-interrupted",)


def test_ble_lns_trace_rejects_sample_burst(tmp_path):
    def add_burst_sample(records):
        sample = next(
            record
            for record in records
            if record["record_type"] == "sample"
            and record["observed_at"] == "2026-08-18T00:00:12Z"
        ).copy()
        sample["observed_at"] = "2026-08-18T00:00:12.100Z"
        records.append(sample)

    manifest_path, jsonl_path, trace_path = _write_ble_fixture(
        tmp_path, mutate_trace=add_burst_sample
    )

    result = validate_artifacts(
        manifest_path, jsonl_path, ble_trace_path=trace_path
    )

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("ble-sample-trace-incomplete",)


def test_ble_lns_trace_rejects_malformed_typed_record(tmp_path):
    def corrupt_usb_count(records):
        next(
            record for record in records if record["record_type"] == "usb"
        )["device_count"] = "zero"

    manifest_path, jsonl_path, trace_path = _write_ble_fixture(
        tmp_path, mutate_trace=corrupt_usb_count
    )

    with pytest.raises(ProbeInputError, match="device_count"):
        validate_artifacts(
            manifest_path, jsonl_path, ble_trace_path=trace_path
        )


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
        for record in records[1:]:
            record["callback_sequence"] += 10
        transitional = []
        for second in range(10):
            record = dict(records[1])
            record["callback_sequence"] = second + 1
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


def test_ten_eligible_callbacks_with_a_gap_are_not_a_consecutive_pass(tmp_path):
    def insert_stale_gap_and_later_callback(records):
        records[5]["location_timestamp"] = "2026-08-17T23:59:59Z"
        later = dict(records[-1])
        later["callback_sequence"] = 11
        later["receipt_timestamp"] = "2026-08-18T00:00:21Z"
        later["location_timestamp"] = "2026-08-18T00:00:21Z"
        records.append(later)

    manifest_path, jsonl_path = _write_fixture(
        tmp_path, mutate_records=insert_stale_gap_and_later_callback
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("nonconsecutive-callbacks",)


def test_capture_longer_than_session_limit_is_inconclusive(tmp_path):
    def exceed_maximum_capture(records):
        records[0]["capture_stopped_at"] = "2026-08-18T00:02:01Z"

    manifest_path, jsonl_path = _write_fixture(
        tmp_path, mutate_records=exceed_maximum_capture
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "inconclusive"
    assert result.reason_codes == ("capture-duration-exceeded",)


def test_qualifying_consecutive_run_is_not_invalidated_by_later_bad_callback(
    tmp_path
):
    def append_bad_callback_after_qualifying_run(records):
        later = dict(records[-1])
        later["callback_sequence"] = 11
        later["receipt_timestamp"] = "2026-08-18T00:00:21Z"
        later["location_timestamp"] = "2026-08-18T00:00:21Z"
        later["is_produced_by_accessory"] = False
        later["latitude"] = 0.0
        later["longitude"] = 0.0
        records.append(later)

    manifest_path, jsonl_path = _write_fixture(
        tmp_path, mutate_records=append_bad_callback_after_qualifying_run
    )

    result = validate_files(manifest_path, jsonl_path)

    assert result.verdict == "pass"
    assert result.reason_codes == ("accessory-attribution-confirmed",)
