"""Validate BLE transport and continuous Apple-USB evidence for one capture."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from sky_walker.accessory_probe import SCHEMA_VERSION
from sky_walker.accessory_probe.errors import ProbeInputError
from sky_walker.accessory_probe.evidence import ProbeEvidence
from sky_walker.accessory_probe.timestamps import parse_timestamp
from sky_walker.accessory_probe.usb import AppleUsbEvidence
from sky_walker.accessory_probe.verdict import ProbeReason


_MAX_SAMPLE_GAP_SECONDS = 2.0
_MIN_SAMPLE_GAP_SECONDS = 0.5
_BOUNDARY_TOLERANCE_SECONDS = 1.5


class TraceRecordType(str, Enum):
    PERIPHERAL = "peripheral"
    USB = "usb"
    SAMPLE = "sample"
    ERROR = "error"
    INTERRUPTED = "interrupted"


class TracePeripheralStatus(str, Enum):
    STOPPED = "stopped"
    ADVERTISING = "advertising"
    SUBSCRIBED = "subscribed"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass(frozen=True)
class BleTraceAssessment:
    reason: Optional[ProbeReason]
    usb_evidence: AppleUsbEvidence


@dataclass(frozen=True)
class _PeripheralRecord:
    observed_at: datetime
    status: TracePeripheralStatus


@dataclass(frozen=True)
class _UsbRecord:
    observed_at: datetime
    status: str
    device_count: int


@dataclass(frozen=True)
class _SampleRecord:
    observed_at: datetime
    latitude: float
    longitude: float
    subscribed_clients: int


@dataclass(frozen=True)
class _SignalRecord:
    observed_at: datetime
    record_type: TraceRecordType


TraceRecord = Union[_PeripheralRecord, _UsbRecord, _SampleRecord, _SignalRecord]


def _integer(document: Dict[str, Any], key: str, context: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProbeInputError(f"{context} {key} must be a non-negative integer")
    return value


def _number(document: Dict[str, Any], key: str, context: str) -> float:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProbeInputError(f"{context} {key} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ProbeInputError(f"{context} {key} must be finite")
    return result


def _parse_record(
    document: Dict[str, Any],
    record_type: TraceRecordType,
    observed_at: datetime,
    context: str,
) -> TraceRecord:
    if record_type is TraceRecordType.PERIPHERAL:
        try:
            peripheral_status = TracePeripheralStatus(document.get("status"))
        except (TypeError, ValueError) as exc:
            raise ProbeInputError(
                f"{context} has an invalid peripheral status"
            ) from exc
        return _PeripheralRecord(
            observed_at=observed_at,
            status=peripheral_status,
        )
    if record_type is TraceRecordType.USB:
        usb_status = document.get("status")
        if not isinstance(usb_status, str) or usb_status not in {
            "absent",
            "present",
            "error",
        }:
            raise ProbeInputError(f"{context} has an invalid USB status")
        return _UsbRecord(
            observed_at=observed_at,
            status=usb_status,
            device_count=_integer(document, "device_count", context),
        )
    if record_type is TraceRecordType.SAMPLE:
        latitude = _number(document, "latitude", context)
        longitude = _number(document, "longitude", context)
        if not -90.0 <= latitude <= 90.0:
            raise ProbeInputError(f"{context} latitude is outside -90..90")
        if not -180.0 <= longitude <= 180.0:
            raise ProbeInputError(f"{context} longitude is outside -180..180")
        return _SampleRecord(
            observed_at=observed_at,
            latitude=latitude,
            longitude=longitude,
            subscribed_clients=_integer(
                document, "subscribed_clients", context
            ),
        )
    if record_type is TraceRecordType.ERROR:
        if not isinstance(document.get("message"), str):
            raise ProbeInputError(f"{context} error message must be a string")
    return _SignalRecord(observed_at=observed_at, record_type=record_type)


def _load_trace(path: Path, session_id: str) -> List[TraceRecord]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProbeInputError(f"cannot read BLE trace: {exc}") from exc
    records: List[TraceRecord] = []
    previous: Optional[datetime] = None
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        context = f"BLE trace line {line_number}"
        try:
            document = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProbeInputError(f"{context} is invalid JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise ProbeInputError(f"{context} must be an object")
        if document.get("schema_version") != SCHEMA_VERSION:
            raise ProbeInputError(f"{context} has unsupported schema_version")
        if document.get("session_id") != session_id:
            raise ProbeInputError(f"{context} does not match the Source Test Session")
        try:
            record_type = TraceRecordType(document.get("record_type"))
        except (TypeError, ValueError) as exc:
            raise ProbeInputError(f"{context} has unknown record_type") from exc
        observed_at = parse_timestamp(
            document.get("observed_at"), f"{context} observed_at"
        )
        if previous is not None and observed_at < previous:
            raise ProbeInputError("BLE trace timestamps must be nondecreasing")
        previous = observed_at
        records.append(
            _parse_record(document, record_type, observed_at, context)
        )
    if not records:
        raise ProbeInputError("BLE trace contains no records")
    return records


def _covers_window(
    times: List[datetime],
    start: datetime,
    stop: datetime,
    *,
    minimum_gap_seconds: float = 0.0,
) -> bool:
    relevant = sorted(time for time in times if start <= time <= stop)
    if not relevant:
        return False
    if (relevant[0] - start).total_seconds() > _BOUNDARY_TOLERANCE_SECONDS:
        return False
    if (stop - relevant[-1]).total_seconds() > _BOUNDARY_TOLERANCE_SECONDS:
        return False
    gaps = [
        (right - left).total_seconds()
        for left, right in zip(relevant, relevant[1:])
    ]
    return all(
        minimum_gap_seconds <= gap <= _MAX_SAMPLE_GAP_SECONDS for gap in gaps
    )


def assess_ble_trace(path: Path, evidence: ProbeEvidence) -> BleTraceAssessment:
    records = _load_trace(path, evidence.session_id)
    usb = [record for record in records if isinstance(record, _UsbRecord)]
    capture_usb = [
        record
        for record in usb
        if evidence.capture_started <= record.observed_at <= evidence.capture_stopped
    ]
    if any(
        record.status == "present" or record.device_count > 0
        for record in capture_usb
    ):
        return BleTraceAssessment(
            reason=ProbeReason.APPLE_USB_PRESENT,
            usb_evidence=AppleUsbEvidence(status="present", device_count=1),
        )
    if any(
        record.status != "absent" or record.device_count != 0
        for record in capture_usb
    ) or not _covers_window(
        [record.observed_at for record in usb],
        evidence.capture_started,
        evidence.capture_stopped,
    ):
        return BleTraceAssessment(
            reason=ProbeReason.APPLE_USB_TRACE_INCOMPLETE,
            usb_evidence=AppleUsbEvidence(status="error", device_count=0),
        )

    peripheral = [
        record for record in records if isinstance(record, _PeripheralRecord)
    ]
    if any(
        record.status
        in {TracePeripheralStatus.DISCONNECTED, TracePeripheralStatus.STOPPED}
        and evidence.capture_started
        <= record.observed_at
        < evidence.capture_stopped
        for record in peripheral
    ):
        return BleTraceAssessment(
            reason=ProbeReason.BLE_DISCONNECTED,
            usb_evidence=AppleUsbEvidence(status="absent", device_count=0),
        )
    if any(
        record.status is TracePeripheralStatus.ERROR
        and evidence.capture_started
        <= record.observed_at
        <= evidence.capture_stopped
        for record in peripheral
    ) or any(
        isinstance(record, _SignalRecord)
        and record.record_type is TraceRecordType.ERROR
        and evidence.capture_started
        <= record.observed_at
        <= evidence.capture_stopped
        for record in records
    ):
        return BleTraceAssessment(
            reason=ProbeReason.BLE_TRANSPORT_ERROR,
            usb_evidence=AppleUsbEvidence(status="absent", device_count=0),
        )
    if any(
        isinstance(record, _SignalRecord)
        and record.record_type is TraceRecordType.INTERRUPTED
        and evidence.capture_started
        <= record.observed_at
        <= evidence.capture_stopped
        for record in records
    ):
        return BleTraceAssessment(
            reason=ProbeReason.BLE_TRANSPORT_INTERRUPTED,
            usb_evidence=AppleUsbEvidence(status="absent", device_count=0),
        )

    status_at_stabilization = next(
        (
            record.status
            for record in reversed(peripheral)
            if record.observed_at <= evidence.stabilization_end
        ),
        None,
    )
    if status_at_stabilization is not TracePeripheralStatus.SUBSCRIBED:
        return BleTraceAssessment(
            reason=ProbeReason.BLE_NOT_SUBSCRIBED,
            usb_evidence=AppleUsbEvidence(status="absent", device_count=0),
        )
    if any(
        record.observed_at > evidence.stabilization_end
        and record.observed_at < evidence.capture_stopped
        and record.status is not TracePeripheralStatus.SUBSCRIBED
        for record in peripheral
    ):
        return BleTraceAssessment(
            reason=ProbeReason.BLE_DISCONNECTED,
            usb_evidence=AppleUsbEvidence(status="absent", device_count=0),
        )

    samples = [record for record in records if isinstance(record, _SampleRecord)]
    capture_samples = [
        record
        for record in samples
        if evidence.stabilization_end
        <= record.observed_at
        <= evidence.capture_stopped
    ]
    if any(
        record.subscribed_clients < 1
        or record.latitude != evidence.expected_latitude
        or record.longitude != evidence.expected_longitude
        for record in capture_samples
    ) or not _covers_window(
        [record.observed_at for record in samples],
        evidence.stabilization_end,
        evidence.capture_stopped,
        minimum_gap_seconds=_MIN_SAMPLE_GAP_SECONDS,
    ):
        return BleTraceAssessment(
            reason=ProbeReason.BLE_SAMPLE_TRACE_INCOMPLETE,
            usb_evidence=AppleUsbEvidence(status="absent", device_count=0),
        )
    return BleTraceAssessment(
        reason=None,
        usb_evidence=AppleUsbEvidence(status="absent", device_count=0),
    )
