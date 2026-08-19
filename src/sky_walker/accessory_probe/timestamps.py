"""Shared timestamp parsing for correlated probe artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sky_walker.accessory_probe.errors import ProbeInputError


def parse_timestamp(value: Any, context: str) -> datetime:
    if not isinstance(value, str):
        raise ProbeInputError(f"{context} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProbeInputError(f"{context} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ProbeInputError(f"{context} must include a timezone")
    return parsed
