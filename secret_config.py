"""Secret resolution for the import service.

Secrets resolve by precedence, matching ``compliance_flow/data/secrets.js`` and
``compliance_web/server/config/secrets.cjs`` so the whole platform has one
shape:

1. ``<NAME>_FILE``           a path to a file holding the value
2. ``/run/secrets/<name>``   a Docker/Compose secret, lowercase name
3. ``<NAME>``                a plain environment variable

Step 1 is the seam a secret manager writes into: once secrets can arrive as
files, introducing Vault requires no change here. See section 4.3 of
"An ideal production configuration.md" in the platform umbrella repo.

This module supersedes the resolver that lived in ``alfresco_client.py``. That
one fell through to the next source when ``<NAME>_FILE`` pointed at a missing
or empty file; this one raises. A silent fallback from a file a secret manager
was supposed to write, to a stale environment value, is how a secret rotation
appears to succeed and does not.

Named ``secret_config`` rather than ``secrets`` on purpose: this directory is
on ``sys.path``, so a module named ``secrets.py`` shadows the standard
library's ``secrets`` module for every import in the process -- including any
dependency reaching for ``secrets.token_hex``.
"""

import os
from pathlib import Path

DEFAULT_SECRET_DIR = "/run/secrets"

#: Secrets this service reads. ``required`` means production startup fails
#: without it. ``IMPORT_API_KEY`` is required in production specifically
#: because leaving it unset does not fail closed -- it disables the API-key
#: check altogether and leaves the ingestion endpoints open.
SECRETS = (
    ("ALFRESCO_USERNAME", True),
    ("ALFRESCO_PASSWORD", True),
    ("IMPORT_API_KEY", True),
)

SECRET_NAMES = tuple(name for name, _ in SECRETS)

#: Values published in this repository, and therefore secret to nobody.
#:
#: ``IMPORT_API_KEY``'s shipped value is shared verbatim with
#: ``compliance_flow``'s ``API_KEY`` and ``compliance_web``'s
#: ``NODE_RED_API_KEY``, so everyone who has cloned any of the three
#: repositories already knows it. Presence is not secrecy.
PUBLIC_PLACEHOLDERS = frozenset(
    {
        "demo-only-CHANGE-BEFORE-ANY-PUBLIC-DEPLOYMENT",
        "replace-me",
        "change-me",
        "changeme",
        "admin",
        "password",
    }
)


class SecretResolutionError(ValueError):
    """Raised when a secret is configured in a way that cannot be honoured.

    Subclasses ``ValueError`` rather than ``RuntimeError`` to preserve the
    contract of the resolver this replaced, which raised ``ValueError`` when a
    required credential was absent. A misconfigured secret is a bad value, and
    keeping the type means existing ``except ValueError`` handlers behave
    exactly as before.
    """


def _read_secret_file(path):
    """Return the stripped contents of ``path``, or ``None`` if unusable."""
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def resolve_secret(name, env=None, secret_dir=DEFAULT_SECRET_DIR):
    """Resolve one secret by precedence.

    Returns the value, or ``None`` when no source provides it.

    Raises ``SecretResolutionError`` when ``<NAME>_FILE`` is set but the file is
    missing or empty, rather than falling through -- see the module docstring.
    """
    environ = os.environ if env is None else env

    explicit_path = environ.get(f"{name}_FILE")
    if explicit_path:
        value = _read_secret_file(explicit_path)
        if not value:
            raise SecretResolutionError(
                f"{name}_FILE points at {explicit_path}, which is missing or empty. "
                f"Not falling back to {name} - a silent fallback would hide a "
                "failed secret rotation."
            )
        return value

    mounted = _read_secret_file(os.path.join(secret_dir, name.lower()))
    if mounted:
        return mounted

    return environ.get(name) or None


def require_secret(name, env=None, secret_dir=DEFAULT_SECRET_DIR):
    """Resolve a secret, raising when no source provides it."""
    value = resolve_secret(name, env=env, secret_dir=secret_dir)
    if value is None:
        raise SecretResolutionError(
            f"Missing {name}. Set {name}, {name}_FILE, or mount a secret at "
            f"{os.path.join(secret_dir, name.lower())}"
        )
    return value


def is_production(env=None):
    """Whether the service is configured to run in production.

    ``APP_ENV`` is the Python-side equivalent of the ``NODE_ENV=production``
    the two Node services use; the name differs because ``NODE_ENV`` in a
    Python service reads as a copy-paste mistake.
    """
    environ = os.environ if env is None else env
    return environ.get("APP_ENV", "").strip().lower() == "production"


def assert_production_secrets(env=None, secret_dir=DEFAULT_SECRET_DIR):
    """Refuse an insecure production configuration.

    Returns silently outside production, and when the configuration is
    acceptable. Raises ``SecretResolutionError`` otherwise.
    """
    environ = os.environ if env is None else env
    if not is_production(environ):
        return

    resolved = {
        name: resolve_secret(name, env=environ, secret_dir=secret_dir)
        for name in SECRET_NAMES
    }

    missing = [name for name, required in SECRETS if required and not resolved[name]]
    if missing:
        raise SecretResolutionError(
            "Refusing to start: APP_ENV=production requires these secrets, via "
            f"<NAME>_FILE, {secret_dir}/<name>, or the environment: "
            + ", ".join(missing)
        )

    published = [
        name for name in SECRET_NAMES if resolved[name] in PUBLIC_PLACEHOLDERS
    ]
    if published:
        raise SecretResolutionError(
            "Refusing to start: these secrets still hold a value published in "
            "this repository, which means they are not secret: "
            + ", ".join(published)
            + ". Generate real values (for example `openssl rand -hex 32`) "
            "before running with APP_ENV=production."
        )
