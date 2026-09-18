import io
import json
import os
import unittest
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from id_utils import build_finding_id

from main import app

TEST_INSPECTION_CODE = "TEST-A-0999"
TEST_SPECIALTY_CODE = "TST"


def _alfresco_test_url():
    return os.getenv("ALFRESCO_TEST_URL", "")


class InspectionImportIntegrationTests(unittest.TestCase):

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

    def test_imports_inspection_to_real_alfresco(self):
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": f"integration-{TEST_INSPECTION_CODE}",
                "inspectionCode": TEST_INSPECTION_CODE,
                "locationId": "TEST-LOC",
                "locationName": "Integration Test Airport",
                "locationCode": "TEST",
                "specialtyId": "TEST-SPEC",
                "specialtyCode": TEST_SPECIALTY_CODE,
                "specialtyName": "Integration Test Specialty",
                "providerId": "TEST-PROV",
            },
            "items": [
                {
                    "itemId": "item-test-1",
                    "itemCode": "TST-0001",
                    "requirement": "Integration test checklist item",
                    "compliance": "Non-compliant",
                }
            ],
        }
        findings = [
            {
                "schemaVersion": "1.0",
                "finding": {
                    "findingId": build_finding_id(TEST_INSPECTION_CODE, TEST_SPECIALTY_CODE, 1),
                    "specialtyId": "TEST-SPEC",
                    "specialtyCode": TEST_SPECIALTY_CODE,
                    "specialtyName": "Integration Test Specialty",
                    "providerId": "TEST-PROV",
                    "locationId": "TEST-LOC",
                    "locationName": "Integration Test Airport",
                    "checklistItemCode": "TST-0001",
                    "description": "Automated integration test finding",
                    "findingLevel": "Observation",
                }
            }
        ]

        payload = self._build_zip_bytes({
            "checklist.json": checklist,
            "findings.json": findings,
        })

        response = self.client.post(
            "/inspection-import",
            files={"file": ("integration_test.zip", payload, "application/zip")},
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("imported", body["status"])
        self.assertEqual(f"integration-{TEST_INSPECTION_CODE}", body["inspectionId"])
        self.assertEqual(1, body["findingsImported"])
        self.assertEqual(0, body["evidenceImported"])

    def test_imports_inspection_with_evidence_file(self):
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": f"integration-evidence-{TEST_INSPECTION_CODE}",
                "inspectionCode": TEST_INSPECTION_CODE,
                "locationId": "TEST-LOC",
                "locationName": "Integration Test Airport",
                "locationCode": "TEST",
                "specialtyId": "TEST-SPEC",
                "specialtyCode": TEST_SPECIALTY_CODE,
                "specialtyName": "Integration Test Specialty",
                "providerId": "TEST-PROV",
            },
            "items": [],
        }

        payload = self._build_zip_bytes({
            "checklist.json": checklist,
            "findings.json": [],
            "test-evidence.txt": "integration test evidence content",
        })

        response = self.client.post(
            "/inspection-import",
            files={"file": ("evidence_test.zip", payload, "application/zip")},
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("imported", body["status"])
        self.assertEqual(1, body["evidenceImported"])

    def test_rejects_corrupt_zip(self):
        response = self.client.post(
            "/inspection-import",
            files={"file": ("bad.zip", b"not a zip file", "application/zip")},
        )

        self.assertEqual(400, response.status_code)
        self.assertIn("not a valid ZIP", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
