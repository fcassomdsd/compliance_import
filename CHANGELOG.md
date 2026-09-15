# Changelog

All notable changes are documented in this file.

## [Unreleased]

### Added

- **`example data/demo_inspection_payload.zip` — a payload aligned with the demo dataset.** The tracked `inspection_payload.zip` targets the pre-Nomenclatura data (`inspectionCode: MDPP-I-0001`, no activity type, SUR, real MDPP location and evidence filenames), so it shares nothing with the synthetic demo dataset in `atrocore-docker`. This ZIP is keyed to it end to end — `AV-ZZZZ-A-0001` / `demo-insp-ans-01`, specialty ATS, `demo-prov-ans`, `demo-loc-zzzz` / ICAO `ZZZZ` — with three checklist items matching the demo catalog questions (`ATS-9001…9003`), two findings (one `Non-Compliance` on the handover records, one `Observation` on the occurrence feedback loop) and three small text evidence files that say "DEMO EVIDENCE" on their first line. Both payloads validate against the repository's own `schema/*.schema.json` via `models.validate()`. Note the checklist schema has no `activityType*` field — the importer resolves the activity type from the inspection — so it is deliberately absent. `run_dryrun.sh` still points at the original `inspection_payload.zip`; this one is for the demo dataset.

### Changed


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
