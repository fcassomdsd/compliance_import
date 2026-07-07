# Changelog

All notable changes are documented in this file.

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
