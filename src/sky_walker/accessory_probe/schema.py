"""Runtime validation against the packaged Accessory Probe JSON Schemas."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from sky_walker.accessory_probe.errors import ProbeInputError


@lru_cache(maxsize=2)
def _validator(filename: str) -> Draft202012Validator:
    schema_resource = resources.files("sky_walker.accessory_probe").joinpath(
        "schemas", filename
    )
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate(document: Dict[str, Any], filename: str, label: str) -> None:
    errors = sorted(
        _validator(filename).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return
    error = _most_relevant_error(errors, document)
    path = ".".join(str(part) for part in error.absolute_path)
    location = f" at {path}" if path else ""
    raise ProbeInputError(f"{label}{location}: {error.message}")


def _most_relevant_error(errors: Iterable[Any], document: Dict[str, Any]) -> Any:
    """Prefer the schema branch selected by a record's discriminator.

    ``jsonschema`` reports a root ``oneOf`` failure when one JSONL record is
    malformed. Its default message hides the useful leaf error among all the
    failures from the unrelated record branch. Select the capture/location
    branch before presenting the error to an operator.
    """

    errors = list(errors)
    if len(errors) != 1 or errors[0].validator != "oneOf":
        return errors[0]

    branch_by_record_type = {"capture": 0, "location": 1}
    record_type = document.get("record_type")
    branch = (
        branch_by_record_type.get(record_type)
        if isinstance(record_type, str)
        else None
    )
    if branch is None:
        return errors[0]

    candidates = []
    for error in errors[0].context:
        schema_path = list(error.absolute_schema_path)
        if len(schema_path) >= 2 and schema_path[:2] == ["oneOf", branch]:
            candidates.append(error)
    return candidates[0] if candidates else errors[0]


def validate_manifest_schema(document: Dict[str, Any]) -> None:
    _validate(
        document,
        "accessory-probe-manifest-v1.schema.json",
        "manifest",
    )


def validate_record_schema(document: Dict[str, Any], label: str) -> None:
    _validate(
        document,
        "accessory-probe-record-v1.schema.json",
        label,
    )
