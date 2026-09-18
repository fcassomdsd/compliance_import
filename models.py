import json
from pathlib import Path

from jsonschema import FormatChecker, validate


SCHEMA_DIR = Path(__file__).resolve().parent / "schema"

# jsonschema does not enforce a schema's "format" keywords (date/date-time) unless a
# format checker is passed explicitly. Without this, a payload carrying e.g.
# startDate "NOT-A-DATE" validates clean and reaches Alfresco as a malformed date.
_format_checker = FormatChecker()

_schemas = None


def _load_schemas():
    global _schemas
    if _schemas is not None:
        return _schemas

    try:
        _schemas = {
            "checklist": json.loads(
                (SCHEMA_DIR / "checklist.schema.json").read_text(encoding="utf-8")
            ),
            "finding": json.loads(
                (SCHEMA_DIR / "finding.schema.json").read_text(encoding="utf-8")
            ),
            "followup_report": json.loads(
                (SCHEMA_DIR / "followup-report.schema.json").read_text(encoding="utf-8")
            ),
            "followup_source_finding": json.loads(
                (SCHEMA_DIR / "followup-source-finding.schema.json").read_text(encoding="utf-8")
            ),
        }
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Failed to load JSON schema from {SCHEMA_DIR}: {exc}"
        ) from exc

    return _schemas


def validate_checklist(data):
    validate(instance=data, schema=_load_schemas()["checklist"], format_checker=_format_checker)


def validate_finding(data):
    validate(instance=data, schema=_load_schemas()["finding"], format_checker=_format_checker)


def validate_findings(data):
    if not isinstance(data, list):
        raise ValueError("findings must be an array")

    for finding in data:
        validate_finding(finding)


def validate_followup_reports(data):
    if not isinstance(data, list):
        raise ValueError("followup-reports.json must be an array")

    for report in data:
        validate(instance=report, schema=_load_schemas()["followup_report"], format_checker=_format_checker)


def validate_followup_source_findings(data):
    if not isinstance(data, list):
        raise ValueError("findings.json must be an array in follow-up payload")

    for finding in data:
        if isinstance(finding, dict) and isinstance(finding.get("finding"), dict):
            validate(instance=finding["finding"], schema=_load_schemas()["followup_source_finding"], format_checker=_format_checker)
            continue

        validate(instance=finding, schema=_load_schemas()["followup_source_finding"], format_checker=_format_checker)
