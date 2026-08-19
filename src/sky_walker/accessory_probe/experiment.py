"""Summarize the bounded BLE LNS hypothesis across preserved verdicts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Sequence, Tuple

from sky_walker.accessory_probe import SCHEMA_VERSION, Scenario
from sky_walker.accessory_probe.errors import ProbeInputError


@dataclass(frozen=True)
class Attempt:
    session_id: str
    verdict: str
    reason_codes: Tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "verdict": self.verdict,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ExperimentSummary:
    experiment_verdict: str
    reason: str
    attempts: Tuple[Attempt, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "experiment": "ble-lns-accessory-attribution",
            "experiment_verdict": self.experiment_verdict,
            "reason_codes": [self.reason],
            "attempt_count": len(self.attempts),
            "attempts": [attempt.as_dict() for attempt in self.attempts],
        }


def _load_attempt(path: Path) -> Attempt:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeInputError(f"cannot read verdict {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ProbeInputError(f"verdict {path} must be a JSON object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ProbeInputError(f"verdict {path} has unsupported schema_version")
    session_id = document.get("session_id")
    if not isinstance(session_id, str) or re.fullmatch(
        r"[A-Z2-9]{8}", session_id
    ) is None:
        raise ProbeInputError(f"verdict {path} has an invalid session_id")
    if document.get("scenario") != Scenario.SKY_WALKER_BLE_LNS.value:
        raise ProbeInputError(f"verdict {path} is not a BLE LNS attempt")
    verdict = document.get("verdict")
    if verdict not in {"pass", "fail", "inconclusive"}:
        raise ProbeInputError(f"verdict {path} has an invalid verdict")
    reason_codes = document.get("reason_codes")
    if (
        not isinstance(reason_codes, list)
        or not reason_codes
        or any(not isinstance(reason, str) or not reason for reason in reason_codes)
    ):
        raise ProbeInputError(f"verdict {path} has invalid reason_codes")
    if verdict == "pass" and "accessory-attribution-confirmed" not in reason_codes:
        raise ProbeInputError(f"pass verdict {path} lacks strict attribution evidence")
    return Attempt(
        session_id=session_id,
        verdict=verdict,
        reason_codes=tuple(reason_codes),
    )


def summarize_attempts(paths: Sequence[Path]) -> ExperimentSummary:
    if not 1 <= len(paths) <= 3:
        raise ProbeInputError("BLE LNS summary requires one to three verdict files")
    attempts = tuple(_load_attempt(path) for path in paths)
    session_ids = {attempt.session_id for attempt in attempts}
    if len(session_ids) != len(attempts):
        raise ProbeInputError("BLE LNS attempts must have distinct session IDs")
    if any(attempt.verdict == "pass" for attempt in attempts):
        return ExperimentSummary(
            experiment_verdict="confirmed",
            reason="strict-pass-observed",
            attempts=attempts,
        )
    if len(attempts) == 3:
        return ExperimentSummary(
            experiment_verdict="rejected",
            reason="three-attempts-without-pass",
            attempts=attempts,
        )
    return ExperimentSummary(
        experiment_verdict="inconclusive",
        reason="more-attempts-required",
        attempts=attempts,
    )
