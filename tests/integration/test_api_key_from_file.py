"""The API-key middleware must honour a key delivered as a file.

Unit tests cover the resolver in isolation; this covers the thing that
actually matters operationally -- that a secret manager writing
/run/secrets/import_api_key results in requests being authenticated against
that value, with no code change and no environment variable.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app

DEMO_PLACEHOLDER = "demo-only-CHANGE-BEFORE-ANY-PUBLIC-DEPLOYMENT"


class ApiKeyFromFileTests(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        directory = tempfile.mkdtemp()
        self.key_path = Path(directory, "import_api_key")
        self.key_path.write_text("file-delivered-key\n", encoding="utf-8")

    def _env(self, **overrides):
        env = {k: v for k, v in os.environ.items() if k != "IMPORT_API_KEY"}
        env.update(overrides)
        return env

    def test_request_with_the_file_delivered_key_passes_the_middleware(self):
        env = self._env(IMPORT_API_KEY_FILE=str(self.key_path))
        with patch.dict(os.environ, env, clear=True):
            response = self.client.post(
                "/inspection-import", headers={"X-API-Key": "file-delivered-key"}
            )
        # 422 is the body validation failing on an empty request, which is
        # exactly what we want: the request got past the API-key middleware.
        self.assertNotEqual(401, response.status_code)

    def test_request_with_a_wrong_key_is_rejected(self):
        env = self._env(IMPORT_API_KEY_FILE=str(self.key_path))
        with patch.dict(os.environ, env, clear=True):
            response = self.client.post(
                "/inspection-import", headers={"X-API-Key": "not-the-key"}
            )
        self.assertEqual(401, response.status_code)

    def test_the_file_outranks_a_plain_environment_variable(self):
        # A stale IMPORT_API_KEY must not keep working once a secret file is in
        # place -- otherwise a rotation silently fails to take effect.
        env = self._env(
            IMPORT_API_KEY_FILE=str(self.key_path), IMPORT_API_KEY="stale-env-key"
        )
        with patch.dict(os.environ, env, clear=True):
            stale = self.client.post(
                "/inspection-import", headers={"X-API-Key": "stale-env-key"}
            )
            current = self.client.post(
                "/inspection-import", headers={"X-API-Key": "file-delivered-key"}
            )
        self.assertEqual(401, stale.status_code, "the superseded key must stop working")
        self.assertNotEqual(401, current.status_code)

    def test_a_rotated_secret_file_takes_effect_without_a_restart(self):
        # The middleware resolves per request precisely so that a secret
        # manager rewriting the file does not require a container restart.
        env = self._env(IMPORT_API_KEY_FILE=str(self.key_path))
        with patch.dict(os.environ, env, clear=True):
            before = self.client.post(
                "/inspection-import", headers={"X-API-Key": "file-delivered-key"}
            )
            self.assertNotEqual(401, before.status_code)

            self.key_path.write_text("rotated-key\n", encoding="utf-8")

            old = self.client.post(
                "/inspection-import", headers={"X-API-Key": "file-delivered-key"}
            )
            new = self.client.post(
                "/inspection-import", headers={"X-API-Key": "rotated-key"}
            )
        self.assertEqual(401, old.status_code, "the pre-rotation key must stop working")
        self.assertNotEqual(401, new.status_code, "the rotated key must work immediately")

    def test_health_stays_reachable_without_a_key(self):
        env = self._env(IMPORT_API_KEY_FILE=str(self.key_path))
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(200, self.client.get("/health").status_code)


if __name__ == "__main__":
    unittest.main()
