import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema.exceptions import ValidationError

from transformer import process_followup_payload, process_inspection


class FakeAlfrescoClient:

    instances = []

    def __init__(self):
        self.checklists = []
        self.findings = []
        self.evidence = []
        self.followup_reports = []
        self.followup_evidence = []
        FakeAlfrescoClient.instances.append(self)

    def store_checklist_document(self, checklist):
        self.checklists.append(checklist)

    def store_finding_document(self, finding):
        self.findings.append(finding)

    def store_evidence_file(self, specialty_name, evidence_file):
        self.evidence.append((specialty_name, evidence_file.name))

    def store_followup_report_document(self, report, specialty_name):
        self.followup_reports.append((specialty_name, report))

    def store_followup_evidence_file(self, specialty_name, evidence_file):
        self.followup_evidence.append((specialty_name, evidence_file.name))


class ProcessInspectionSessionTests(unittest.TestCase):

    def setUp(self):
        FakeAlfrescoClient.instances = []

    def _write_json(self, parent, filename, payload):
        file_path = Path(parent) / filename
        file_path.write_text(json.dumps(payload), encoding="utf-8")

    def test_process_inspection_builds_findings_from_session(self):
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "inspection-1",
                "inspectionCode": "MDPP-2026-01",
                "locationId": "location-1",
                "locationName": "Aeropuerto",
                "icaoCode": "MDPP",
                "specialtyId": "specialty-1",
                "specialtyCode": "VIG",
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "VIG-0001",
                    "requirement": "Question text from checklist",
                    "compliance": "Non-compliant",
                }
            ],
        }

        session_data = {
            "summary": {
                "specialty": "Vigilancia",
                "lastUpdated": "2026-03-26T10:35:00.000Z",
            },
            "responses": {
                "item-1": {
                    "id": "item-1",
                    "compliance": "Non-compliant",
                    "comments": "fallback comments",
                    "nonConformityDetails": {
                        "description": "Generated finding description",
                        "riskLevel": "High",
                        "findingLevel": "Observation",
                    },
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_json(tmpdir, "checklist.json", checklist)
            self._write_json(tmpdir, "session.json", session_data)

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
        self.assertEqual("2026-03-26", finding["dateIssued"])

    def test_process_inspection_rejects_invalid_session_schema(self):
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "inspection-1",
                "inspectionCode": "MDPP-2026-01",
                "locationId": "location-1",
                "locationName": "Aeropuerto",
                "icaoCode": "MDPP",
                "specialtyId": "specialty-1",
                "specialtyCode": "VIG",
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "VIG-0001",
                    "requirement": "Question text from checklist",
                    "compliance": "Non-compliant",
                }
            ],
        }

        invalid_session_data = {
            "summary": {
                "lastUpdated": "2026-03-26T10:35:00.000Z"
            },
            "responses": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_json(tmpdir, "checklist.json", checklist)
            self._write_json(tmpdir, "session.json", invalid_session_data)

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
                "findingId": "MDPP-VIG-2025-02",
                "specialtyId": "specialty-1",
                "specialtyCode": "VIG",
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
                "locationId": "location-1",
                "locationCode": "MDPP",
                "locationName": "Location",
                "itemId": "item-1",
                "itemCode": "VIG-0001",
                "description": "desc",
                "correctiveAction": {
                    "capId": "10"
                }
            }
        ]

        reports = [
            {
                "schemaVersion": "1.0",
                "followUpReport": {
                    "findingId": "MDPP-VIG-2025-02",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Location",
                    "followUpDate": "2026-04-14T15:36:28.825Z",
                    "findingClosed": False,
                    "percentComplete": 30,
                    "effectivenessConfirmed": False,
                    "specialtyId": "specialty-1",
                    "capId": "10",
                    "evidence": [
                        {
                            "evidenceId": "FUEV-0001-01",
                            "evidenceType": "document",
                            "evidenceSource": "proof.pdf"
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

        client = FakeAlfrescoClient.instances[0]
        self.assertEqual(1, len(client.followup_reports))
        self.assertEqual(1, len(client.followup_evidence))

    def test_process_followup_payload_rejects_cap_mismatch(self):
        findings = [
            {
                "findingId": "MDPP-VIG-2025-02",
                "specialtyId": "specialty-1",
                "specialtyCode": "VIG",
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
                "locationId": "location-1",
                "locationCode": "MDPP",
                "locationName": "Location",
                "itemId": "item-1",
                "itemCode": "VIG-0001",
                "description": "desc",
                "correctiveAction": {
                    "capId": "11"
                }
            }
        ]

        reports = [
            {
                "schemaVersion": "1.0",
                "followUpReport": {
                    "findingId": "MDPP-VIG-2025-02",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Location",
                    "followUpDate": "2026-04-14T15:36:28.825Z",
                    "findingClosed": False,
                    "percentComplete": 30,
                    "effectivenessConfirmed": False,
                    "specialtyId": "specialty-1",
                    "capId": "10",
                    "evidence": []
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
                    "findingId": "MDPP-VIG-2025-02",
                    "specialtyId": "specialty-1",
                    "specialtyCode": "VIG",
                    "specialtyName": "Vigilancia",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationCode": "MDPP",
                    "locationName": "Location",
                    "itemId": "item-1",
                    "itemCode": "VIG-0001",
                    "description": "desc",
                    "correctiveAction": {
                        "capId": "10"
                    }
                }
            }
        ]

        reports = [
            {
                "schemaVersion": "1.0",
                "followUpReport": {
                    "findingId": "MDPP-VIG-2025-02",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Location",
                    "followUpDate": "2026-04-14T15:36:28.825Z",
                    "findingClosed": False,
                    "percentComplete": 30,
                    "effectivenessConfirmed": False,
                    "specialtyId": "specialty-1",
                    "capId": "10",
                    "evidence": []
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


if __name__ == "__main__":
    unittest.main()
