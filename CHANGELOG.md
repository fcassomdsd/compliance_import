# Changelog

All notable changes are documented in this file.

## [Unreleased]

### Added

- **Structured JSON logging, with a request id on every line — P3.5.** Every line this service wrote was previously free text, which a log aggregator can store and little else: greppable, but "errors in the last hour" or "everything for this upload" needed a parser per message shape. `structured_logging.py` emits one JSON object per line with `ts`, `level`, `service`, `logger`, `msg` and whatever a caller passed as `extra`.

  It reconfigures **uvicorn's** loggers too, not just the root. `logging.basicConfig` reaches only the root logger, while uvicorn installs its own handlers on `uvicorn`, `uvicorn.error` and `uvicorn.access`; left alone they keep writing their text format into the same stream, and Promtail parses a container's output as one format or the other — a stream that is 90% JSON is a stream that is not JSON.

  A **request id** is bound per request by middleware and echoed back as `X-Request-Id`. An import is a multi-step operation logging from several modules, and without a correlation id, telling one upload's lines from another's under concurrent load means guessing from timestamps. An inbound `X-Request-Id` is honoured so a trace can span the gateway and this service, capped at 64 characters — it lands in every log line, and an unbounded caller-supplied string in a log field is a way to make logs expensive to store.

  Timestamps are genuinely UTC. `logging`'s default converter is localtime, so a formatter that writes a trailing `Z` without an explicit UTC converter claims UTC and carries the host's wall clock — an error that only surfaces while correlating an incident across machines, which is the worst possible moment to find it. Covered by a test.

  Uvicorn's `color_message` extra is dropped: every uvicorn record carries an ANSI-coloured duplicate of its own message under that name, which doubled the size of every uvicorn line for a second copy of text already in `msg`.

  JSON when `APP_ENV=production`, text otherwise, and `LOG_FORMAT=json|text` overrides both ways — a developer reading a terminal is not a log aggregator.

### Security

- **Alfresco tickets are no longer written to the log.** This was a live leak, not a precaution. `resolve_ticket_identity` calls Alfresco with `params={"alf_ticket": ticket}`, and `AlfrescoClient._check_response` logs `response.request.url` on any failure — so a rejected operator ticket was written to stdout in full. An Alfresco ticket is a bearer credential: anyone holding it is that user until it expires.

  The redaction happens in the **formatter**, where it cannot be forgotten at a call site, and it applies in text mode as well as JSON — a ticket in a development log is still a live credential, and a developer is far more likely to paste a log excerpt into a chat than to ship it anywhere. Other query parameters are left intact, because a redaction that ate the whole URL would destroy the one thing the line is there for: knowing which request failed.

  It was survivable while logs stayed on one host. It is not, now that P3.5 ships them to a log aggregator.

### Changed

- **`BIND_IP` controls which host interface published ports listen on — P3.3.** Every published port in this repo now binds through `${BIND_IP:-0.0.0.0}`. The default preserves current behaviour exactly: the demo quickstart and `demo-verify-ci.sh` reach services over the network, and under dind `DEMO_HOST` is `docker` rather than localhost, so a hardcoded loopback bind would break the whole-stack guard. A production deployment sets `BIND_IP=127.0.0.1`, leaving `compliance_web`'s TLS edge on 443 as the only externally published port. See "An ideal production configuration.md" §2.3.

### Security

- **Container hardening — P3.2.** No service in this platform previously declared a resource limit, a non-root user, a read-only root filesystem, dropped capabilities or `no-new-privileges`. What each service can take differs, and the differences are recorded as comments in the compose files rather than silently skipped:

  - **Full hardening** (read-only rootfs, non-root user, `cap_drop: ALL`, `no-new-privileges`, CPU/memory limits) where the service writes nothing to its own filesystem. Verified by booting each one, not just by rendering the config.
  - **Partial, with the reason stated in-file**, where a control is structurally inapplicable rather than merely postponed: Postgres chowns its data directory and drops privileges at startup, so `cap_drop: ALL` and a read-only rootfs break it; Node-RED must write `flows.json` into a bind mount, which is its deployment model; AtroCore installs itself into a bind mount at first run and Apache binds `:80` as root; the Alfresco JVM services write caches, logs and indexes inside their own filesystems.

### Added

- **Supply-chain scanning in CI — P3.2.** No repository in this platform had any security scanning before this. A new `security:scan` job (GitLab, mirrored to GitHub Actions) runs Trivy over the dependency tree and produces a CycloneDX SBOM as an artifact.

  The gate policy was chosen from measurement, not aspiration. **CRITICAL is blocking**: measured at zero across all six repos, so the gate is green today and genuinely stops a regression rather than being red on arrival. **HIGH is reported but not blocking**: 33 findings exist today (21 in `compliance_web`, 12 in `compliance_checklist`), every one with a fix available. Blocking on HIGH immediately would red those pipelines and the gate would be switched off within a day — which is worse than no gate, because a disabled gate still reads as protection. Clear the backlog, then raise the bar.

  `--ignore-unfixed` keeps the gate actionable: a CVE with no available fix is information, not a task. `--skip-dirs` excludes generated and bind-mounted runtime trees — `web-data/` in particular is the AtroCore application installed at container bootstrap, gitignored and absent from a fresh checkout, which vendors its own npm tree; scanning it reports upstream's dependencies as if they were ours. It is not clean (upstream vendors a CRITICAL prototype-pollution advisory in `swiper`), but that belongs in an upstream report and in image scanning, not a gate on tracked source.

### Changed

- **Dependencies are pinned to exact versions and SHA-256 hashes — P3.2 (supply chain).** `requirements.txt` was five bare package names: no versions, no lockfile, no hashes. Two builds a week apart could install different code, and a compromised release on PyPI would have been pulled silently. It is now **generated** by `pip-compile --generate-hashes` from a new `requirements.in` (which holds the top-level intent), pinning 23 packages with 448 hashes that pip verifies on install; `requirements-dev.txt` is generated the same way from `requirements-dev.in`. Do not hand-edit the two `.txt` files — the regeneration command is in the header of each.

  The lockfile is deliberately generated **inside `python:3.12-slim`**, the image this service actually runs, rather than on a developer's interpreter. A first attempt resolved on Python 3.14 (what the local venv happens to be) and would have pinned a set never validated against the runtime; dependency resolution is Python-version-specific, so the lockfile has to come from the target. Verified end to end in that image: hashes accepted, `pip check` clean, 118 tests pass.

- **The base image is pinned by digest** (`python:3.12-slim@sha256:...`) as well as tag, so a re-pushed upstream tag cannot silently change the build.

### Added

- **`IMPORT_API_KEY` now resolves from a file, and `APP_ENV=production` refuses an insecure configuration — P3.1 (production secrets).** The Alfresco credentials already resolved by precedence (`<NAME>_FILE` → `/run/secrets/<name>` → the environment variable); that logic moves into a new `secret_config.py` shared with the API key, matching `compliance_flow/data/secrets.js` and `compliance_web/server/config/secrets.cjs` so the platform has one shape. The key is resolved **per request rather than cached at import**, so a secret manager rewriting the file takes effect without restarting the container — covered by a test that rotates the file mid-flight and asserts the old key stops working and the new one starts. With `APP_ENV=production` the service now refuses to start when a required secret is missing or still holds a value published in this repository. `IMPORT_API_KEY` counts as required there specifically because leaving it unset **does not fail closed** — it disables the API-key middleware and leaves `/inspection-import` and `/followup-import` open. Development and the demo are unaffected: the guard is a no-op unless `APP_ENV=production`, which the demo does not set.

### Changed

- **A `<NAME>_FILE` pointing at a missing or empty file is now a hard failure instead of a silent fallback.** The previous resolver in `alfresco_client.py` fell through to the Docker secret and then the plain environment variable, so deleting the file a secret manager was supposed to write left the service running against a stale credential — a failed rotation that looks like a successful one. It now raises. `SecretResolutionError` subclasses `ValueError`, preserving the old contract exactly, so existing `except ValueError` handlers are unaffected.

- **The new module is named `secret_config.py`, not `secrets.py`.** This directory is on `sys.path`, so a module named `secrets.py` shadows the standard library's `secrets` for every import in the process — verified during development: `secrets.token_hex` disappeared entirely, which would break any dependency reaching for it. A regression test asserts the stdlib module still resolves to the stdlib.

### Fixed

- **Schema `format` keywords (`date`, `date-time`) are now enforced.** `models.py` passed no `format_checker` to `jsonschema.validate`, so a payload carrying `startDate: "NOT-A-DATE"` validated clean and reached Alfresco as a malformed date. A regression test now pins the rejection.
- **`.dockerignore` now excludes `.env` and `.venv/`.** `Dockerfile` uses `COPY . .`, so a developer's local `.env` (and the full `.venv/`) was baked into the image build context; only `venv/` was listed. Matches `CONTRIBUTING.md`'s "never commit `.env`, `venv/`, `.venv/`" rule.

### Documentation

- **README ID table corrected to the canonical `AV-XXXX-T-####` activity format** (was the bare `XXXX-T-####`), with a note that the importer's input validation accepts the optional `AV-` prefix and that `XXXXT####` is the compact form (`AV-MDPP-I-0001` → `MDPPI0001`).

## [2026-09-18]

### Added

- **`THIRD_PARTY_LICENSES.md`, backed by a `pip-licenses` scan of the full resolved dependency tree.** No copyleft dependencies found — every package is MIT, BSD, Apache-2.0, MPL-2.0, or PSF.


### Changed

- **`IMPORT_API_KEY` ships enabled by default (`.env.docker.example`), and `/health` is now exempt from it.** The gateway posture across the platform was "auth code exists but is off" — this flips the default so a cloned/demo stack is not an open service. The shipped value is a public placeholder shared with `compliance_flow`'s `API_KEY` and `compliance_web`'s `NODE_RED_API_KEY`; it must be rotated before any real deployment. Turning it on exposed a real bug the middleware always had: it protected *every* route including `GET /health`, so a keyed deployment's own compose healthcheck and the `atrocore-docker` demo quickstart's readiness probe (neither sends `X-API-Key`) would have failed with `401` instead of `200`. `_require_api_key` now exempts `/health` explicitly before the key check runs. `test_health_endpoint_does_not_require_auth` previously never set `IMPORT_API_KEY`, so it passed trivially without exercising the keyed case at all — two new tests cover it: `/health` returns `200` with no header even when a key is configured, and a real route still returns `401` without one. **A second gap found during live verification**: `docker-compose.yml`'s `environment:` block never actually listed `IMPORT_API_KEY`, so the container never saw it regardless of what `.env` held — `.env.example`/`.env.docker.example` documenting a variable does not make Compose pass it through. Added `IMPORT_API_KEY: ${IMPORT_API_KEY:-}` alongside the other passed-through vars. Verified live end to end against the running stack: bare request `401`, correct key `200`(-equivalent, `422` on a route needing a body), wrong key `401`, and `/health` `200` with no header, a wrong key, or nothing at all — before *and* after an image rebuild, confirming the fix isn't just present in source but actually running.

- **The demo payloads now carry their USOAP chain references, so the demo actually exercises USOAP evidence tagging.** Each checklist item in `demo_inspection_payload.zip` and `demo_met_inspection_payload.zip` gained a `reference.usoapPqReference` entry — the synthetic PQ its specialty resolves to, with the ICAO Critical Element and area (`ATS-900x` → `PQ 99.001`/`CE-5`/`ATS`, `MET-900x` → `PQ 99.003`/`CE-2`/`MET`), matching the citation chain `atrocore-docker/sql/seed-demo-dataset.sql` seeds. Nothing in this service resolves that chain: the canonical import writes `vso:usoapPqReference`, `vso:ceMapping`, `vso:usoapCriticalElement`, `vso:usoapAreaCode` and `vso:usoapTagSource = "Chain-derived"` only when the payload already carries the resolved reference, so the demo imported fully untagged documents and `POST /api/usoap/ce-evidence-report` reported `total: 0` for every Critical Element — the platform's USOAP evidence organisation was invisible in the demo. The schema already allowed the field, so no schema change. **Verified live**: after re-importing the two payloads and running the canonical import, all six demo checklist items and both ATS findings carry `vso:usoapPqReference` with `vso:usoapTagSource = "Chain-derived"`, and the CE-5 report returns 5 artifacts (2 findings + 3 checklist items) grouped under `PQ 99.001`/area `ATS`, with its gap analysis flagging the missing `vso:usoapEvidenceBasis` on each. `tests/test_example_payloads.py` asserts the reference is present and matches the item's specialty.

### Fixed

- **Fixed: updating an existing document's content failed with `415` from Alfresco.** `_update_node_content` sent the payload as `multipart/form-data` (`files=`), which is right for the create path but rejected by Alfresco's v1 update-content endpoint — it takes the raw bytes with the file's own `Content-Type`. Importing a payload for the first time therefore worked while re-importing the same payload failed, which is exactly what the demo quickstart hits on its second run. The path was untested because the only test that reached it replaced the method with a fake; there is now a test asserting the request shape (raw `data`, the file's `Content-Type`, and no `files=`).
### Added

- **`example data/demo_met_inspection_payload.zip` — the second inspection payload, so both seeded demo inspections have a window.** The demo dataset seeds two inspections (`AV-ZZZZ-A-0001` ATS and `AV-ZZZZ-I-0001` MET) but only the ATS one had a payload, so the MET inspection had no canonical documents and — because the inspection **window** lives on the Alfresco inspection folder (`vso:startDate`/`vso:endDate`; AtroCore's `inspection` table has no date columns of its own) — no window either. Its items could therefore never be dated and dropped out of the year-filtered provider-history report. The ZIP carries the three MET catalog questions (`MET-9001…9003`, the `9xxx` demo range), one small evidence file per item, the MET specialty (`Meteorología aeronáutica`), and a two-day window (`2026-10-07` → `2026-10-08`). Verified live against the running stack: `{"status":"imported","inspectionId":"demo-insp-met-01","findingsImported":0,"evidenceImported":3}`, then the canonical import created `…/Vigilancia/Inspecciones/AV-ZZZZ-I-0001` with `vso:startDate`/`vso:endDate` set. Note both demo windows are **fixed dates** while `atrocore-docker/sql/seed-demo-dataset.sql` computes the site visit's as `CURRENT_DATE + 21`/`+ 22`, so they agree only near the day the payloads were written — documented in the README, and harmless for the demo because both stay inside the year the report filters on. **Superseded (2026-09-16):** the payloads are now stamped with the seeded window before they are imported, so the tracked dates are a template rather than what the demo runs on — see *Changed* above.
- **`tests/test_example_payloads.py` — the tracked demo payloads are now validated in CI.** Nothing checked them, so the contract documentation for `/inspection-import` and `/followup-import` could drift into a `422` on the documented demo path unnoticed. The tests validate each inspection payload's `checklist.json` (and `findings.json` when present) against the schemas this service enforces, assert that both `startDate` and `endDate` are present, that every `evidenceItems[].source` resolves to a file inside the ZIP, and that the follow-up payload's `followup-reports.json`/`prior-findings.json` validate with a `FollowUpEvidence/` folder present. 84 tests pass.
- **`example data/demo_inspection_payload.zip` — a payload aligned with the demo dataset.** The tracked `inspection_payload.zip` targets the pre-Nomenclatura data (`inspectionCode: MDPP-I-0001`, no activity type, SUR, real MDPP location and evidence filenames), so it shares nothing with the synthetic demo dataset in `atrocore-docker`. This ZIP is keyed to it end to end — `AV-ZZZZ-A-0001` / `demo-insp-ans-01`, specialty ATS, `demo-prov-ans`, `demo-loc-zzzz` / ICAO `ZZZZ` — with three checklist items matching the demo catalog questions (`ATS-9001…9003`), two findings (one `Non-Compliance` on the handover records, one `Observation` on the occurrence feedback loop) and three small text evidence files that say "DEMO EVIDENCE" on their first line. Both payloads validate against the repository's own `schema/*.schema.json` via `models.validate()`. Note the checklist schema has no `activityType*` field — the importer resolves the activity type from the inspection — so it is deliberately absent. `run_dryrun.sh` still points at the original `inspection_payload.zip`; this one is for the demo dataset. **Corrected:** `findings.json` must be a bare JSON array of `{schemaVersion, finding}` entries — the first version wrapped it in `{findings: [...]}`, which the importer rejects with `422 'finding' is a required property`; the tracked test payload had the array form all along and `models.validate()` on the inner entries does not catch the difference. Verified by importing: `{"status":"imported","findingsImported":2,"evidenceImported":3}`.

### Added

- **`example data/demo_followup_payload.zip` — the first tracked follow-up payload, plus the contract it has to satisfy.** It closes `H-ZZZZA0001-ATS-001` (Closure Verification, `effectivenessConfirmed: true`) with its source finding and evidence. Building it established three non-obvious requirements now documented in the README: the entries are `followup-reports.json` and `prior-findings.json` (`prior-findings.json` is mandatory), the evidence folder is `FollowUpEvidence/` and not `Evidence/`, and the comment field is `followUpComment` (`comments` is rejected — the schema sets `additionalProperties: false`). Verified: `{"status":"imported","followUpReportsImported":1,"followUpEvidenceImported":1}`. **Correction (2026-09-15):** the closure path *does* work — this was a wrong call on my part, not a gap. `GET /importCanonical?inspectionId=…&specialty=…` carries no follow-up context, so `closurePolicy.shouldClose` never ran; the follow-up-aware call does. `POST /api/inspection/import-canonical` with `followUpFiles: ["FollowUp H-ZZZZA0001-ATS-001 01.json"]` returns `pendingClosureApprovals: 1` and moves the finding to `Pending Closure Approval`, where a reviewer approves or rejects it via compliance_web's `PATCH /findings/:findingId/closure-review`.

### Changed

- **The demo payloads' dates are now derived from the seeded site visit instead of being fixed in the ZIP.** `atrocore-docker/sql/seed-demo-dataset.sql` computes the site visit's window relative to the day it is seeded (`CURRENT_DATE + 21`/`+ 22`), but a committed ZIP freezes its dates the day it is written (`2026-10-06`/`2026-10-07` for ATS, `2026-10-07`/`2026-10-08` for MET, findings issued `2026-10-07`, follow-up `2026-10-20`) — and the window is not cosmetic: the canonical import copies `checklist.startDate`/`endDate` onto the Alfresco inspection folder, which is the only place an inspection's window lives, so a stale payload dates the demo's inspection into the wrong week and its checklist items fall out of the year-filtered provider-history report. New `scripts/stamp-payload-window.py` rewrites a copy of a payload onto a given window: `checklist.startDate`/`endDate` land on the window's first/last day, every other date is shifted by the same delta as the window's last day (so a finding issued on the inspection's last day stays there), and the follow-up is dated 13 days after the window ends (`--follow-up-lag-days`) because it belongs to an inspection in another ZIP and so carries no window of its own. `atrocore-docker/scripts/demo-quickstart.sh` reads the window back from the seeded `site_visit` row, stamps all three payloads, imports the stamped copies, and step 6 now fails unless both inspection folders carry exactly that window. The tracked ZIPs stay pristine **templates** — importing one by hand still imports its template dates — and re-stamping for the same window is a no-op, so the quickstart stays idempotent. `tests/test_stamp_payload_window.py` pins the derivation to those templates: the window lands exactly on the target, findings keep their distance from the window's end, a longer window still ends on its last day, evidence entries are copied byte for byte, the templates are never modified, and a ZIP with no payload entry is rejected. 93 tests pass (9 of them new).

- **README points at the whole-platform demo quickstart, which lives in `atrocore-docker`.** `run_dryrun.sh` proves this service in isolation; §7 of `atrocore-docker/docs/COMPLIANCE_INTEGRATION_RUNBOOK.md` — executable as `atrocore-docker/scripts/demo-quickstart.sh`, which posts the tracked `example data/demo_inspection_payload.zip` and `example data/demo_followup_payload.zip` — exercises it against a running stack and walks the resulting finding through closure. The README now links to it. No code, schema or payload changed.
- **BREAKING** — adopted the platform-wide Nomenclatura ID formats:
  - `inspectionCode`: `XXXX-NNN` → `XXXX-T-####` (activity-type letter, 4-digit sequence)
  - `checklistId`: `CHK-XXXXNNN-EEE` → `LV-XXXXT####-EEE`
  - `findingId`: `XXXXNNN-EEE-NN` → `H-XXXXT####-EEE-###` (3-digit sequence)
  - `capId`: `CA-XXXXNNNYYY-SS-VV` → `P-XXXXT####-EEE###-##`
  - `followUpId`: `FU-XXXXNNNYYY-MM-VV` → `S-XXXXT####-EEE###-##`
- **BREAKING** — `specialtyCode` and checklist `itemCode`/`checklistItemCode` patterns
  tightened to 3–4 uppercase letters (`^[A-Z]{3,4}$`), matching the new flat 16-code
  specialty vocabulary. This also fixes the previous inability to express codes that
  contained `/`.
- **BREAKING** — CAP and follow-up sequences are now 1-based; the first follow-up stored
  for a finding is `01` (was `00`), aligning with the already 1-based finding sequence.
- Checklist documents are stored in Alfresco as `Checklist <checklistId>.json`
  (was `Checklist <inspectionCode> <specialtyCode>.json`), matching the convention
  already used for findings and follow-ups.
- Example payloads under `example data/` migrated to the new ID formats.
- **Versioning and tagging standardised across the platform.** Releases are tagged `YYYY-MM-DD` (CalVer) after the date of the newest `## [YYYY-MM-DD]` CHANGELOG section, with `YYYY-MM-DD.2` for a second release on the same day. The release jobs now run `scripts/release-tag.sh`, which fails when that section is missing, when `CHANGELOG.md` is unchanged since the previous release, or when the tag already exists; `scripts/release-tag.test.sh` is its self-test. See CONTRIBUTING.md, "Versioning and releases".
- **Endpoint manifest now guarded by a test.** `tests/test_endpoint_manifest.py` asserts the README's "What this service does" endpoint list matches the FastAPI routes, so a route added/removed without a README update fails the unittest suite.

### Removed

- Unused date-based follow-up ID path (`build_followup_id`,
  `_format_followup_date_yy_mm_dd`); the Nomenclatura sequence suffix is a plain counter.

## [0.2.1] - 2026-08-01

### Added
- `findingSeverity` property to finding JSON schema (enum: A/B/C)
- `resolutionDeadline` auto-calculation from severity: dateIssued + {A:7, B:30, C:90} days
- `targetResidualRisk` and `achievedResidualRisk` to finding JSON schema (enum: Low/Medium/High/Critical)
- `currentResidualRisk` to followup-report JSON schema (enum: Low/Medium/High/Critical)
- `Pending Closure Approval` status added to finding status enum

## [0.2.0] - 2026-06-21

### Added
- API key authentication via `X-API-Key` header and `IMPORT_API_KEY` env var.
- Upload size limits: 400 MB ZIP, 500 MB total extracted, 50 MB per file, configurable via env vars.
- ZIP bomb protection: compression ratio check (default 100:1), per-file and total decompressed size tracking.
- Path traversal protection in ZIP extraction.
- `GET /health` endpoint returning `{"status": "ok"}`.
- `ALFRESCO_RETRY_READ` env var (default `1`) — read timeouts now retried.
- Lazy-loaded JSON schemas with clear error on missing/corrupt schema files.
- Python `logging` module integration for structured log output.
- Shared `FakeAlfrescoClient` extracted to `tests/support/` for reuse across test files.
- Integration test directory (`tests/integration/`) with opt-in real-Alfresco tests.
- Non-root user in Docker container.

### Changed
- Node-RED sequence API dependency eliminated; follow-up sequencing now done locally via Alfresco list-children.
- Default `ALFRESCO_URL` changed to `http://proxy:8080/alfresco/...` for consistency.
- Default canonical path aligned to `Vigilancia/Datos de campo` everywhere.
- `id_utils.py`: `_parse_inspection_code` and `_finding_segment_for_followup_and_corrective_action` now raise `ValueError` on invalid input instead of returning sentinel junk values.
- Evidence mapping from `_validate_followup_evidence_sources` now reused instead of rebuilt.
- `store_followup_evidence_file` now delegates to `store_evidence_file` (removed duplicate implementation).
- `_check_response` no longer leaks raw Alfresco response body in error messages.
- `main.py` error handling reorganized for clarity.

### Removed
- `SEQ_API_URL` and `DEFAULT_SEQ_API_URL` — eliminated Node-RED dependency from codebase and all config files.
- `_get_next_followup_seq` replaced with `_resolve_next_followup_seq` (Alfresco-based).
- Dead code from `AlfrescoClient`: `create_inspection`, `create_checklist`, `create_checklist_item`, `upload_evidence`, `create_finding` (vso:* structured model methods, unused by JSON pipeline).
- `httpx` from `requirements.txt` (unused dependency).
- Module-level schema loading replaced with lazy `_load_schemas()` function.

### Fixed
- Response body on 502 errors no longer leaks raw Alfresco error details.

## [2026-05-17] - Develop to Main Release

This release captures all changes in `develop` since `main` and is intended for merge into `main`.

### Added
- Follow-up import pipeline with a dedicated API endpoint and related schemas.
- Deterministic identifier utility module (`id_utils.py`) and associated tests.
- New schemas for follow-up report and follow-up source finding payloads.
- Expanded governance and onboarding documents (`CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `LICENSE`, `NOTICE`).
- Additional test coverage for API behavior, checklist field handling, follow-up IDs, and transformer processing.
- Example payloads and evidence archives under `example data/`.

### Changed
- Checklist ingestion now supports updated location and specialty metadata.
- Transformer and ingestion flow aligned to canonical payload keys and explicit findings contract.
- Identifier patterns refactored to a unified nomenclature, with docs and tests updated accordingly.
- Follow-up handling improved to preserve `followUpId` and return stored follow-up filenames.
- Core ingestion-related files updated: `main.py`, `transformer.py`, `models.py`, and `alfresco_client.py`.
- Docker and local run support updated (`docker-compose.yml`, `.env.docker.example`, `run_dryrun.sh`, `requirements.txt`).

### Fixed
- Backfilled missing follow-up report `capId` from source findings when absent.
- Added finding-location mapping from checklist ICAO/location fields.
- Corrected finding-to-checklist item association logic.

### Removed
- Legacy/unused ingestion schemas: `schema/session.schema.json` and `schema/inspection.schema.json`.

### Commits Included
- 26 commits from `main..develop`.
