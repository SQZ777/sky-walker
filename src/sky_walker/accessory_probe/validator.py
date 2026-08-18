"""Derive an evidence-based verdict from Source Probe artifacts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

from sky_walker.accessory_probe import SCHEMA_VERSION
from sky_walker.accessory_probe.errors import ProbeInputError
from sky_walker.accessory_probe.evidence import ProbeEvidence, load_evidence
from sky_walker.accessory_probe.usb import AppleUsbEvidence


@dataclass(frozen=True)
class ProbeResult:
    session_id: str
    scenario: str
    verdict: str
    reason_codes: Sequence[str]
    total_location_records: int
    eligible_location_records: int
    total_callback_count: int
    eligible_callback_count: int
    validation_apple_usb_status: str
    validation_apple_usb_device_count: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "scenario": self.scenario,
            "verdict": self.verdict,
            "reason_codes": list(self.reason_codes),
            "total_location_records": self.total_location_records,
            "eligible_location_records": self.eligible_location_records,
            "total_callback_count": self.total_callback_count,
            "eligible_callback_count": self.eligible_callback_count,
            "validation_apple_usb_status": self.validation_apple_usb_status,
            "validation_apple_usb_device_count": self.validation_apple_usb_device_count,
        }


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


def _validation_usb(
    scenario: str,
    detector: Optional[Callable[[], AppleUsbEvidence]],
) -> AppleUsbEvidence:
    if scenario != "ianygo-bluetooth":
        return AppleUsbEvidence(status="not-required", device_count=0)
    if detector is None:
        return AppleUsbEvidence(status="error", device_count=0)
    try:
        return detector()
    except Exception:
        return AppleUsbEvidence(status="error", device_count=0)


def _environment_complete(evidence: ProbeEvidence) -> bool:
    required = (
        "ios_version",
        "source_probe_build",
        "windows_version",
        "location_product_version",
    )
    complete = all(
        isinstance(evidence.environment.get(key), str)
        and bool(evidence.environment[key].strip())
        for key in required
    )
    if evidence.scenario == "ianygo-bluetooth":
        complete = complete and (
            isinstance(evidence.environment.get("bluetooth_adapter"), str)
            and bool(evidence.environment["bluetooth_adapter"].strip())
        )
    return complete


def _derive_verdict(
    evidence: ProbeEvidence,
    validation_usb: AppleUsbEvidence,
) -> tuple[str, str]:
    eligible = evidence.eligible_location_records
    in_range = [
        record
        for record in eligible
        if _distance_metres(
            evidence.expected_latitude,
            evidence.expected_longitude,
            float(record["latitude"]),
            float(record["longitude"]),
        )
        <= evidence.horizontal_tolerance_m
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
    manifest_usb_present = (
        evidence.connection.get("windows_apple_usb_status") == "present"
        or evidence.connection.get("windows_apple_usb_device_count", 0) > 0
    )
    validation_usb_present = (
        validation_usb.status == "present" or validation_usb.device_count > 0
    )
    usb_complete = evidence.scenario != "ianygo-bluetooth" or (
        evidence.connection.get("user_confirmed_usb_disconnected") is True
        and evidence.connection.get("windows_apple_usb_status") == "absent"
        and evidence.connection.get("windows_apple_usb_device_count") == 0
        and validation_usb.status == "absent"
        and validation_usb.device_count == 0
    )
    environment_complete = _environment_complete(evidence)
    capture_environment_complete = all(
        isinstance(evidence.capture.get(key), str)
        and bool(evidence.capture[key].strip())
        for key in ("ios_version", "source_probe_build")
    )
    environment_matches = (
        evidence.capture.get("ios_version") == evidence.environment.get("ios_version")
        and evidence.capture.get("source_probe_build")
        == evidence.environment.get("source_probe_build")
    )
    common_complete = (
        len(evidence.eligible_callbacks) >= evidence.minimum_callback_count
        and len(in_range) == len(eligible)
        and source_complete
        and usb_complete
        and environment_complete
        and capture_environment_complete
        and environment_matches
    )
    if common_complete and attributed:
        return "pass", "accessory-attribution-confirmed"
    if common_complete and not_attributed:
        return "fail", "accessory-attribution-not-observed"

    if (
        len(evidence.eligible_callbacks) < evidence.minimum_callback_count
        and len(evidence.post_stabilization_callbacks)
        >= evidence.minimum_callback_count
        and evidence.stale_post_stabilization_callbacks
    ):
        reason = "stale-samples"
    elif len(evidence.eligible_callbacks) < evidence.minimum_callback_count:
        reason = "insufficient-callbacks"
    elif not environment_complete or not capture_environment_complete:
        reason = "environment-incomplete"
    elif not environment_matches:
        reason = "environment-mismatch"
    elif len(in_range) != len(eligible):
        reason = "expected-location-inactive"
    elif evidence.scenario == "ianygo-bluetooth" and (
        manifest_usb_present or validation_usb_present
    ):
        reason = "apple-usb-present"
    elif evidence.scenario == "ianygo-bluetooth" and (
        evidence.connection.get("windows_apple_usb_status") != "absent"
        or validation_usb.status != "absent"
    ):
        reason = "apple-usb-status-unknown"
    elif (
        evidence.scenario == "ianygo-bluetooth"
        and evidence.connection.get("user_confirmed_usb_disconnected") is not True
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
    return "inconclusive", reason


def validate_files(
    manifest_path: Path,
    jsonl_path: Path,
    usb_detector: Optional[Callable[[], AppleUsbEvidence]] = None,
) -> ProbeResult:
    """Validate an artifact pair and return a deterministic Probe Verdict."""

    evidence = load_evidence(manifest_path, jsonl_path)
    validation_usb = _validation_usb(evidence.scenario, usb_detector)
    verdict, reason = _derive_verdict(evidence, validation_usb)
    return ProbeResult(
        session_id=evidence.session_id,
        scenario=evidence.scenario,
        verdict=verdict,
        reason_codes=(reason,),
        total_location_records=len(evidence.location_records),
        eligible_location_records=len(evidence.eligible_location_records),
        total_callback_count=evidence.callback_count,
        eligible_callback_count=len(evidence.eligible_callbacks),
        validation_apple_usb_status=validation_usb.status,
        validation_apple_usb_device_count=validation_usb.device_count,
    )
