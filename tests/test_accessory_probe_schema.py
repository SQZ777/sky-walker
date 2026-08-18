"""Versioned manifest and JSONL contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sky_walker.accessory_probe.validator import ProbeInputError, validate_files


FIXTURES = Path(__file__).parent / "fixtures" / "accessory_probe"


def test_location_record_missing_required_measurement_is_invalid(tmp_path):
    manifest_path = FIXTURES / "pass.manifest.json"
    records = [
        json.loads(line)
        for line in (FIXTURES / "pass.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    records[-1].pop("course")
    jsonl_path = tmp_path / "missing-course.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(record) for record in records), encoding="utf-8"
    )

    with pytest.raises(ProbeInputError, match="course"):
        validate_files(manifest_path, jsonl_path)


def test_nil_source_marker_with_boolean_flags_is_invalid(tmp_path):
    manifest_path = FIXTURES / "pass.manifest.json"
    records = [
        json.loads(line)
        for line in (FIXTURES / "pass.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    records[-1]["source_information_present"] = False
    jsonl_path = tmp_path / "contradictory-source.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(record) for record in records), encoding="utf-8"
    )

    with pytest.raises(ProbeInputError, match="source information"):
        validate_files(manifest_path, jsonl_path)


def test_missing_environment_key_is_invalid(tmp_path):
    manifest = json.loads(
        (FIXTURES / "pass.manifest.json").read_text(encoding="utf-8")
    )
    manifest["environment"].pop("windows_version")
    manifest_path = tmp_path / "missing-environment-key.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ProbeInputError, match="windows_version"):
        validate_files(manifest_path, FIXTURES / "pass.jsonl")


def test_unknown_schema_version_is_invalid(tmp_path):
    manifest = json.loads(
        (FIXTURES / "pass.manifest.json").read_text(encoding="utf-8")
    )
    manifest["schema_version"] = 2
    manifest_path = tmp_path / "future.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ProbeInputError, match="unsupported schema_version"):
        validate_files(manifest_path, FIXTURES / "pass.jsonl")


def test_malformed_jsonl_is_invalid(tmp_path):
    jsonl_path = tmp_path / "malformed.jsonl"
    jsonl_path.write_text('{"schema_version": 1\n', encoding="utf-8")

    with pytest.raises(ProbeInputError, match="line 1"):
        validate_files(FIXTURES / "pass.manifest.json", jsonl_path)


@pytest.mark.parametrize("field", ["session_id", "scenario"])
def test_location_record_must_match_manifest(field, tmp_path):
    records = [
        json.loads(line)
        for line in (FIXTURES / "pass.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    records[-1][field] = "WRONG"
    jsonl_path = tmp_path / f"wrong-{field}.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(record) for record in records), encoding="utf-8"
    )

    with pytest.raises(ProbeInputError, match="does not match"):
        validate_files(FIXTURES / "pass.manifest.json", jsonl_path)


def test_manifest_requires_created_at(tmp_path):
    manifest = _manifest_fixture()
    manifest.pop("created_at")
    manifest_path = tmp_path / "missing-created-at.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ProbeInputError, match="created_at"):
        validate_files(manifest_path, FIXTURES / "pass.jsonl")


def test_capture_requires_stopped_at(tmp_path):
    records = _record_fixtures()
    records[0].pop("capture_stopped_at")
    jsonl_path = tmp_path / "missing-stopped-at.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(record) for record in records), encoding="utf-8"
    )

    with pytest.raises(ProbeInputError, match="capture_stopped_at"):
        validate_files(FIXTURES / "pass.manifest.json", jsonl_path)


def test_session_id_must_be_eight_safe_characters(tmp_path):
    manifest = _manifest_fixture()
    records = _record_fixtures()
    manifest["session_id"] = "SHORT"
    for record in records:
        record["session_id"] = "SHORT"
    manifest_path = tmp_path / "bad-id.manifest.json"
    jsonl_path = tmp_path / "bad-id.jsonl"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    jsonl_path.write_text(
        "\n".join(json.dumps(record) for record in records), encoding="utf-8"
    )

    with pytest.raises(ProbeInputError, match="session_id"):
        validate_files(manifest_path, jsonl_path)


def _manifest_fixture():
    return json.loads((FIXTURES / "pass.manifest.json").read_text(encoding="utf-8"))


def _record_fixtures():
    return [
        json.loads(line)
        for line in (FIXTURES / "pass.jsonl").read_text(encoding="utf-8").splitlines()
    ]
