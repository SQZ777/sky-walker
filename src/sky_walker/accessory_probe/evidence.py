"""Load and normalize one manifest-plus-JSONL Source Probe artifact pair."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Set, Tuple, cast

from sky_walker.accessory_probe import SCENARIOS, SCHEMA_VERSION
from sky_walker.accessory_probe.errors import ProbeInputError
from sky_walker.accessory_probe.schema import (
    validate_manifest_schema,
    validate_record_schema,
)


JsonObject = Dict[str, Any]


@dataclass(frozen=True)
class ProbeEvidence:
    """Structurally valid evidence normalized for verdict evaluation."""

    session_id: str
    scenario: str
    expected_latitude: float
    expected_longitude: float
    horizontal_tolerance_m: float
    minimum_callback_count: int
    environment: JsonObject
    connection: JsonObject
    capture: JsonObject
    location_records: Tuple[JsonObject, ...]
    eligible_location_records: Tuple[JsonObject, ...]
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


def load_evidence(manifest_path: Path, jsonl_path: Path) -> ProbeEvidence:
    """Validate both artifacts and return the policy-ready evidence model."""

    manifest = _read_object(manifest_path, "manifest")
    records = _read_jsonl(jsonl_path)
    _require_schema(manifest, "manifest")
    validate_manifest_schema(manifest)

    session_id = cast(str, _required(manifest, "session_id", "manifest"))
    scenario = cast(str, _required(manifest, "scenario", "manifest"))
    if re.fullmatch(r"[A-Z2-9]{8}", session_id) is None:
        raise ProbeInputError("manifest session_id must be eight characters from A-Z or 2-9")
    if scenario not in SCENARIOS:
        raise ProbeInputError(f"manifest scenario is unsupported: {scenario!r}")
    _parse_time(_required(manifest, "created_at", "manifest"), "created_at")

    expected = cast(JsonObject, _required(manifest, "expected_location", "manifest"))
    timing = cast(JsonObject, _required(manifest, "timing", "manifest"))
    environment = cast(JsonObject, _required(manifest, "environment", "manifest"))
    connection = cast(JsonObject, _required(manifest, "connection_evidence", "manifest"))

    header = records[0]
    _require_schema(header, "capture record")
    validate_record_schema(header, "capture record")
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
    stabilization_end = capture_started + timedelta(
        seconds=float(_required(timing, "stabilization_seconds", "timing"))
    )

    locations: List[JsonObject] = []
    eligible: List[JsonObject] = []
    callback_locations: Dict[int, Set[int]] = {}
    seen_callback_locations: Set[Tuple[int, int]] = set()
    post_stabilization_callbacks: Set[int] = set()
    eligible_callbacks: Set[int] = set()
    stale_callbacks: Set[int] = set()
    for index, record in enumerate(records[1:], start=2):
        context = f"JSONL line {index}"
        _require_schema(record, context)
        validate_record_schema(record, context)
        if _required(record, "record_type", context) != "location":
            raise ProbeInputError(f"{context} has unknown record_type")
        if record.get("session_id") != session_id or record.get("scenario") != scenario:
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
        callback_locations.setdefault(callback_sequence, set()).add(location_index)
        locations.append(record)

        received = _parse_time(record["receipt_timestamp"], "receipt_timestamp")
        location_time = _parse_time(record["location_timestamp"], "location_timestamp")
        if received >= stabilization_end:
            post_stabilization_callbacks.add(callback_sequence)
            if location_time >= capture_started:
                eligible.append(record)
                eligible_callbacks.add(callback_sequence)
            else:
                stale_callbacks.add(callback_sequence)

    for callback_sequence, indices in callback_locations.items():
        if indices != set(range(len(indices))):
            raise ProbeInputError(
                f"callback_sequence {callback_sequence} has non-contiguous location_index values"
            )

    return ProbeEvidence(
        session_id=session_id,
        scenario=scenario,
        expected_latitude=float(expected["latitude"]),
        expected_longitude=float(expected["longitude"]),
        horizontal_tolerance_m=float(expected["horizontal_tolerance_m"]),
        minimum_callback_count=int(timing["minimum_post_stabilization_callbacks"]),
        environment=environment,
        connection=connection,
        capture=header,
        location_records=tuple(locations),
        eligible_location_records=tuple(eligible),
        callback_count=len(callback_locations),
        post_stabilization_callbacks=frozenset(post_stabilization_callbacks),
        eligible_callbacks=frozenset(eligible_callbacks),
        stale_post_stabilization_callbacks=frozenset(stale_callbacks),
    )
