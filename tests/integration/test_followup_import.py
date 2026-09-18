import io
import json
import os
import unittest
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from id_utils import build_corrective_action_id, build_finding_id

from main import app

TEST_INSPECTION_CODE = "TEST-A-0999"
TEST_SPECIALTY_CODE = "TST"
TEST_FINDING_ID = build_finding_id(TEST_INSPECTION_CODE, TEST_SPECIALTY_CODE, 1)
TEST_CAP_ID = build_corrective_action_id(TEST_FINDING_ID, 1)


def _alfresco_test_url():
    return os.getenv("ALFRESCO_TEST_URL", "")


class FollowupImportIntegrationTests(unittest.TestCase):

    def setUp(self):
        if not _alfresco_test_url():
            raise unittest.SkipTest("Set ALFRESCO_TEST_URL to run integration tests")
        self.client = TestClient(app)

    @classmethod
    def setUpClass(cls):
        test_url = _alfresco_test_url()
        if not test_url:
            return
        cls.env_patch = patch.dict(os.environ, {
            "ALFRESCO_URL": test_url,
        }, clear=False)
        cls.env_patch.start()

    @classmethod
    def tearDownClass(cls):
        if not _alfresco_test_url():
            return
        cls.env_patch.stop()

    @staticmethod
    def _build_zip_bytes(files):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for name, content in files.items():
                if isinstance(content, (dict, list)):
                    zip_file.writestr(name, json.dumps(content))
                    continue
                zip_file.writestr(name, content)
        buffer.seek(0)
        return buffer.getvalue()

    def test_imports_followup_to_real_alfresco(self):
        findings = [
            {
                "findingId": TEST_FINDING_ID,
                "specialtyId": "TEST-SPEC",
                "specialtyCode": TEST_SPECIALTY_CODE,
                "specialtyName": "Integration Test Specialty",
                "providerId": "TEST-PROV",
                "locationId": "TEST-LOC",
                "locationCode": "TEST",
                "locationName": "Integration Test Airport",
                "checklistItemCode": "TST-0001",
                "description": "Integration test finding for follow-up",
                "correctiveAction": {
                    "capId": TEST_CAP_ID,
                },
            }
        ]
        reports = [
            {
                "schemaVersion": "1.0",
                "followUpReport": {
                    "findingId": TEST_FINDING_ID,
                    "providerId": "TEST-PROV",
                    "locationId": "TEST-LOC",
                    "locationName": "Integration Test Airport",
                    "followUpDate": "2026-06-21T10:00:00.000Z",
                    "percentComplete": 50,
                    "effectivenessConfirmed": False,
                    "specialtyId": "TEST-SPEC",
                    "capId": TEST_CAP_ID,
                    "evidenceItems": [],
                }
            }
        ]

        payload = self._build_zip_bytes({
            "prior-findings.json": findings,
            "followup-reports.json": reports,
            "FollowUpEvidence/.keep": "",
        })

        response = self.client.post(
            "/followup-import",
            files={"file": ("followup_test.zip", payload, "application/zip")},
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("imported", body["status"])
        self.assertEqual(1, body["followUpReportsImported"])
        self.assertEqual(0, body["followUpEvidenceImported"])
        self.assertTrue(len(body["followUpFilenames"]) >= 1)

    def test_followup_rejects_missing_evidence_folder(self):
        findings = [
            {
                "findingId": TEST_FINDING_ID,
                "specialtyId": "TEST-SPEC",
                "specialtyCode": TEST_SPECIALTY_CODE,
                "specialtyName": "Integration Test Specialty",
                "providerId": "TEST-PROV",
                "locationId": "TEST-LOC",
                "locationCode": "TEST",
                "locationName": "Integration Test Airport",
                "checklistItemCode": "TST-0001",
                "description": "Test finding",
            }
        ]
        reports = [
            {
                "schemaVersion": "1.0",
                "followUpReport": {
                    "findingId": TEST_FINDING_ID,
                    "providerId": "TEST-PROV",
                    "locationId": "TEST-LOC",
                    "locationName": "Integration Test Airport",
                    "followUpDate": "2026-06-21T10:00:00.000Z",
                    "percentComplete": 30,
                    "effectivenessConfirmed": False,
                    "specialtyId": "TEST-SPEC",
                    "evidenceItems": [],
                }
            }
        ]

        payload = self._build_zip_bytes({
            "prior-findings.json": findings,
            "followup-reports.json": reports,
        })

        response = self.client.post(
            "/followup-import",
            files={"file": ("no_evidence.zip", payload, "application/zip")},
        )

        self.assertEqual(400, response.status_code)
        self.assertIn("Missing FollowUpEvidence folder", response.json()["detail"])

    def test_followup_with_evidence_uploads_both(self):
        findings = [
            {
                "findingId": TEST_FINDING_ID,
                "specialtyId": "TEST-SPEC",
                "specialtyCode": TEST_SPECIALTY_CODE,
                "specialtyName": "Integration Test Specialty",
                "providerId": "TEST-PROV",
                "locationId": "TEST-LOC",
                "locationCode": "TEST",
                "locationName": "Integration Test Airport",
                "checklistItemCode": "TST-0001",
                "description": "Test finding with evidence",
                "correctiveAction": {
                    "capId": TEST_CAP_ID,
                },
            }
        ]
        reports = [
            {
                "schemaVersion": "1.0",
                "followUpReport": {
                    "findingId": TEST_FINDING_ID,
                    "providerId": "TEST-PROV",
                    "locationId": "TEST-LOC",
                    "locationName": "Integration Test Airport",
                    "followUpDate": "2026-06-21T10:00:00.000Z",
                    "percentComplete": 80,
                    "effectivenessConfirmed": True,
                    "specialtyId": "TEST-SPEC",
                    "capId": TEST_CAP_ID,
                    "evidenceItems": [
                        {
                            "evidenceId": "FUEV-TEST-01",
                            "evidenceType": "document",
                            "source": "test-evid.pdf",
                        }
                    ],
                }
            }
        ]

        payload = self._build_zip_bytes({
            "prior-findings.json": findings,
            "followup-reports.json": reports,
            "FollowUpEvidence/test-evid.pdf": "integration test binary evidence content",
        })

        response = self.client.post(
            "/followup-import",
            files={"file": ("followup_evidence.zip", payload, "application/zip")},
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("imported", body["status"])
        self.assertEqual(1, body["followUpReportsImported"])
        self.assertEqual(1, body["followUpEvidenceImported"])


if __name__ == "__main__":
    unittest.main()
