import unittest

from alfresco_client import AlfrescoClient
from id_utils import build_followup_id


class FollowupReportIdTests(unittest.TestCase):

    def _build_client(self):
        client = AlfrescoClient.__new__(AlfrescoClient)
        client.upload_json_document = lambda filename, document, specialty_name: {
            "filename": filename,
            "document": document,
            "specialty_name": specialty_name,
        }
        return client

    def test_store_followup_report_document_preserves_source_followup_id(self):
        client = self._build_client()

        report = {
            "schemaVersion": "1.0",
            "followUpReport": {
                "findingId": "MDPP001-VIG-01",
                "followUpId": "FU-CUSTOM-123",
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        result = client.store_followup_report_document(report, "Vigilancia")

        self.assertEqual("FU-CUSTOM-123", report["followUpReport"]["followUpId"])
        self.assertEqual("FollowUp MDPP001-VIG-01 2026-04-14", result["filename"])

    def test_store_followup_report_document_generates_followup_id_when_missing(self):
        client = self._build_client()

        report = {
            "schemaVersion": "1.0",
            "followUpReport": {
                "findingId": "MDPP001-VIG-01",
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        client.store_followup_report_document(report, "Vigilancia")

        self.assertEqual(
            build_followup_id("MDPP001-VIG-01", "2026-04-14T15:36:28.825Z"),
            report["followUpReport"]["followUpId"],
        )


if __name__ == "__main__":
    unittest.main()
