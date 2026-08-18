"""Published JSON Schemas agree with de-identified v1 fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).parents[1]
SCHEMAS = ROOT / "docs" / "schemas"
FIXTURES = Path(__file__).parent / "fixtures" / "accessory_probe"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_fixture_matches_published_schema():
    schema = _load(SCHEMAS / "accessory-probe-manifest-v1.schema.json")
    Draft202012Validator.check_schema(schema)

    Draft202012Validator(schema).validate(
        _load(FIXTURES / "pass.manifest.json")
    )


def test_every_jsonl_fixture_record_matches_published_schema():
    schema = _load(SCHEMAS / "accessory-probe-record-v1.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    for line in (FIXTURES / "pass.jsonl").read_text(encoding="utf-8").splitlines():
        validator.validate(json.loads(line))
