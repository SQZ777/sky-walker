"""Derive an evidence-based verdict from Source Probe artifacts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from sky_walker.accessory_probe import (
    SCHEMA_VERSION,
    Scenario,
    ScenarioDefinition,
    scenario_definition,
)
from sky_walker.accessory_probe.ble_trace import assess_ble_trace
from sky_walker.accessory_probe.errors import ProbeInputError
from sky_walker.accessory_probe.evidence import (
    LocationObservation,
    ProbeEvidence,
    load_evidence,
)
from sky_walker.accessory_probe.usb import AppleUsbEvidence
from sky_walker.accessory_probe.verdict import ProbeReason, ProbeVerdict


@dataclass(frozen=True)
class ProbeResult:
    session_id: str
    scenario: str
    verdict: ProbeVerdict
    reason_codes: Sequence[ProbeReason]
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
            "verdict": self.verdict.value,
            "reason_codes": [reason.value for reason in self.reason_codes],
            "total_location_records": self.total_location_records,
            "eligible_location_records": self.eligible_location_records,
            "total_callback_count": self.total_callback_count,
            "eligible_callback_count": self.eligible_callback_count,
            "validation_apple_usb_status": self.validation_apple_usb_status,
            "validation_apple_usb_device_count": self.validation_apple_usb_device_count,
        }


@dataclass(frozen=True)
class _CallbackAssessment:
    fresh_count: int
    post_stabilization_count: int
    has_stale_callbacks: bool
    fresh_run: int
    in_range_run: int
    source_run: int
    accessory_run: int
    non_accessory_run: int


@dataclass(frozen=True)
class _SessionAssessment:
    usb_complete: bool
    manifest_usb_present: bool
    validation_usb_present: bool
    environment_complete: bool
    capture_environment_complete: bool
    environment_matches: bool
    capture_within_limit: bool


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
    scenario: ScenarioDefinition,
    detector: Optional[Callable[[], AppleUsbEvidence]],
) -> AppleUsbEvidence:
    if not scenario.requires_usb_disconnection:
        return AppleUsbEvidence(status="not-required", device_count=0)
    if detector is None:
        return AppleUsbEvidence(status="error", device_count=0)
    try:
        return detector()
    except Exception:
        return AppleUsbEvidence(status="error", device_count=0)


def _environment_complete(evidence: ProbeEvidence) -> bool:
    required_values = (
        evidence.environment.ios_version,
        evidence.environment.source_probe_build,
        evidence.environment.windows_version,
        evidence.environment.location_product_version,
    )
    complete = all(
        isinstance(value, str) and bool(value.strip()) for value in required_values
    )
    if scenario_definition(evidence.scenario).requires_usb_disconnection:
        complete = complete and (
            isinstance(evidence.environment.bluetooth_adapter, str)
            and bool(evidence.environment.bluetooth_adapter.strip())
        )
    return complete


def _longest_consecutive_run(values: Sequence[int]) -> int:
    longest = 0
    current = 0
    previous: Optional[int] = None
    for value in sorted(values):
        current = current + 1 if previous is not None and value == previous + 1 else 1
        longest = max(longest, current)
        previous = value
    return longest


def _matching_callbacks(
    evidence: ProbeEvidence,
    predicate: Callable[[LocationObservation], bool],
) -> Sequence[int]:
    by_callback: Dict[int, List[LocationObservation]] = {}
    for record in evidence.eligible_location_records:
        by_callback.setdefault(record.callback_sequence, []).append(record)
    fresh_callbacks = (
        evidence.eligible_callbacks - evidence.stale_post_stabilization_callbacks
    )
    return tuple(
        callback
        for callback in fresh_callbacks
        if callback in by_callback
        and all(predicate(record) for record in by_callback[callback])
    )


def _assess_callbacks(evidence: ProbeEvidence) -> _CallbackAssessment:
    def in_range(record: LocationObservation) -> bool:
        return _distance_metres(
            evidence.expected_latitude,
            evidence.expected_longitude,
            record.latitude,
            record.longitude,
        ) <= evidence.horizontal_tolerance_m

    def source_complete(record: LocationObservation) -> bool:
        return (
            in_range(record)
            and record.source_information_present is True
            and isinstance(record.is_simulated_by_software, bool)
            and isinstance(record.is_produced_by_accessory, bool)
        )

    fresh_callbacks = tuple(
        evidence.eligible_callbacks - evidence.stale_post_stabilization_callbacks
    )
    return _CallbackAssessment(
        fresh_count=len(fresh_callbacks),
        post_stabilization_count=len(evidence.post_stabilization_callbacks),
        has_stale_callbacks=bool(evidence.stale_post_stabilization_callbacks),
        fresh_run=_longest_consecutive_run(fresh_callbacks),
        in_range_run=_longest_consecutive_run(
            _matching_callbacks(evidence, in_range)
        ),
        source_run=_longest_consecutive_run(
            _matching_callbacks(evidence, source_complete)
        ),
        accessory_run=_longest_consecutive_run(
            _matching_callbacks(
                evidence,
                lambda record: source_complete(record)
                and record.is_produced_by_accessory is True,
            )
        ),
        non_accessory_run=_longest_consecutive_run(
            _matching_callbacks(
                evidence,
                lambda record: source_complete(record)
                and record.is_produced_by_accessory is False,
            )
        ),
    )


def _assess_session(
    evidence: ProbeEvidence,
    validation_usb: AppleUsbEvidence,
) -> _SessionAssessment:
    scenario = scenario_definition(evidence.scenario)
    return _SessionAssessment(
        usb_complete=not scenario.requires_usb_disconnection
        or (
            evidence.connection.user_confirmed_usb_disconnected is True
            and evidence.connection.windows_apple_usb_status == "absent"
            and evidence.connection.windows_apple_usb_device_count == 0
            and validation_usb.status == "absent"
            and validation_usb.device_count == 0
        ),
        manifest_usb_present=(
            evidence.connection.windows_apple_usb_status == "present"
            or evidence.connection.windows_apple_usb_device_count > 0
        ),
        validation_usb_present=(
            validation_usb.status == "present" or validation_usb.device_count > 0
        ),
        environment_complete=_environment_complete(evidence),
        capture_environment_complete=all(
            isinstance(value, str) and bool(value.strip())
            for value in (
                evidence.capture_ios_version,
                evidence.capture_source_probe_build,
            )
        ),
        environment_matches=(
            evidence.capture_ios_version == evidence.environment.ios_version
            and evidence.capture_source_probe_build
            == evidence.environment.source_probe_build
        ),
        capture_within_limit=(
            evidence.capture_stopped - evidence.capture_started
        ).total_seconds()
        <= evidence.maximum_capture_seconds,
    )


def _derive_verdict(
    evidence: ProbeEvidence,
    validation_usb: AppleUsbEvidence,
    transport_reason: Optional[ProbeReason] = None,
) -> tuple[ProbeVerdict, ProbeReason]:
    scenario = scenario_definition(evidence.scenario)
    callbacks = _assess_callbacks(evidence)
    session = _assess_session(evidence, validation_usb)
    environment_and_transport_complete = (
        session.usb_complete
        and session.environment_complete
        and session.capture_environment_complete
        and session.environment_matches
        and transport_reason is None
        and session.capture_within_limit
    )
    if (
        environment_and_transport_complete
        and callbacks.accessory_run >= evidence.minimum_callback_count
    ):
        return (
            ProbeVerdict.PASS,
            ProbeReason.ACCESSORY_ATTRIBUTION_CONFIRMED,
        )
    if (
        environment_and_transport_complete
        and callbacks.non_accessory_run >= evidence.minimum_callback_count
    ):
        return (
            ProbeVerdict.FAIL,
            ProbeReason.ACCESSORY_ATTRIBUTION_NOT_OBSERVED,
        )

    if (
        callbacks.fresh_count >= evidence.minimum_callback_count
        and callbacks.fresh_run < evidence.minimum_callback_count
    ):
        reason = ProbeReason.NONCONSECUTIVE_CALLBACKS
    elif (
        callbacks.fresh_count < evidence.minimum_callback_count
        and callbacks.post_stabilization_count >= evidence.minimum_callback_count
        and callbacks.has_stale_callbacks
    ):
        reason = ProbeReason.STALE_SAMPLES
    elif callbacks.fresh_count < evidence.minimum_callback_count:
        reason = ProbeReason.INSUFFICIENT_CALLBACKS
    elif not session.capture_within_limit:
        reason = ProbeReason.CAPTURE_DURATION_EXCEEDED
    elif (
        not session.environment_complete
        or not session.capture_environment_complete
    ):
        reason = ProbeReason.ENVIRONMENT_INCOMPLETE
    elif not session.environment_matches:
        reason = ProbeReason.ENVIRONMENT_MISMATCH
    elif callbacks.in_range_run < evidence.minimum_callback_count:
        reason = ProbeReason.EXPECTED_LOCATION_INACTIVE
    elif transport_reason is not None:
        reason = transport_reason
    elif scenario.requires_usb_disconnection and (
        session.manifest_usb_present or session.validation_usb_present
    ):
        reason = ProbeReason.APPLE_USB_PRESENT
    elif scenario.requires_usb_disconnection and (
        evidence.connection.windows_apple_usb_status != "absent"
        or validation_usb.status != "absent"
    ):
        reason = ProbeReason.APPLE_USB_STATUS_UNKNOWN
    elif (
        scenario.requires_usb_disconnection
        and evidence.connection.user_confirmed_usb_disconnected is not True
    ):
        reason = ProbeReason.USB_DISCONNECTION_UNCONFIRMED
    elif callbacks.source_run < evidence.minimum_callback_count:
        reason = ProbeReason.SOURCE_INFORMATION_MISSING
    elif (
        callbacks.accessory_run < evidence.minimum_callback_count
        and callbacks.non_accessory_run < evidence.minimum_callback_count
    ):
        reason = ProbeReason.MIXED_ACCESSORY_FLAGS
    else:
        reason = ProbeReason.EVIDENCE_INCOMPLETE
    return ProbeVerdict.INCONCLUSIVE, reason


def validate_files(
    manifest_path: Path,
    jsonl_path: Path,
    usb_detector: Optional[Callable[[], AppleUsbEvidence]] = None,
    ble_trace_path: Optional[Path] = None,
) -> ProbeResult:
    """Validate an artifact pair and return a deterministic Probe Verdict."""

    evidence = load_evidence(manifest_path, jsonl_path)
    scenario = scenario_definition(evidence.scenario)
    transport_reason: Optional[ProbeReason] = None
    if scenario.scenario is Scenario.SKY_WALKER_BLE_LNS:
        if ble_trace_path is None:
            validation_usb = AppleUsbEvidence(status="error", device_count=0)
            transport_reason = ProbeReason.BLE_TRACE_MISSING
        else:
            assessment = assess_ble_trace(ble_trace_path, evidence)
            validation_usb = assessment.usb_evidence
            transport_reason = assessment.reason
    else:
        validation_usb = _validation_usb(scenario, usb_detector)
    verdict, reason = _derive_verdict(
        evidence,
        validation_usb,
        transport_reason=transport_reason,
    )
    return ProbeResult(
        session_id=evidence.session_id,
        scenario=evidence.scenario.value,
        verdict=verdict,
        reason_codes=(reason,),
        total_location_records=len(evidence.location_records),
        eligible_location_records=len(evidence.eligible_location_records),
        total_callback_count=evidence.callback_count,
        eligible_callback_count=len(evidence.eligible_callbacks),
        validation_apple_usb_status=validation_usb.status,
        validation_apple_usb_device_count=validation_usb.device_count,
    )
