import unittest

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


if __name__ == "__main__":
    unittest.main()
