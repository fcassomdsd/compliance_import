import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from id_utils import build_corrective_action_id, build_finding_id

import main
from main import app
from tests.support.fake_alfresco_client import FakeAlfrescoClient


INSPECTION_CODE = "MDPP-I-0001"
SPECIALTY_CODE = "SUR"
FINDING_ID = build_finding_id(INSPECTION_CODE, SPECIALTY_CODE, 1)
CAP_ID = build_corrective_action_id(FINDING_ID, 1)


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
                    "itemCode": "SUR-0001",
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
                    "checklistItemCode": "SUR-0001",
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
                "checklistItemCode": "SUR-0001",
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
                "checklistItemCode": "SUR-0001",
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
                    "checklistItemCode": "SUR-0001",
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

    def test_import_rejects_upload_larger_than_configured_cap(self):
        payload = self._build_zip_bytes({"checklist.json": json.dumps({"test": True})})

        with patch.object(main, "MAX_UPLOAD_SIZE_BYTES", 10):
            response = self.client.post(
                "/inspection-import",
                files={"file": ("payload.zip", payload, "application/zip")},
            )

        self.assertEqual(413, response.status_code)
        self.assertIn("maximum size", response.json()["detail"])

    def test_import_rejects_empty_upload(self):
        response = self.client.post(
            "/inspection-import",
            files={"file": ("payload.zip", b"", "application/zip")},
        )

        self.assertEqual(400, response.status_code)
        self.assertIn("empty", response.json()["detail"])


class AuthMiddlewareTests(unittest.TestCase):

    def setUp(self):
        FakeAlfrescoClient.instances = []
        self.client = TestClient(app)

    @staticmethod
    def _empty_zip():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(".keep", "")
        buffer.seek(0)
        return buffer.getvalue()

    def test_auth_allows_request_when_import_api_key_is_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.post(
                "/inspection-import",
                files={"file": ("test.zip", self._empty_zip(), "application/zip")},
            )

        self.assertIn(response.status_code, (200, 400))

    def test_auth_rejects_request_without_api_key(self):
        with patch.dict(os.environ, {"IMPORT_API_KEY": "secret-key"}):
            response = self.client.post(
                "/inspection-import",
                files={"file": ("test.zip", self._empty_zip(), "application/zip")},
            )

        self.assertEqual(401, response.status_code)

    def test_auth_rejects_request_with_invalid_api_key(self):
        with patch.dict(os.environ, {"IMPORT_API_KEY": "secret-key"}):
            response = self.client.post(
                "/inspection-import",
                files={"file": ("test.zip", self._empty_zip(), "application/zip")},
                headers={"X-API-Key": "wrong-key"},
            )

        self.assertEqual(401, response.status_code)

    def test_auth_allows_request_with_valid_api_key(self):
        with patch.dict(os.environ, {"IMPORT_API_KEY": "secret-key"}):
            response = self.client.post(
                "/inspection-import",
                files={"file": ("test.zip", self._empty_zip(), "application/zip")},
                headers={"X-API-Key": "secret-key"},
            )

        self.assertIn(response.status_code, (200, 400))


class ZipBombProtectionTests(unittest.TestCase):

    def setUp(self):
        FakeAlfrescoClient.instances = []

    def test_validate_zip_bomb_rejects_high_compression_ratio(self):
        info = zipfile.ZipInfo("bomb.txt")
        info.file_size = 10000
        info.compress_size = 50

        with self.assertRaises(HTTPException) as ctx:
            main._validate_zip_bomb(info)

        self.assertEqual(400, ctx.exception.status_code)
        self.assertIn("compression ratio", ctx.exception.detail)

    def test_validate_zip_bomb_rejects_oversized_file(self):
        with patch("main.MAX_EXTRACTED_FILE_SIZE", 100):
            info = zipfile.ZipInfo("huge.bin")
            info.file_size = 500
            info.compress_size = 500

            with self.assertRaises(HTTPException) as ctx:
                main._validate_zip_bomb(info)

            self.assertEqual(400, ctx.exception.status_code)
            self.assertIn("maximum decompressed", ctx.exception.detail)

    def test_safe_extract_rejects_total_oversize(self):
        with patch("main.MAX_EXTRACTED_TOTAL_SIZE", 200):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr("a.txt", "A" * 150)
                zip_file.writestr("b.txt", "B" * 100)
            buffer.seek(0)

            with tempfile.TemporaryDirectory() as tmpdir:
                with zipfile.ZipFile(buffer, "r") as zip_ref:
                    with self.assertRaises(HTTPException) as ctx:
                        main._safe_extract(zip_ref, tmpdir)

                    self.assertEqual(400, ctx.exception.status_code)
                    self.assertIn("maximum total", ctx.exception.detail)

    def test_safe_extract_rejects_path_traversal(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            info = zipfile.ZipInfo("../escape.txt")
            zip_file.writestr(info, "escaped")
        buffer.seek(0)

        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(buffer, "r") as zip_ref:
                with self.assertRaises(HTTPException) as ctx:
                    main._safe_extract(zip_ref, tmpdir)

                self.assertEqual(400, ctx.exception.status_code)
                self.assertIn("unsafe", ctx.exception.detail)

    def test_safe_extract_allows_normal_payload(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr("checklist.json", json.dumps({"test": True}))
        buffer.seek(0)

        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(buffer, "r") as zip_ref:
                main._safe_extract(zip_ref, tmpdir)

            extracted = Path(tmpdir) / "checklist.json"
            self.assertTrue(extracted.is_file())


if __name__ == "__main__":
    unittest.main()