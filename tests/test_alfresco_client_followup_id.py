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


class ResolveNextFollowupSeqPaginationTests(unittest.TestCase):
    """The sequence lookup must walk CMIS pages instead of stopping at 1000."""

    class _PagedResponse:
        status_code = 200

        def __init__(self, names):
            self._names = names

        def json(self):
            return {"list": {"entries": [{"entry": {"name": name}} for name in self._names]}}

        def raise_for_status(self):
            return None

    class _PagedSession:
        def __init__(self, pages):
            self.pages = pages
            self.calls = []

        def get(self, url, params=None, **kwargs):
            self.calls.append(dict(params or {}))
            page_size = (params or {}).get("maxItems", 200)
            skip = (params or {}).get("skipCount", 0)
            index = skip // page_size
            names = self.pages[index] if index < len(self.pages) else []
            return ResolveNextFollowupSeqPaginationTests._PagedResponse(names)

    def _client(self, session):
        client = AlfrescoClient.__new__(AlfrescoClient)
        client.canonical_json_path = "Sites/test/documentLibrary"
        client.timeout_seconds = 20
        client.base_url = "http://alfresco.test"
        client.session = session
        return client

    def test_sequence_lookup_reads_beyond_the_first_page(self):
        prefix = "FollowUp H-MDPPI0001-SUR-001"
        first_page = [f"{prefix} {i:03d}.json" for i in range(1, 201)]
        second_page = [f"{prefix} 201.json"]
        session = self._PagedSession([first_page, second_page])

        client = self._client(session)
        seq = client._resolve_next_followup_seq("Sites/test", prefix)

        self.assertEqual(202, seq)
        self.assertEqual(2, len(session.calls), "should have requested a second page")
        self.assertEqual(0, session.calls[0]["skipCount"])
        self.assertEqual(200, session.calls[1]["skipCount"])


class IdempotentDocumentWriteTests(unittest.TestCase):

    def _client(self):
        client = AlfrescoClient.__new__(AlfrescoClient)
        client.canonical_json_path = "Sites/test/documentLibrary"
        client.timeout_seconds = 20
        client.base_url = "http://alfresco.test"
        client._ensured_specialty_folders = set()
        client._batch_created_ids = []
        client._batch_active = False
        client._ensure_specialty_folder = lambda name: None
        return client

    def test_existing_document_is_updated_instead_of_duplicated(self):
        client = self._client()
        client._find_child_by_name = lambda relative_path, name: {"id": "node-existing", "name": name}

        updated = []

        def fake_update(node_id, filename, payload, content_type):
            updated.append((node_id, filename))
            return {"entry": {"id": node_id, "name": filename}}

        def unexpected_post(*args, **kwargs):
            raise AssertionError("an existing document should be updated, not re-created")

        client._update_node_content = fake_update
        client.session = SimpleNamespace(post=unexpected_post)

        result = client.upload_json_document("Checklist LV-TEST", {"a": 1}, "Vigilancia")

        self.assertTrue(result.get("updated"))
        self.assertEqual([("node-existing", "Checklist LV-TEST.json")], updated)

    def test_missing_document_is_created_and_recorded_for_rollback(self):
        client = self._client()
        client._find_child_by_name = lambda relative_path, name: None

        class _Response:
            status_code = 201

            def raise_for_status(self):
                return None

            def json(self):
                return {"entry": {"id": "node-new", "name": "Checklist LV-TEST.json"}}

        client.session = SimpleNamespace(post=lambda *args, **kwargs: _Response())

        client.begin_batch()
        result = client.upload_json_document("Checklist LV-TEST", {"a": 1}, "Vigilancia")

        self.assertTrue(result.get("created"))
        self.assertEqual(["node-new"], client._batch_created_ids)


class BatchRollbackTests(unittest.TestCase):

    def test_rollback_deletes_nodes_created_in_the_batch(self):
        client = AlfrescoClient.__new__(AlfrescoClient)
        client.base_url = "http://alfresco.test"
        client.timeout_seconds = 20

        deleted = []

        class _DeleteResponse:
            status_code = 204

        client.session = SimpleNamespace(delete=lambda url, **kwargs: (deleted.append(url), _DeleteResponse())[1])

        client.begin_batch()
        client._record_created({"entry": {"id": "node-1"}})
        client._record_created({"entry": {"id": "node-2"}})

        removed = client.rollback_batch()

        # Newest first.
        self.assertEqual(["node-2", "node-1"], removed)
        self.assertEqual(
            ["http://alfresco.test/nodes/node-2", "http://alfresco.test/nodes/node-1"],
            deleted,
        )
        self.assertFalse(client._batch_active)
        self.assertEqual([], client._batch_created_ids)


class RetryPolicyTests(unittest.TestCase):

    def test_get_and_head_are_retried(self):
        from alfresco_client import DEFAULT_RETRY_METHODS

        self.assertIn("GET", DEFAULT_RETRY_METHODS)
        self.assertIn("HEAD", DEFAULT_RETRY_METHODS)
        self.assertIn("POST", DEFAULT_RETRY_METHODS)


if __name__ == "__main__":
    unittest.main()
