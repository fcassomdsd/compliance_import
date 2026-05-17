# Changelog

All notable changes are documented in this file.

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
