import unittest

from alfresco_client import AlfrescoClient
from id_utils import build_followup_id_seq


class FollowupReportIdTests(unittest.TestCase):

    def _build_client(self):
        client = AlfrescoClient.__new__(AlfrescoClient)
        client.canonical_json_path = "Sites/test/documentLibrary"
        client.timeout_seconds = 20
        client._ensured_specialty_folders = set()
        return client

    def _make_upload_ok(self, filename):
        return {"entry": {"name": f"{filename}.json"}}

    def test_store_followup_uses_sequential_id_for_filename_and_followup_id(self):
        client = self._build_client()
        client._resolve_next_followup_seq = lambda relative_path, prefix: 3
        client._upload_followup_json = lambda filename, doc, specialty: self._make_upload_ok(filename)

        report = {
            "schemaVersion": "1.0",
            "followUpReport": {
                "findingId": "MDPP001-VIG-01",
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        result = client.store_followup_report_document(report, "Vigilancia")

        self.assertEqual("FollowUp MDPP001-VIG-01 03", result["entry"]["name"].removesuffix(".json"))
        self.assertEqual(
            build_followup_id_seq("MDPP001-VIG-01", 3),
            report["followUpReport"]["followUpId"],
        )

    def test_store_followup_replaces_source_temporary_id(self):
        client = self._build_client()
        client._resolve_next_followup_seq = lambda relative_path, prefix: 0
        client._upload_followup_json = lambda filename, doc, specialty: self._make_upload_ok(filename)

        report = {
            "schemaVersion": "1.0",
            "followUpReport": {
                "findingId": "MDPP001-VIG-01",
                "followUpId": "FU-MDPP001VIG-01-260414",  # temporary source ID
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        client.store_followup_report_document(report, "Vigilancia")

        self.assertEqual(
            build_followup_id_seq("MDPP001-VIG-01", 0),
            report["followUpReport"]["followUpId"],
        )

    def test_store_followup_retries_on_conflict(self):
        client = self._build_client()

        seq_calls = []

        def mock_get_seq(relative_path, prefix):
            seq_calls.append(1)
            return len(seq_calls) - 1  # returns 0, 1, 2, ...

        upload_calls = []

        def mock_upload(filename, doc, specialty):
            upload_calls.append(filename)
            # Conflict on first attempt, success on second
            if len(upload_calls) == 1:
                return None
            return self._make_upload_ok(filename)

        client._resolve_next_followup_seq = mock_get_seq
        client._upload_followup_json = mock_upload

        report = {
            "schemaVersion": "1.0",
            "followUpReport": {
                "findingId": "MDPP001-VIG-01",
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        result = client.store_followup_report_document(report, "Vigilancia")

        self.assertEqual(2, len(upload_calls))
        self.assertIn("FollowUp MDPP001-VIG-01 01", upload_calls[1])
        self.assertIsNotNone(result)

    def test_store_followup_raises_after_max_retries(self):
        client = self._build_client()
        client._resolve_next_followup_seq = lambda relative_path, prefix: 0
        client._upload_followup_json = lambda filename, doc, specialty: None  # always conflict

        report = {
            "schemaVersion": "1.0",
            "followUpReport": {
                "findingId": "MDPP001-VIG-01",
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        with self.assertRaises(RuntimeError):
            client.store_followup_report_document(report, "Vigilancia")

    def test_store_followup_seq_zero_on_first_file(self):
        client = self._build_client()
        client._resolve_next_followup_seq = lambda relative_path, prefix: 0
        client._upload_followup_json = lambda filename, doc, specialty: self._make_upload_ok(filename)

        report = {
            "schemaVersion": "1.0",
            "followUpReport": {
                "findingId": "MDPP001-VIG-01",
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        result = client.store_followup_report_document(report, "Vigilancia")

        self.assertEqual("FollowUp MDPP001-VIG-01 00", result["entry"]["name"].removesuffix(".json"))


if __name__ == "__main__":
    unittest.main()
