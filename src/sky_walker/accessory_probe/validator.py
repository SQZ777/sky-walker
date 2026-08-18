"""Validate Source Probe artifacts and derive an evidence-based verdict."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Sequence

from sky_walker.accessory_probe import SCENARIOS, SCHEMA_VERSION


class ProbeInputError(ValueError):
    """The artifact cannot be evaluated because its structure is invalid."""


@dataclass(frozen=True)
class ProbeResult:
    session_id: str
    scenario: str
    verdict: str
    reason_codes: Sequence[str]
    total_location_records: int
    eligible_location_records: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "scenario": self.scenario,
            "verdict": self.verdict,
            "reason_codes": list(self.reason_codes),
            "total_location_records": self.total_location_records,
            "eligible_location_records": self.eligible_location_records,
        }


def _read_object(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeInputError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProbeInputError(f"{label} must be a JSON object")
    return value


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProbeInputError(f"cannot read JSONL: {exc}") from exc
    records: List[Dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProbeInputError(f"JSONL line {line_number} is invalid: {exc}") from exc
        if not isinstance(record, dict):
            raise ProbeInputError(f"JSONL line {line_number} must be an object")
        records.append(record)
    if not records:
        raise ProbeInputError("JSONL contains no records")
    return records


def _required(mapping: Dict[str, Any], key: str, context: str) -> Any:
    if key not in mapping:
        raise ProbeInputError(f"{context} is missing {key}")
    return mapping[key]


def _require_schema(record: Dict[str, Any], context: str) -> None:
    version = _required(record, "schema_version", context)
    if version != SCHEMA_VERSION:
        raise ProbeInputError(f"{context} has unsupported schema_version {version!r}")


def _parse_time(value: Any, context: str) -> datetime:
    if not isinstance(value, str):
        raise ProbeInputError(f"{context} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProbeInputError(f"{context} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ProbeInputError(f"{context} must include a timezone")
    return parsed


def _distance_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return radius * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def validate_files(manifest_path: Path, jsonl_path: Path) -> ProbeResult:
    manifest = _read_object(manifest_path, "manifest")
    records = _read_jsonl(jsonl_path)
    _require_schema(manifest, "manifest")

    session_id = _required(manifest, "session_id", "manifest")
    scenario = _required(manifest, "scenario", "manifest")
    if not isinstance(session_id, str) or re.fullmatch(r"[A-Z2-9]{8}", session_id) is None:
        raise ProbeInputError("manifest session_id must be eight characters from A-Z or 2-9")
    if scenario not in SCENARIOS:
        raise ProbeInputError(f"manifest scenario is unsupported: {scenario!r}")
    _parse_time(_required(manifest, "created_at", "manifest"), "created_at")
    expected = _required(manifest, "expected_location", "manifest")
    timing = _required(manifest, "timing", "manifest")
    stimulus = _required(manifest, "stimulus", "manifest")
    environment = _required(manifest, "environment", "manifest")
    connection = _required(manifest, "connection_evidence", "manifest")
    for value, label in (
        (expected, "expected_location"),
        (timing, "timing"),
        (stimulus, "stimulus"),
        (environment, "environment"),
        (connection, "connection_evidence"),
    ):
        if not isinstance(value, dict):
            raise ProbeInputError(f"manifest {label} must be an object")
    for key in (
        "ios_version",
        "source_probe_build",
        "windows_version",
        "location_product_version",
        "bluetooth_adapter",
    ):
        _required(environment, key, "environment")

    header = records[0]
    _require_schema(header, "capture record")
    if _required(header, "record_type", "capture record") != "capture":
        raise ProbeInputError("first JSONL record must be a capture record")
    if header.get("session_id") != session_id or header.get("scenario") != scenario:
        raise ProbeInputError("capture record does not match manifest session or scenario")
    capture_started = _parse_time(
        _required(header, "capture_started_at", "capture record"),
        "capture_started_at",
    )
    capture_stopped = _parse_time(
        _required(header, "capture_stopped_at", "capture record"),
        "capture_stopped_at",
    )
    if capture_stopped < capture_started:
        raise ProbeInputError("capture_stopped_at cannot precede capture_started_at")
    _required(header, "ios_version", "capture record")
    _required(header, "source_probe_build", "capture record")
    stabilization_end = capture_started + timedelta(
        seconds=float(_required(timing, "stabilization_seconds", "timing"))
    )

    location_records: List[Dict[str, Any]] = []
    eligible: List[Dict[str, Any]] = []
    post_stabilization_count = 0
    stale_post_stabilization_count = 0
    for index, record in enumerate(records[1:], start=2):
        context = f"JSONL line {index}"
        _require_schema(record, context)
        if _required(record, "record_type", context) != "location":
            raise ProbeInputError(f"{context} has unknown record_type")
        if record.get("session_id") != session_id or record.get("scenario") != scenario:
            raise ProbeInputError(f"{context} does not match manifest session or scenario")
        for key in (
            "callback_sequence",
            "location_index",
            "location_timestamp",
            "receipt_timestamp",
            "latitude",
            "longitude",
            "altitude",
            "horizontal_accuracy",
            "vertical_accuracy",
            "speed",
            "course",
            "source_information_present",
            "is_simulated_by_software",
            "is_produced_by_accessory",
        ):
            _required(record, key, context)
        source_present = record["source_information_present"]
        simulated = record["is_simulated_by_software"]
        accessory = record["is_produced_by_accessory"]
        if not isinstance(source_present, bool):
            raise ProbeInputError(f"{context} source information marker must be boolean")
        if source_present and not (
            isinstance(simulated, bool) and isinstance(accessory, bool)
        ):
            raise ProbeInputError(f"{context} source information flags must be boolean")
        if not source_present and (simulated is not None or accessory is not None):
            raise ProbeInputError(
                f"{context} source information flags must be null when metadata is absent"
            )
        location_records.append(record)
        received = _parse_time(_required(record, "receipt_timestamp", context), "receipt_timestamp")
        location_time = _parse_time(
            _required(record, "location_timestamp", context), "location_timestamp"
        )
        if received >= stabilization_end:
            post_stabilization_count += 1
            if location_time >= capture_started:
                eligible.append(record)
            else:
                stale_post_stabilization_count += 1

    minimum = int(_required(timing, "minimum_post_stabilization_samples", "timing"))
    expected_lat = float(_required(expected, "latitude", "expected_location"))
    expected_lon = float(_required(expected, "longitude", "expected_location"))
    tolerance = float(
        _required(expected, "horizontal_tolerance_m", "expected_location")
    )
    in_range = [
        record
        for record in eligible
        if _distance_metres(
            expected_lat,
            expected_lon,
            float(_required(record, "latitude", "location record")),
            float(_required(record, "longitude", "location record")),
        )
        <= tolerance
    ]
    source_complete = all(
        record.get("source_information_present") is True
        and isinstance(record.get("is_simulated_by_software"), bool)
        and isinstance(record.get("is_produced_by_accessory"), bool)
        for record in eligible
    )
    attributed = all(record.get("is_produced_by_accessory") is True for record in eligible)
    not_attributed = all(
        record.get("is_produced_by_accessory") is False for record in eligible
    )
    usb_complete = scenario != "ianygo-bluetooth" or (
        connection.get("user_confirmed_usb_disconnected") is True
        and connection.get("windows_apple_usb_status") == "absent"
        and connection.get("windows_apple_usb_device_count") == 0
    )
    required_environment = (
        "ios_version",
        "source_probe_build",
        "windows_version",
        "location_product_version",
    )
    environment_complete = all(
        isinstance(environment.get(key), str) and bool(environment[key].strip())
        for key in required_environment
    )
    if scenario == "ianygo-bluetooth":
        environment_complete = environment_complete and (
            isinstance(environment.get("bluetooth_adapter"), str)
            and bool(environment["bluetooth_adapter"].strip())
        )
    capture_environment_complete = all(
        isinstance(header.get(key), str) and bool(header[key].strip())
        for key in ("ios_version", "source_probe_build")
    )
    environment_matches = (
        header.get("ios_version") == environment.get("ios_version")
        and header.get("source_probe_build") == environment.get("source_probe_build")
    )
    if (
        len(eligible) >= minimum
        and len(in_range) == len(eligible)
        and source_complete
        and attributed
        and usb_complete
        and environment_complete
        and capture_environment_complete
        and environment_matches
    ):
        return ProbeResult(
            session_id=session_id,
            scenario=scenario,
            verdict="pass",
            reason_codes=("accessory-attribution-confirmed",),
            total_location_records=len(location_records),
            eligible_location_records=len(eligible),
        )
    if (
        len(eligible) >= minimum
        and len(in_range) == len(eligible)
        and source_complete
        and not_attributed
        and usb_complete
        and environment_complete
        and capture_environment_complete
        and environment_matches
    ):
        return ProbeResult(
            session_id=session_id,
            scenario=scenario,
            verdict="fail",
            reason_codes=("accessory-attribution-not-observed",),
            total_location_records=len(location_records),
            eligible_location_records=len(eligible),
        )

    if (
        len(eligible) < minimum
        and post_stabilization_count >= minimum
        and stale_post_stabilization_count > 0
    ):
        reason = "stale-samples"
    elif len(eligible) < minimum:
        reason = "insufficient-samples"
    elif not environment_complete or not capture_environment_complete:
        reason = "environment-incomplete"
    elif not environment_matches:
        reason = "environment-mismatch"
    elif len(in_range) != len(eligible):
        reason = "expected-location-inactive"
    elif (
        scenario == "ianygo-bluetooth"
        and connection.get("windows_apple_usb_status") == "present"
    ):
        reason = "apple-usb-present"
    elif (
        scenario == "ianygo-bluetooth"
        and connection.get("windows_apple_usb_status") != "absent"
    ):
        reason = "apple-usb-status-unknown"
    elif (
        scenario == "ianygo-bluetooth"
        and connection.get("user_confirmed_usb_disconnected") is not True
    ):
        reason = "usb-disconnection-unconfirmed"
    elif not source_complete:
        reason = "source-information-missing"
    elif source_complete and len({
        record["is_produced_by_accessory"] for record in eligible
    }) > 1:
        reason = "mixed-accessory-flags"
    else:
        reason = "evidence-incomplete"
    return ProbeResult(
        session_id=session_id,
        scenario=scenario,
        verdict="inconclusive",
        reason_codes=(reason,),
        total_location_records=len(location_records),
        eligible_location_records=len(eligible),
    )
