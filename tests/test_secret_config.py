"""Tests for secret_config -- the import service's secret resolution.

These matter because the module decides whether the ingestion endpoints are
authenticated at all: IMPORT_API_KEY resolving to None disables the API-key
middleware entirely.
"""

import os
import tempfile
import unittest
from pathlib import Path

import secret_config
from secret_config import (
    PUBLIC_PLACEHOLDERS,
    SECRET_NAMES,
    SecretResolutionError,
    assert_production_secrets,
    resolve_secret,
    require_secret,
)


def _secret_dir(**entries):
    """A throwaway directory shaped like a Docker secret mount."""
    directory = tempfile.mkdtemp()
    for name, value in entries.items():
        Path(directory, name).write_text(value, encoding="utf-8")
    return directory


def _secret_file(value):
    handle = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
    handle.write(value)
    handle.close()
    return handle.name


def _healthy_env():
    """Every required secret present and real."""
    env = {name: f"generated-{name.lower()}" for name in SECRET_NAMES}
    env["APP_ENV"] = "production"
    return env


class ResolutionPrecedenceTests(unittest.TestCase):

    def test_file_env_var_wins_over_plain_env_var(self):
        path = _secret_file("from-the-file\n")
        value = resolve_secret(
            "IMPORT_API_KEY",
            env={"IMPORT_API_KEY_FILE": path, "IMPORT_API_KEY": "from-the-environment"},
            secret_dir=_secret_dir(),
        )
        self.assertEqual(value, "from-the-file", "the file wins, and is stripped")

    def test_docker_secret_wins_over_plain_env_var(self):
        directory = _secret_dir(import_api_key="from-the-mount\n")
        value = resolve_secret(
            "IMPORT_API_KEY",
            env={"IMPORT_API_KEY": "from-the-environment"},
            secret_dir=directory,
        )
        self.assertEqual(value, "from-the-mount")

    def test_plain_env_var_is_the_last_resort(self):
        value = resolve_secret(
            "IMPORT_API_KEY",
            env={"IMPORT_API_KEY": "from-the-environment"},
            secret_dir=_secret_dir(),
        )
        self.assertEqual(value, "from-the-environment")

    def test_returns_none_when_nothing_provides_the_value(self):
        self.assertIsNone(
            resolve_secret("IMPORT_API_KEY", env={}, secret_dir=_secret_dir())
        )


class BrokenSecretFileTests(unittest.TestCase):
    """A broken <NAME>_FILE must fail loudly, not fall back.

    This is the behaviour change from the resolver that lived in
    alfresco_client.py. Falling back meant a deleted secret file left the
    service running on a stale environment variable -- a failed rotation that
    looks like a successful one.
    """

    def test_missing_file_raises_instead_of_using_the_env_var(self):
        with self.assertRaises(SecretResolutionError) as caught:
            resolve_secret(
                "ALFRESCO_PASSWORD",
                env={
                    "ALFRESCO_PASSWORD_FILE": "/nonexistent/path",
                    "ALFRESCO_PASSWORD": "stale-but-present",
                },
                secret_dir=_secret_dir(),
            )
        self.assertIn("Not falling back", str(caught.exception))

    def test_empty_file_raises(self):
        path = _secret_file("   \n  ")
        with self.assertRaises(SecretResolutionError):
            resolve_secret(
                "ALFRESCO_PASSWORD",
                env={"ALFRESCO_PASSWORD_FILE": path},
                secret_dir=_secret_dir(),
            )

    def test_error_is_a_value_error_for_backwards_compatibility(self):
        # The resolver this replaced raised ValueError for a missing required
        # credential; existing `except ValueError` handlers must still work.
        self.assertTrue(issubclass(SecretResolutionError, ValueError))


class RequireSecretTests(unittest.TestCase):

    def test_raises_when_absent(self):
        with self.assertRaises(SecretResolutionError) as caught:
            require_secret("ALFRESCO_USERNAME", env={}, secret_dir=_secret_dir())
        message = str(caught.exception)
        self.assertIn("ALFRESCO_USERNAME", message)
        self.assertIn("ALFRESCO_USERNAME_FILE", message)

    def test_returns_the_value_when_present(self):
        self.assertEqual(
            require_secret(
                "ALFRESCO_USERNAME",
                env={"ALFRESCO_USERNAME": "svc"},
                secret_dir=_secret_dir(),
            ),
            "svc",
        )


class ProductionGuardTests(unittest.TestCase):

    def test_no_op_outside_production(self):
        # The demo runs without APP_ENV set and must be unaffected.
        assert_production_secrets(env={}, secret_dir=_secret_dir())
        assert_production_secrets(
            env={"IMPORT_API_KEY": "demo-only-CHANGE-BEFORE-ANY-PUBLIC-DEPLOYMENT"},
            secret_dir=_secret_dir(),
        )

    def test_accepts_a_fully_configured_production_setup(self):
        assert_production_secrets(env=_healthy_env(), secret_dir=_secret_dir())

    def test_rejects_a_missing_required_secret(self):
        env = _healthy_env()
        del env["ALFRESCO_PASSWORD"]
        with self.assertRaises(SecretResolutionError) as caught:
            assert_production_secrets(env=env, secret_dir=_secret_dir())
        self.assertIn("ALFRESCO_PASSWORD", str(caught.exception))

    def test_rejects_an_unset_api_key_in_production(self):
        # An unset IMPORT_API_KEY does not fail closed -- it disables the
        # middleware and leaves the ingestion endpoints open.
        env = _healthy_env()
        del env["IMPORT_API_KEY"]
        with self.assertRaises(SecretResolutionError) as caught:
            assert_production_secrets(env=env, secret_dir=_secret_dir())
        self.assertIn("IMPORT_API_KEY", str(caught.exception))

    def test_rejects_the_shared_demo_gateway_key(self):
        env = _healthy_env()
        env["IMPORT_API_KEY"] = "demo-only-CHANGE-BEFORE-ANY-PUBLIC-DEPLOYMENT"
        with self.assertRaises(SecretResolutionError) as caught:
            assert_production_secrets(env=env, secret_dir=_secret_dir())
        self.assertIn("published in this repository", str(caught.exception))
        self.assertIn("IMPORT_API_KEY", str(caught.exception))

    def test_rejects_every_known_public_placeholder(self):
        for placeholder in PUBLIC_PLACEHOLDERS:
            env = _healthy_env()
            env["ALFRESCO_PASSWORD"] = placeholder
            with self.assertRaises(SecretResolutionError, msg=f"accepted {placeholder!r}"):
                assert_production_secrets(env=env, secret_dir=_secret_dir())


class ShippedPlaceholderTests(unittest.TestCase):

    def test_the_value_in_env_docker_example_is_on_the_rejection_list(self):
        # Guards against the example file and the rejection list drifting
        # apart, which would let a "configured" deployment ship a key that
        # every reader of this repository already has.
        example = Path(__file__).resolve().parent.parent / ".env.docker.example"
        shipped = None
        for line in example.read_text(encoding="utf-8").splitlines():
            if line.startswith("IMPORT_API_KEY="):
                shipped = line.split("=", 1)[1].strip()
                break
        self.assertIsNotNone(shipped, ".env.docker.example must define IMPORT_API_KEY")
        self.assertIn(shipped, PUBLIC_PLACEHOLDERS)


class StdlibShadowingTests(unittest.TestCase):

    def test_this_module_does_not_shadow_the_stdlib_secrets_module(self):
        # An earlier revision named this file secrets.py, which put it ahead of
        # the standard library on sys.path and removed secrets.token_hex from
        # every import in the process.
        import secrets as stdlib_secrets

        self.assertTrue(hasattr(stdlib_secrets, "token_hex"))
        self.assertNotEqual(stdlib_secrets.__file__, secret_config.__file__)


if __name__ == "__main__":
    unittest.main()
