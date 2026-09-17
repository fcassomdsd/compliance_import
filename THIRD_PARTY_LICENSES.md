# Third-party licenses

This repository is licensed under Apache License 2.0 for original project code and documentation.

Runtime dependencies and container images used by this project are provided by third parties and remain under their respective licenses and terms.

## Base image

| Image | Upstream project/vendor | License source |
|---|---|---|
| python:3.12-slim | Python Software Foundation / Debian | PSF License (CPython) + Debian package licenses |

This service has no other images in its own `docker-compose.yml` — it depends on `compliance_cmis` (Alfresco) and `atrocore-docker` (AtroCore) at runtime over the network, not as containers it starts itself.

## Python dependencies (`requirements.txt`, scanned with `pip-licenses` against the full resolved tree)

| Package | Version | License |
|---|---|---|
| fastapi | 0.138.0 | MIT |
| starlette | 1.3.1 | BSD-3-Clause |
| pydantic / pydantic_core | 2.13.4 / 2.46.4 | MIT |
| uvicorn | 0.49.0 | BSD-3-Clause |
| requests | 2.34.2 | Apache-2.0 |
| httpx / httpcore / h11 | 0.28.1 / 1.0.9 / 0.16.0 | BSD-3-Clause / BSD-3-Clause / MIT |
| jsonschema / jsonschema-specifications / referencing | 4.26.0 / 2025.9.1 / 0.37.0 | MIT |
| python-multipart | 0.0.32 | Apache-2.0 |
| certifi | 2026.6.17 | MPL-2.0 |
| click, idna, urllib3, anyio, attrs, charset-normalizer, rpds-py, typing-inspection, annotated-types, annotated-doc | various | MIT or BSD-3-Clause |
| typing_extensions | 4.15.0 | PSF-2.0 |

**No copyleft dependencies found.** Every resolved package (including transitive) is MIT, BSD, Apache-2.0, MPL-2.0, or PSF — all permissive and compatible with Apache-2.0 redistribution. `httpx`/`httpcore`/`h11` are `requirements-dev.txt` only (testing), not shipped in the production image.

Regenerate with: `venv/bin/pip install pip-licenses && venv/bin/pip-licenses --format=markdown --with-urls`.

## How to maintain this file

1. Add new third-party libraries or images when introduced.
2. Record version numbers used in this repository.
3. Re-run the scan above after any `requirements.txt` change.
4. Preserve required attribution and notice text when redistributing.

## Important note

This file is an operational tracking document, not legal advice.
For commercial redistribution or productization, perform a legal review of all third-party license obligations.
