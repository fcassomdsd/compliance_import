# Changelog

All notable changes are documented in this file.

## [Unreleased]


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
