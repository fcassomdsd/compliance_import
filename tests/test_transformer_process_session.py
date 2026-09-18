import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema.exceptions import ValidationError
from id_utils import build_corrective_action_id, build_finding_id

from transformer import process_followup_payload, process_inspection
from tests.support.fake_alfresco_client import FakeAlfrescoClient


INSPECTION_CODE = "MDPP-I-0001"
SPECIALTY_CODE = "SUR"
FINDING_ID = build_finding_id(INSPECTION_CODE, SPECIALTY_CODE, 1)
CAP_ID = build_corrective_action_id(FINDING_ID, 1)
CAP_ID_MISMATCH = build_corrective_action_id(FINDING_ID, 2)


class ProcessInspectionPayloadTests(unittest.TestCase):

    def setUp(self):
        FakeAlfrescoClient.instances = []

    def _write_json(self, parent, filename, payload):
        file_path = Path(parent) / filename
        file_path.write_text(json.dumps(payload), encoding="utf-8")

    def test_process_inspection_imports_explicit_findings(self):
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "inspection-1",
                "inspectionCode": INSPECTION_CODE,
                "locationId": "location-1",
                "locationName": "Aeropuerto",
                "locationCode": "MDPP",
                "specialtyId": "specialty-1",
                "specialtyCode": SPECIALTY_CODE,
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "SUR-0001",
                    "requirement": "Question text from checklist",
                    "compliance": "Non-compliant",
                }
            ],
        }

        findings = [
            {
                "schemaVersion": "1.0",
                "finding": {
                    "findingId": FINDING_ID,
                    "specialtyId": "specialty-1",
                    "specialtyCode": SPECIALTY_CODE,
                    "specialtyName": "Vigilancia",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Aeropuerto",
                    "checklistItemCode": "SUR-0001",
                    "description": "Generated finding description",
                    "findingLevel": "Observation"
                }
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_json(tmpdir, "checklist.json", checklist)
            self._write_json(tmpdir, "findings.json", findings)

            with patch("transformer.AlfrescoClient", FakeAlfrescoClient):
                result = process_inspection(tmpdir)

        self.assertEqual("inspection-1", result["inspectionId"])
        self.assertEqual(1, result["findingsImported"])
        self.assertEqual(0, result["evidenceImported"])

        client = FakeAlfrescoClient.instances[0]
        self.assertEqual(1, len(client.checklists))
        self.assertEqual(1, len(client.findings))

        finding = client.findings[0]["finding"]
        self.assertEqual("Observation", finding["findingLevel"])
        self.assertEqual("Question text from checklist", finding["requirementBreached"])
        self.assertEqual("SUR-0001", finding["checklistItemCode"])

    def test_process_inspection_rejects_invalid_finding_schema(self):
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "inspection-1",
                "inspectionCode": INSPECTION_CODE,
                "locationId": "location-1",
                "locationName": "Aeropuerto",
                "locationCode": "MDPP",
                "specialtyId": "specialty-1",
                "specialtyCode": SPECIALTY_CODE,
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "SUR-0001",
                    "requirement": "Question text from checklist",
                    "compliance": "Non-compliant",
                }
            ],
        }

        invalid_findings = [
            {
                "schemaVersion": "1.0",
                "finding": {
                    "findingId": FINDING_ID,
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Aeropuerto",
                    "description": "Missing checklistItemCode"
                }
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_json(tmpdir, "checklist.json", checklist)
            self._write_json(tmpdir, "findings.json", invalid_findings)

            with patch("transformer.AlfrescoClient", FakeAlfrescoClient):
                with self.assertRaises(ValidationError):
                    process_inspection(tmpdir)


class ProcessFollowupPayloadTests(unittest.TestCase):

    def setUp(self):
        FakeAlfrescoClient.instances = []

    def _write_json(self, parent, filename, payload):
        file_path = Path(parent) / filename
        file_path.write_text(json.dumps(payload), encoding="utf-8")

    def test_process_followup_payload_imports_reports_and_evidence(self):
        findings = [
            {
                "findingId": FINDING_ID,
                "specialtyId": "specialty-1",
                "specialtyCode": SPECIALTY_CODE,
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
                "locationId": "location-1",
                "locationCode": "MDPP",
                "locationName": "Location",
                "checklistItemCode": "SUR-0001",
                "description": "desc",
                "correctiveAction": {
                    "capId": CAP_ID
                }
            }
        ]

        reports = [
            {
                "schemaVersion": "1.0",
                "followUpReport": {
                    "findingId": FINDING_ID,
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Location",
                    "followUpDate": "2026-04-14T15:36:28.825Z",
                    "percentComplete": 30,
                    "effectivenessConfirmed": False,
                    "specialtyId": "specialty-1",
                    "capId": CAP_ID,
                    "evidenceItems": [
                        {
                            "evidenceId": "FUEV-0001-01",
                            "evidenceType": "document",
                            "source": "proof.pdf"
                        }
                    ]
                }
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_json(tmpdir, "prior-findings.json", findings)
            self._write_json(tmpdir, "followup-reports.json", reports)

            evidence_dir = Path(tmpdir) / "FollowUpEvidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / "proof.pdf").write_text("binary-content", encoding="utf-8")

            with patch("transformer.AlfrescoClient", FakeAlfrescoClient):
                result = process_followup_payload(tmpdir)

        self.assertEqual(1, result["followUpReportsImported"])
        self.assertEqual(1, result["followUpEvidenceImported"])
        self.assertEqual([f"FollowUp {FINDING_ID} 01.json"], result["followUpFilenames"])

        client = FakeAlfrescoClient.instances[0]
        self.assertEqual(1, len(client.followup_reports))
        self.assertEqual(1, len(client.followup_evidence))

    def test_process_followup_payload_backfills_missing_report_cap_id(self):
        findings = [
            {
                "findingId": FINDING_ID,
                "specialtyId": "specialty-1",
                "specialtyCode": SPECIALTY_CODE,
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
                "locationId": "location-1",
                "locationCode": "MDPP",
                "locationName": "Location",
                "checklistItemCode": "SUR-0001",
                "description": "desc",
                "correctiveAction": {
                    "capId": CAP_ID
                }
            }
        ]

        reports = [
            {
                "schemaVersion": "1.0",
                "followUpReport": {
                    "findingId": FINDING_ID,
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Location",
                    "followUpDate": "2026-04-14T15:36:28.825Z",
                    "percentComplete": 30,
                    "effectivenessConfirmed": False,
                    "specialtyId": "specialty-1",
                    "evidenceItems": []
                }
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_json(tmpdir, "prior-findings.json", findings)
            self._write_json(tmpdir, "followup-reports.json", reports)

            evidence_dir = Path(tmpdir) / "FollowUpEvidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)

            with patch("transformer.AlfrescoClient", FakeAlfrescoClient):
                result = process_followup_payload(tmpdir)

        self.assertEqual(1, result["followUpReportsImported"])
        self.assertEqual(0, result["followUpEvidenceImported"])
        self.assertEqual([f"FollowUp {FINDING_ID} 01.json"], result["followUpFilenames"])
        client = FakeAlfrescoClient.instances[0]
        imported_report = client.followup_reports[0][1]
        self.assertEqual(CAP_ID, imported_report["followUpReport"]["capId"])

    def test_process_followup_payload_rejects_cap_mismatch(self):
        findings = [
            {
                "findingId": FINDING_ID,
                "specialtyId": "specialty-1",
                "specialtyCode": SPECIALTY_CODE,
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
                "locationId": "location-1",
                "locationCode": "MDPP",
                "locationName": "Location",
                "checklistItemCode": "SUR-0001",
                "description": "desc",
                "correctiveAction": {
                    "capId": CAP_ID_MISMATCH
                }
            }
        ]

        reports = [
            {
                "schemaVersion": "1.0",
                "followUpReport": {
                    "findingId": FINDING_ID,
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Location",
                    "followUpDate": "2026-04-14T15:36:28.825Z",
                    "percentComplete": 30,
                    "effectivenessConfirmed": False,
                    "specialtyId": "specialty-1",
                    "capId": CAP_ID,
                    "evidenceItems": []
                }
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_json(tmpdir, "prior-findings.json", findings)
            self._write_json(tmpdir, "followup-reports.json", reports)

            evidence_dir = Path(tmpdir) / "FollowUpEvidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)

            with patch("transformer.AlfrescoClient", FakeAlfrescoClient):
                with self.assertRaises(ValueError):
                    process_followup_payload(tmpdir)

    def test_process_followup_payload_accepts_wrapped_source_findings(self):
        findings = [
            {
                "schemaVersion": "1.0",
                "finding": {
                    "findingId": FINDING_ID,
                    "specialtyId": "specialty-1",
                    "specialtyCode": SPECIALTY_CODE,
                    "specialtyName": "Vigilancia",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationCode": "MDPP",
                    "locationName": "Location",
                    "checklistItemCode": "SUR-0001",
                    "description": "desc",
                    "correctiveAction": {
                        "capId": CAP_ID
                    }
                }
            }
        ]

        reports = [
            {
                "schemaVersion": "1.0",
                "followUpReport": {
                    "findingId": FINDING_ID,
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Location",
                    "followUpDate": "2026-04-14T15:36:28.825Z",
                    "percentComplete": 30,
                    "effectivenessConfirmed": False,
                    "specialtyId": "specialty-1",
                    "capId": CAP_ID,
                    "evidenceItems": []
                }
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_json(tmpdir, "prior-findings.json", findings)
            self._write_json(tmpdir, "followup-reports.json", reports)

            evidence_dir = Path(tmpdir) / "FollowUpEvidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)

            with patch("transformer.AlfrescoClient", FakeAlfrescoClient):
                result = process_followup_payload(tmpdir)

        self.assertEqual(1, result["followUpReportsImported"])
        self.assertEqual(0, result["followUpEvidenceImported"])
        self.assertEqual([f"FollowUp {FINDING_ID} 01.json"], result["followUpFilenames"])


class FailingFindingWriteClient(FakeAlfrescoClient):
    """Fake client whose second write fails, to exercise batch compensation."""

    def store_finding_document(self, finding):
        raise RuntimeError("Alfresco request failed (502)")


class BatchCompensationTests(unittest.TestCase):

    def setUp(self):
        FakeAlfrescoClient.instances = []
        FailingFindingWriteClient.instances = []

    def test_failed_inspection_write_rolls_the_batch_back(self):
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "inspection-rollback",
                "inspectionCode": INSPECTION_CODE,
                "locationId": "location-1",
                "locationName": "Aeropuerto",
                "locationCode": "MDPP",
                "specialtyId": "specialty-1",
                "specialtyCode": SPECIALTY_CODE,
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "SUR-0001",
                    "requirement": "Question text from checklist",
                    "compliance": "Non-compliant",
                }
            ],
        }
        findings = [
            {
                "schemaVersion": "1.0",
                "finding": {
                    "findingId": FINDING_ID,
                    "specialtyId": "specialty-1",
                    "specialtyCode": SPECIALTY_CODE,
                    "specialtyName": "Vigilancia",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Aeropuerto",
                    "checklistItemCode": "SUR-0001",
                    "description": "Generated finding description",
                    "findingLevel": "Observation",
                }
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "checklist.json").write_text(json.dumps(checklist), encoding="utf-8")
            Path(tmpdir, "findings.json").write_text(json.dumps(findings), encoding="utf-8")

            with patch("transformer.AlfrescoClient", FailingFindingWriteClient):
                with self.assertRaises(RuntimeError):
                    process_inspection(tmpdir)

        client = FakeAlfrescoClient.instances[-1]
        self.assertEqual(1, client.rollback_count, "the failed batch should be compensated")
        self.assertFalse(client.batch_active)


if __name__ == "__main__":
    unittest.main()
