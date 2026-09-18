"""Conformance tests for the shared, cross-repo domain-rule spec.

``domain-rules/nomenclatura.spec.json`` is vendored from compliance_cmis (the
canonical copy). These tests run the shared vectors against this service's id
builders, its severity baseline and its follow-up/closure schema, so any
implementation that drifts from the published rules fails here.

Keep the assertions vector-driven: add cases to the spec, not to this file.
"""

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema.exceptions import ValidationError

from domain_rules import (
    FOLLOW_UP_TYPES,
    SPEC,
    SPEC_PATH,
    SEVERITY_DAYS,
    closure_policy,
    normalize_follow_up_type,
)
from id_utils import (
    FINDING_ID_PATTERN,
    INSPECTION_CODE_PATTERN,
    build_checklist_id,
    build_corrective_action_id,
    build_finding_id,
    build_followup_id_seq,
)
from models import _load_schemas, validate_followup_reports

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = REPO_ROOT / "domain-rules" / "nomenclatura.spec.json"


def _build_report(follow_up_type, effectiveness_confirmed):
    return {
        "schemaVersion": "1.0",
        "followUpReport": {
            "findingId": "H-MDSDA0002-COM-001",
            "providerId": "provider-1",
            "locationId": "location-1",
            "locationName": "Location",
            "followUpDate": "2026-01-05",
            "percentComplete": 50,
            "effectivenessConfirmed": effectiveness_confirmed,
            "specialtyId": "specialty-1",
            "followUpType": follow_up_type,
        },
    }


class DomainRuleConformanceTests(unittest.TestCase):

    def test_vendored_spec_is_the_canonical_document(self):
        vendored = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
        self.assertEqual(vendored, SPEC)
        self.assertTrue(SPEC_PATH.samefile(SPEC_FILE))
        self.assertTrue(SPEC["version"])

    def test_id_patterns_are_loaded_verbatim_from_the_spec(self):
        self.assertEqual(INSPECTION_CODE_PATTERN.pattern, SPEC["ids"]["activity"]["inputPattern"])
        self.assertEqual(FINDING_ID_PATTERN.pattern, SPEC["ids"]["finding"]["pattern"])

    def test_builders_match_every_build_vector(self):
        builders = {
            "checklist": lambda input: build_checklist_id(input["activityCode"], input["specialtyCode"]),
            "finding": lambda input: build_finding_id(
                input["activityCode"], input["specialtyCode"], input["findingSequence"]
            ),
            "correctiveAction": lambda input: build_corrective_action_id(input["findingId"], input["sequence"]),
            "followUp": lambda input: build_followup_id_seq(input["findingId"], input["sequence"]),
        }

        # The shared build vectors carry the canonical activity code as an
        # explicit input where the builders take one.
        inputs = {
            "checklist": {
                "activityCode": "AV-MDSD-A-0002",
                "compactActivityCode": "MDSDA0002",
                "specialtyCode": "COM",
            },
            "finding": {
                "activityCode": "AV-MDSD-A-0002",
                "compactActivityCode": "MDSDA0002",
                "specialtyCode": "COM",
                "findingSequence": 1,
            },
        }

        for vector in SPEC["conformanceVectors"]["build"]:
            builder = builders.get(vector["id"])
            if builder is None:
                continue

            payload = {**vector["input"], **inputs.get(vector["id"], {})}
            self.assertEqual(builder(payload), vector["expected"], vector["id"])

    def test_invalid_activity_vectors_are_rejected(self):
        for vector in SPEC["conformanceVectors"]["invalid"]:
            if vector["id"] != "activity":
                continue

            with self.assertRaises(ValueError, msg=vector["value"]):
                build_checklist_id(vector["value"], "COM")

    def test_invalid_finding_vectors_are_rejected(self):
        for vector in SPEC["conformanceVectors"]["invalid"]:
            if vector["id"] != "finding":
                continue

            with self.assertRaises(ValueError, msg=vector["value"]):
                build_followup_id_seq(vector["value"], 1)

    def test_severity_baseline_matches_the_spec(self):
        expected = {level["id"]: level["daysToSolution"] for level in SPEC["severity"]["levels"]}
        self.assertEqual(SEVERITY_DAYS, expected)

        for vector in SPEC["conformanceVectors"]["severity"]:
            issued = datetime.fromisoformat(vector["baseDate"])
            deadline = issued + timedelta(days=SEVERITY_DAYS[vector["severity"]])
            self.assertEqual(deadline.date().isoformat(), vector["resolutionDeadline"])

    def test_follow_up_vocabulary_matches_the_spec(self):
        schema = _load_schemas()["followup_report"]
        enum = schema["properties"]["followUpReport"]["properties"]["followUpType"]["enum"]
        self.assertEqual(enum, list(FOLLOW_UP_TYPES))

        for vector in SPEC["conformanceVectors"]["followUpTypeNormalization"]:
            self.assertEqual(normalize_follow_up_type(vector["input"]), vector["expected"])

    def test_follow_up_schema_enforces_the_shared_closure_gate(self):
        for vector in SPEC["conformanceVectors"]["closureGate"]:
            report = _build_report(vector["followUpType"], vector["effectivenessConfirmed"])
            should_close, error = closure_policy(vector["followUpType"], vector["effectivenessConfirmed"])

            self.assertEqual(should_close, vector["shouldClose"], vector["followUpType"])
            self.assertEqual(bool(error), vector["error"], vector["followUpType"])

            if vector["error"]:
                with self.assertRaises(ValidationError, msg=vector):
                    validate_followup_reports([report])
            else:
                validate_followup_reports([report])


if __name__ == "__main__":
    unittest.main()
