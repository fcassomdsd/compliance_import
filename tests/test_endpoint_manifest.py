"""Guards the README's endpoint manifest against drift from the FastAPI routes.

The service exposes three routes (plus FastAPI's own /docs, /openapi.json and
/redoc, which are documentation surface, not service endpoints). The README
lists the service endpoints in "What this service does" as
`- `METHOD /path`` bullets. This test fails when a route is added/removed
without updating that list, or when the README documents a route that no longer
exists.

This runs as part of the ordinary unittest suite (`python -m unittest discover`),
so there is no separate CI job to keep in sync.
"""

import re
import unittest
from pathlib import Path

import main


README_PATH = Path(__file__).resolve().parent.parent / "README.md"

# FastAPI's interactive-docs routes are not service endpoints.
IGNORED_PATHS = {
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}


def _actual_endpoints():
    endpoints = set()
    for route in main.app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or methods is None:
            continue
        if path in IGNORED_PATHS:
            continue
        for method in sorted(methods):
            endpoints.add(f"{method.upper()} {path}")
    return endpoints


def _documented_endpoints():
    text = README_PATH.read_text(encoding="utf-8")
    # Bullet rows in "What this service does": - `GET /health`
    pattern = re.compile(r"^\s*-\s*`?(GET|POST|PUT|PATCH|DELETE)\s+(/\S+?)`?\s*$", re.MULTILINE)
    return {f"{match.group(1).upper()} {match.group(2)}" for match in pattern.finditer(text)}


class EndpointManifestTests(unittest.TestCase):

    def test_every_route_is_documented_and_nothing_stale(self):
        actual = _actual_endpoints()
        documented = _documented_endpoints()

        self.assertNotEqual(actual, set(), "no routes discovered; the FastAPI app is empty")

        missing = sorted(actual - documented)
        stale = sorted(documented - actual)

        self.assertEqual(
            missing,
            [],
            "routes exist in main.py but are missing from README.md "
            '"What this service does": ' + ", ".join(missing),
        )
        self.assertEqual(
            stale,
            [],
            "README.md documents routes that no longer exist: " + ", ".join(stale),
        )


if __name__ == "__main__":
    unittest.main()
