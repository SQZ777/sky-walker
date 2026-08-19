"""Load and normalize one manifest-plus-JSONL Source Probe artifact pair."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple, cast

from sky_walker.accessory_probe import SCHEMA_VERSION, Scenario, scenario_definition
from sky_walker.accessory_probe.errors import ProbeInputError
from sky_walker.accessory_probe.schema import (
    validate_manifest_schema,
    validate_record_schema,
)
from sky_walker.accessory_probe.timestamps import parse_timestamp


JsonObject = Dict[str, Any]


@dataclass(frozen=True)
class ProbeEnvironment:
    ios_version: Optional[str]
    source_probe_build: Optional[str]
    windows_version: Optional[str]
    location_product_version: Optional[str]
    bluetooth_adapter: Optional[str]


@dataclass(frozen=True)
class ConnectionEvidence:
    user_confirmed_usb_disconnected: Optional[bool]
    windows_apple_usb_status: str
    windows_apple_usb_device_count: int


@dataclass(frozen=True)
class LocationObservation:
    callback_sequence: int
    latitude: float
    longitude: float
    source_information_present: bool
    is_simulated_by_software: Optional[bool]
    is_produced_by_accessory: Optional[bool]


@dataclass(frozen=True)
class ProbeEvidence:
    """Structurally valid, typed evidence ready for verdict evaluation."""

    session_id: str
    scenario: Scenario
    expected_latitude: float
    expected_longitude: float
    horizontal_tolerance_m: float
    minimum_callback_count: int
    maximum_capture_seconds: float
    capture_started: datetime
    capture_stopped: datetime
    stabilization_end: datetime
    environment: ProbeEnvironment
    connection: ConnectionEvidence
    capture_ios_version: Optional[str]
    capture_source_probe_build: Optional[str]
    location_records: Tuple[LocationObservation, ...]
    eligible_location_records: Tuple[LocationObservation, ...]
    callback_count: int
    post_stabilization_callbacks: FrozenSet[int]
    eligible_callbacks: FrozenSet[int]
    stale_post_stabilization_callbacks: FrozenSet[int]


def _read_object(path: Path, label: str) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeInputError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProbeInputError(f"{label} must be a JSON object")
    return value


def _read_jsonl(path: Path) -> List[JsonObject]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProbeInputError(f"cannot read JSONL: {exc}") from exc
    records: List[JsonObject] = []
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


def _required(mapping: JsonObject, key: str, context: str) -> Any:
    if key not in mapping:
        raise ProbeInputError(f"{context} is missing {key}")
    return mapping[key]


def _require_schema(record: JsonObject, context: str) -> None:
    version = _required(record, "schema_version", context)
    if version != SCHEMA_VERSION:
        raise ProbeInputError(f"{context} has unsupported schema_version {version!r}")


def load_evidence(manifest_path: Path, jsonl_path: Path) -> ProbeEvidence:
    """Validate both artifacts and return the policy-ready evidence model."""

    manifest = _read_object(manifest_path, "manifest")
    records = _read_jsonl(jsonl_path)
    _require_schema(manifest, "manifest")
    validate_manifest_schema(manifest)

    session_id = cast(str, _required(manifest, "session_id", "manifest"))
    scenario_value = cast(str, _required(manifest, "scenario", "manifest"))
    if re.fullmatch(r"[A-Z2-9]{8}", session_id) is None:
        raise ProbeInputError("manifest session_id must be eight characters from A-Z or 2-9")
    try:
        scenario = scenario_definition(scenario_value).scenario
    except ValueError as exc:
        raise ProbeInputError(
            f"manifest scenario is unsupported: {scenario_value!r}"
        ) from exc
    parse_timestamp(_required(manifest, "created_at", "manifest"), "created_at")

    expected = cast(JsonObject, _required(manifest, "expected_location", "manifest"))
    timing = cast(JsonObject, _required(manifest, "timing", "manifest"))
    environment_document = cast(
        JsonObject, _required(manifest, "environment", "manifest")
    )
    connection_document = cast(
        JsonObject, _required(manifest, "connection_evidence", "manifest")
    )

    header = records[0]
    _require_schema(header, "capture record")
    validate_record_schema(header, "capture record")
    if _required(header, "record_type", "capture record") != "capture":
        raise ProbeInputError("first JSONL record must be a capture record")
    if (
        header.get("session_id") != session_id
        or header.get("scenario") != scenario.value
    ):
        raise ProbeInputError("capture record does not match manifest session or scenario")
    capture_started = parse_timestamp(
        _required(header, "capture_started_at", "capture record"),
        "capture_started_at",
    )
    capture_stopped = parse_timestamp(
        _required(header, "capture_stopped_at", "capture record"),
        "capture_stopped_at",
    )
    if capture_stopped < capture_started:
        raise ProbeInputError("capture_stopped_at cannot precede capture_started_at")
    stabilization_end = capture_started + timedelta(
        seconds=float(_required(timing, "stabilization_seconds", "timing"))
    )

    locations: List[LocationObservation] = []
    eligible: List[LocationObservation] = []
    seen_callback_locations: Set[Tuple[int, int]] = set()
    post_stabilization_callbacks: Set[int] = set()
    eligible_callbacks: Set[int] = set()
    stale_callbacks: Set[int] = set()
    last_callback_sequence = 0
    next_location_index = 0
    for index, record in enumerate(records[1:], start=2):
        context = f"JSONL line {index}"
        _require_schema(record, context)
        validate_record_schema(record, context)
        if _required(record, "record_type", context) != "location":
            raise ProbeInputError(f"{context} has unknown record_type")
        if (
            record.get("session_id") != session_id
            or record.get("scenario") != scenario.value
        ):
            raise ProbeInputError(f"{context} does not match manifest session or scenario")

        callback_sequence = cast(int, record["callback_sequence"])
        location_index = cast(int, record["location_index"])
        callback_location = (callback_sequence, location_index)
        if callback_location in seen_callback_locations:
            raise ProbeInputError(
                f"{context} duplicates callback_sequence {callback_sequence} "
                f"location_index {location_index}"
            )
        seen_callback_locations.add(callback_location)
        if callback_sequence == last_callback_sequence:
            if location_index != next_location_index:
                raise ProbeInputError(
                    f"{context} callback_sequence {callback_sequence} has "
                    f"non-contiguous location_index {location_index}"
                )
        elif callback_sequence == last_callback_sequence + 1:
            if location_index != 0:
                raise ProbeInputError(
                    f"{context} callback_sequence {callback_sequence} must start "
                    "with location_index 0"
                )
            last_callback_sequence = callback_sequence
        else:
            raise ProbeInputError(
                f"{context} callback_sequence must be consecutive; expected "
                f"{last_callback_sequence} or {last_callback_sequence + 1}, "
                f"got {callback_sequence}"
            )
        next_location_index = location_index + 1
        observation = LocationObservation(
            callback_sequence=callback_sequence,
            latitude=float(record["latitude"]),
            longitude=float(record["longitude"]),
            source_information_present=cast(
                bool, record["source_information_present"]
            ),
            is_simulated_by_software=cast(
                Optional[bool], record["is_simulated_by_software"]
            ),
            is_produced_by_accessory=cast(
                Optional[bool], record["is_produced_by_accessory"]
            ),
        )
        locations.append(observation)

        received = parse_timestamp(record["receipt_timestamp"], "receipt_timestamp")
        location_time = parse_timestamp(
            record["location_timestamp"], "location_timestamp"
        )
        if not capture_started <= received <= capture_stopped:
            raise ProbeInputError(
                f"{context} receipt_timestamp is outside the capture window"
            )
        if received >= stabilization_end:
            post_stabilization_callbacks.add(callback_sequence)
            if location_time >= capture_started:
                eligible.append(observation)
                eligible_callbacks.add(callback_sequence)
            else:
                stale_callbacks.add(callback_sequence)

    return ProbeEvidence(
        session_id=session_id,
        scenario=scenario,
        expected_latitude=float(expected["latitude"]),
        expected_longitude=float(expected["longitude"]),
        horizontal_tolerance_m=float(expected["horizontal_tolerance_m"]),
        minimum_callback_count=int(timing["minimum_post_stabilization_callbacks"]),
        maximum_capture_seconds=float(timing["maximum_capture_seconds"]),
        capture_started=capture_started,
        capture_stopped=capture_stopped,
        stabilization_end=stabilization_end,
        environment=ProbeEnvironment(
            ios_version=cast(Optional[str], environment_document["ios_version"]),
            source_probe_build=cast(
                Optional[str], environment_document["source_probe_build"]
            ),
            windows_version=cast(
                Optional[str], environment_document["windows_version"]
            ),
            location_product_version=cast(
                Optional[str], environment_document["location_product_version"]
            ),
            bluetooth_adapter=cast(
                Optional[str], environment_document["bluetooth_adapter"]
            ),
        ),
        connection=ConnectionEvidence(
            user_confirmed_usb_disconnected=cast(
                Optional[bool],
                connection_document["user_confirmed_usb_disconnected"],
            ),
            windows_apple_usb_status=cast(
                str, connection_document["windows_apple_usb_status"]
            ),
            windows_apple_usb_device_count=cast(
                int, connection_document["windows_apple_usb_device_count"]
            ),
        ),
        capture_ios_version=cast(Optional[str], header["ios_version"]),
        capture_source_probe_build=cast(
            Optional[str], header["source_probe_build"]
        ),
        location_records=tuple(locations),
        eligible_location_records=tuple(eligible),
        callback_count=last_callback_sequence,
        post_stabilization_callbacks=frozenset(post_stabilization_callbacks),
        eligible_callbacks=frozenset(eligible_callbacks),
        stale_post_stabilization_callbacks=frozenset(stale_callbacks),
    )
