import unittest
from types import SimpleNamespace

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
                "findingId": "H-MDPPI0001-SUR-001",
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        result = client.store_followup_report_document(report, "Vigilancia")

        self.assertEqual("FollowUp H-MDPPI0001-SUR-001 03", result["entry"]["name"].removesuffix(".json"))
        self.assertEqual(
            build_followup_id_seq("H-MDPPI0001-SUR-001", 3),
            report["followUpReport"]["followUpId"],
        )

    def test_store_followup_replaces_source_temporary_id(self):
        client = self._build_client()
        client._resolve_next_followup_seq = lambda relative_path, prefix: 1
        client._upload_followup_json = lambda filename, doc, specialty: self._make_upload_ok(filename)

        report = {
            "schemaVersion": "1.0",
            "followUpReport": {
                "findingId": "H-MDPPI0001-SUR-001",
                "followUpId": "S-MDPPI0001-SUR001-99",  # temporary source ID
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        client.store_followup_report_document(report, "Vigilancia")

        self.assertEqual(
            build_followup_id_seq("H-MDPPI0001-SUR-001", 1),
            report["followUpReport"]["followUpId"],
        )

    def test_store_followup_retries_on_conflict(self):
        client = self._build_client()

        seq_calls = []

        def mock_get_seq(relative_path, prefix):
            seq_calls.append(1)
            return len(seq_calls)  # returns 1, 2, 3, ...

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
                "findingId": "H-MDPPI0001-SUR-001",
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        result = client.store_followup_report_document(report, "Vigilancia")

        self.assertEqual(2, len(upload_calls))
        self.assertIn("FollowUp H-MDPPI0001-SUR-001 02", upload_calls[1])
        self.assertIsNotNone(result)

    def test_store_followup_raises_after_max_retries(self):
        client = self._build_client()
        client._resolve_next_followup_seq = lambda relative_path, prefix: 0
        client._upload_followup_json = lambda filename, doc, specialty: None  # always conflict

        report = {
            "schemaVersion": "1.0",
            "followUpReport": {
                "findingId": "H-MDPPI0001-SUR-001",
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        with self.assertRaises(RuntimeError):
            client.store_followup_report_document(report, "Vigilancia")

    def test_store_followup_seq_one_on_first_file(self):
        client = self._build_client()
        client._resolve_next_followup_seq = lambda relative_path, prefix: 1
        client._upload_followup_json = lambda filename, doc, specialty: self._make_upload_ok(filename)

        report = {
            "schemaVersion": "1.0",
            "followUpReport": {
                "findingId": "H-MDPPI0001-SUR-001",
                "followUpDate": "2026-04-14T15:36:28.825Z",
            },
        }

        result = client.store_followup_report_document(report, "Vigilancia")

        self.assertEqual("FollowUp H-MDPPI0001-SUR-001 01", result["entry"]["name"].removesuffix(".json"))


class ResolveNextFollowupSeqTests(unittest.TestCase):

    class _FakeResponse:

        status_code = 200

        def __init__(self, names):
            self._names = names

        def json(self):
            return {"list": {"entries": [{"entry": {"name": name}} for name in self._names]}}

        def raise_for_status(self):
            return None

    def _client_listing(self, names):
        client = AlfrescoClient.__new__(AlfrescoClient)
        client.canonical_json_path = "Sites/test/documentLibrary"
        client.timeout_seconds = 20
        client.base_url = "http://alfresco.test"
        client.session = SimpleNamespace(get=lambda *args, **kwargs: self._FakeResponse(names))
        return client

    def test_empty_folder_starts_sequence_at_one(self):
        client = self._client_listing([])

        self.assertEqual(
            1,
            client._resolve_next_followup_seq("Sites/test", "FollowUp H-MDPPI0001-SUR-001"),
        )

    def test_next_sequence_follows_highest_existing(self):
        client = self._client_listing([
            "FollowUp H-MDPPI0001-SUR-001 01.json",
            "FollowUp H-MDPPI0001-SUR-001 02.json",
            "Finding H-MDPPI0001-SUR-001.json",
        ])

        self.assertEqual(
            3,
            client._resolve_next_followup_seq("Sites/test", "FollowUp H-MDPPI0001-SUR-001"),
        )


if __name__ == "__main__":
    unittest.main()
