import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class HealthIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint_returns_ok(self):
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())

    def test_health_endpoint_does_not_require_auth(self):
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)

    def test_health_endpoint_does_not_require_auth_even_when_a_key_is_configured(self):
        # A keyed deployment (the shipped default) must still answer /health without
        # X-API-Key -- that's what compose healthchecks and the demo quickstart's
        # readiness probe send.
        with patch.dict(os.environ, {"IMPORT_API_KEY": "secret-key"}):
            response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())

    def test_other_routes_still_require_the_key_when_configured(self):
        with patch.dict(os.environ, {"IMPORT_API_KEY": "secret-key"}):
            response = self.client.post("/inspection-import")

        self.assertEqual(401, response.status_code)


if __name__ == "__main__":
    unittest.main()
