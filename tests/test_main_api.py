import io
import json
import unittest
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


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


class ImportInspectionApiTests(unittest.TestCase):

    def setUp(self):
        FakeAlfrescoClient.instances = []
        self.client = TestClient(app)

    def _build_zip_bytes(self, files):
        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for name, content in files.items():
                if isinstance(content, (dict, list)):
                    zip_file.writestr(name, json.dumps(content))
                    continue

                zip_file.writestr(name, content)

        buffer.seek(0)
        return buffer.getvalue()

    def test_import_inspection_route_processes_standard_payload(self):
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
                "providerId": "provider-1"
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "VIG-0001",
                    "requirement": "Question text from checklist",
                    "compliance": "Non-compliant"
                }
            ]
        }
        session_data = {
            "summary": {
                "specialty": "Vigilancia",
                "lastUpdated": "2026-03-26T10:35:00.000Z"
            },
            "responses": {
                "item-1": {
                    "id": "item-1",
                    "compliance": "Non-compliant",
                    "comments": "fallback comments",
                    "nonConformityDetails": {
                        "description": "Generated finding description",
                        "riskLevel": "High",
                        "findingLevel": "Observation"
                    }
                }
            }
        }

        payload = self._build_zip_bytes(
            {
                "checklist.json": checklist,
                "session.json": session_data,
            }
        )

        with patch("transformer.AlfrescoClient", FakeAlfrescoClient):
            response = self.client.post(
                "/inspection-import",
                files={"file": ("inspection_payload_test.zip", payload, "application/zip")},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "status": "imported",
                "inspectionId": "inspection-1",
                "findingsImported": 1,
                "evidenceImported": 0,
            },
            response.json(),
        )

    def test_followup_import_route_processes_followup_payload(self):
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
        followup_reports = [
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

        payload = self._build_zip_bytes(
            {
                "findings.json": findings,
                "followup-reports.json": followup_reports,
                "FollowUpEvidence/proof.pdf": "binary-content",
            }
        )

        with patch("transformer.AlfrescoClient", FakeAlfrescoClient):
            response = self.client.post(
                "/followup-import",
                files={"file": ("followup_payload_test.zip", payload, "application/zip")},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "status": "imported",
                "followUpReportsImported": 1,
                "followUpEvidenceImported": 1,
            },
            response.json(),
        )

    def test_followup_import_route_rejects_followup_payload_with_missing_evidence(self):
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
        followup_reports = [
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
                            "evidenceSource": "missing-proof.pdf"
                        }
                    ]
                }
            }
        ]

        payload = self._build_zip_bytes(
            {
                "findings.json": findings,
                "followup-reports.json": followup_reports,
            }
        )

        with patch("transformer.AlfrescoClient", FakeAlfrescoClient):
            response = self.client.post(
                "/followup-import",
                files={"file": ("followup_payload_bad.zip", payload, "application/zip")},
            )

        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {
                "detail": "Missing FollowUpEvidence folder in follow-up payload"
            },
            response.json(),
        )

    def test_followup_import_route_accepts_wrapped_source_findings(self):
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
        followup_reports = [
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

        payload = self._build_zip_bytes(
            {
                "findings.json": findings,
                "followup-reports.json": followup_reports,
                "FollowUpEvidence/.keep": "",
            }
        )

        with patch("transformer.AlfrescoClient", FakeAlfrescoClient):
            response = self.client.post(
                "/followup-import",
                files={"file": ("followup_payload_wrapped.zip", payload, "application/zip")},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "status": "imported",
                "followUpReportsImported": 1,
                "followUpEvidenceImported": 0,
            },
            response.json(),
        )


if __name__ == "__main__":
    unittest.main()