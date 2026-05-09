import io
import json
import unittest
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from id_utils import build_corrective_action_id, build_finding_id

from main import app


INSPECTION_CODE = "MDPP-001"
SPECIALTY_CODE = "VIG"
FINDING_ID = build_finding_id(INSPECTION_CODE, SPECIALTY_CODE, 1)
CAP_ID = build_corrective_action_id(FINDING_ID, 1)


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
        finding_id = report["followUpReport"]["findingId"]
        sequence = len(self.followup_reports) + 1
        self.followup_reports.append((specialty_name, report))
        return {
            "storedFilename": f"FollowUp {finding_id} {sequence:02d}.json"
        }

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
                "inspectionCode": INSPECTION_CODE,
                "locationId": "location-1",
                "locationName": "Aeropuerto",
                "locationCode": "MDPP",
                "specialtyId": "specialty-1",
                "specialtyCode": SPECIALTY_CODE,
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
                    "checklistItemCode": "VIG-0001",
                    "description": "Generated finding description",
                    "findingLevel": "Observation"
                }
            }
        ]

        payload = self._build_zip_bytes(
            {
                "checklist.json": checklist,
                "findings.json": findings,
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
                "findingId": FINDING_ID,
                "specialtyId": "specialty-1",
                "specialtyCode": SPECIALTY_CODE,
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
                "locationId": "location-1",
                "locationCode": "MDPP",
                "locationName": "Location",
                "checklistItemCode": "VIG-0001",
                "description": "desc",
                "correctiveAction": {
                    "capId": CAP_ID
                }
            }
        ]
        followup_reports = [
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

        payload = self._build_zip_bytes(
            {
                "prior-findings.json": findings,
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
                "followUpFilenames": [f"FollowUp {FINDING_ID} 01.json"],
            },
            response.json(),
        )

    def test_followup_import_route_rejects_followup_payload_with_missing_evidence(self):
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
                "checklistItemCode": "VIG-0001",
                "description": "desc",
                "correctiveAction": {
                    "capId": CAP_ID
                }
            }
        ]
        followup_reports = [
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
                            "source": "missing-proof.pdf"
                        }
                    ]
                }
            }
        ]

        payload = self._build_zip_bytes(
            {
                "prior-findings.json": findings,
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
                    "findingId": FINDING_ID,
                    "specialtyId": "specialty-1",
                    "specialtyCode": SPECIALTY_CODE,
                    "specialtyName": "Vigilancia",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationCode": "MDPP",
                    "locationName": "Location",
                    "checklistItemCode": "VIG-0001",
                    "description": "desc",
                    "correctiveAction": {
                        "capId": CAP_ID
                    }
                }
            }
        ]
        followup_reports = [
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

        payload = self._build_zip_bytes(
            {
                "prior-findings.json": findings,
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
                "followUpFilenames": [f"FollowUp {FINDING_ID} 01.json"],
            },
            response.json(),
        )


if __name__ == "__main__":
    unittest.main()