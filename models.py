import json
from pathlib import Path

from jsonschema import validate


SCHEMA_DIR = Path(__file__).resolve().parent / "schema"

with (SCHEMA_DIR / "checklist.schema.json").open() as f:
    CHECKLIST_SCHEMA = json.load(f)

with (SCHEMA_DIR / "finding.schema.json").open() as f:
    FINDING_SCHEMA = json.load(f)

with (SCHEMA_DIR / "session.schema.json").open() as f:
    SESSION_SCHEMA = json.load(f)

def validate_checklist(data):

    validate(instance=data, schema=CHECKLIST_SCHEMA)


def validate_finding(data):

    validate(instance=data, schema=FINDING_SCHEMA)


def validate_findings(data):

    if not isinstance(data, list):
        raise ValueError("findings must be an array")

    for finding in data:
        validate_finding(finding)


def validate_session(data):

    validate(instance=data, schema=SESSION_SCHEMA)
