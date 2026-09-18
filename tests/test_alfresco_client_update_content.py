import unittest
from types import SimpleNamespace

from alfresco_client import AlfrescoClient


class UpdateNodeContentTests(unittest.TestCase):
    """The update-content request shape.

    This existed untested, so a multipart body (415 from Alfresco) went unnoticed
    until the demo quickstart was run a second time: creating a document worked,
    updating an existing one failed.
    """

    def _client(self):
        client = AlfrescoClient.__new__(AlfrescoClient)
        client.base_url = "http://alfresco/api/-default-/public/alfresco/versions/1"
        client.timeout_seconds = 20
        client._check_response = lambda response: None
        return client

    def test_update_sends_raw_content_with_its_own_content_type(self):
        client = self._client()
        calls = []

        class FakeResponse:
            def json(self):
                return {"entry": {"id": "node-1"}}

        def fake_put(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse()

        client.session = SimpleNamespace(put=fake_put)
        payload = b'{"a": 1}'

        result = client._update_node_content("node-1", "Checklist.json", payload, "application/json")

        self.assertEqual({"entry": {"id": "node-1"}}, result)
        self.assertEqual(1, len(calls))
        url, kwargs = calls[0]
        self.assertTrue(url.endswith("/nodes/node-1/content"), url)
        self.assertEqual({"majorVersion": "false"}, kwargs.get("params"))
        self.assertEqual(payload, kwargs.get("data"))
        self.assertEqual({"Content-Type": "application/json"}, kwargs.get("headers"))
        # `files=` would produce multipart/form-data, which Alfresco rejects with 415.
        self.assertNotIn("files", kwargs)


if __name__ == "__main__":
    unittest.main()
