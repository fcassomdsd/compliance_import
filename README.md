# Compliance Import Service

FastAPI service that imports inspection and follow-up payloads from ZIP files, validates JSON content against schemas, enriches records, and stores canonical documents in Alfresco.

## What this service does

- Exposes two endpoints:
  - `POST /inspection-import`
  - `POST /followup-import`
- Validates incoming JSON using the schemas in `schema/`.
- Performs domain transformations (for example, finding enrichment from checklist data).
- Stores JSON documents and evidence files in Alfresco under:
  - `<ALFRESCO_CANONICAL_JSON_PATH>/<specialtyName>/...`

## Quick start (local)

### 1. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Note: This repository may already include `.venv/` in some developer setups. The scripts use `venv/` by default.

### 2. Configure Alfresco credentials

The service requires credentials and resolves them in this order for each value (`ALFRESCO_USERNAME`, `ALFRESCO_PASSWORD`):

1. `ALFRESCO_*_FILE`
2. `/run/secrets/alfresco_*`
3. `ALFRESCO_*`

Example:

```bash
export ALFRESCO_USERNAME="admin"
export ALFRESCO_PASSWORD="admin"
```

### 3. Run the API

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

### 4. Upload a ZIP payload

Inspection:

```bash
curl -X POST "http://127.0.0.1:8000/inspection-import" \
  -F "file=@/absolute/path/to/inspection_payload.zip"
```

Follow-up:

```bash
curl -X POST "http://127.0.0.1:8000/followup-import" \
  -F "file=@/absolute/path/to/followup_payload.zip"
```

## API responses

Inspection response:

```json
{
  "status": "imported",
  "inspectionId": "inspection-1",
  "findingsImported": 2,
  "evidenceImported": 3
}
```

Follow-up response:

```json
{
  "status": "imported",
  "followUpReportsImported": 1,
  "followUpEvidenceImported": 1,
  "followUpFilenames": [
    "FollowUp MDPP001-VIG-01 01.json"
  ]
}
```

`followUpFilenames` helps clients reference the exact JSON documents created in Alfresco.

## Payload contracts

### Inspection import (`POST /inspection-import`)

Required ZIP contents:

- `checklist.json` (required)
- Findings provided as either:
  - `findings.json` (array or single object), or
  - one or more `finding*.json` files
- Optional evidence files:
  - any non-JSON files anywhere in the ZIP are treated as evidence

Behavior notes:

- `checklist.items[].evidenceItems` accepts:
  - array (preferred)
  - single object (auto-normalized to one-item array)
  - `null` (normalized to `[]`)
- Each finding must map to a checklist item via `finding.checklistItemCode`.
- `finding.requirementBreached` is auto-populated from checklist item text fields.
- Missing finding metadata may be backfilled from checklist metadata (`specialty*`, `providerId`, `location*`).

### Follow-up import (`POST /followup-import`)

Required ZIP contents:

- `prior-findings.json` (required)
  - array of source findings for linking
  - can be either flattened finding objects or wrapped objects with a `finding` key
- `followup-reports.json` (required)
  - array of follow-up report objects
- `FollowUpEvidence/` folder (required)
  - evidence files referenced by each report's `evidenceItems[].source`

Behavior notes:

- Each follow-up report is matched to a source finding by `findingId`.
- `capId` consistency is enforced:
  - if source finding has `correctiveAction.capId` and report omits `capId`, it is backfilled
  - if both exist and differ, import fails
- Follow-up JSON filenames use sequence-based naming:
  - `FollowUp <findingId> <NN>.json` (for example `FollowUp MDPP001-VIG-01 01.json`)

## Sample ZIP layouts

These examples show the minimum structure expected by each endpoint.

### Inspection payload example

```text
inspection_payload.zip
|-- checklist.json
|-- findings.json
|-- evidence-photo-01.jpg
`-- attachments/
  `-- supporting-note.txt
```

Valid alternatives for findings:

- `findings.json` with one object or an array of objects
- one or more files named like `finding-1.json`, `finding-2.json`, and so on

### Follow-up payload example

```text
followup_payload.zip
|-- prior-findings.json
|-- followup-reports.json
`-- FollowUpEvidence/
  |-- proof-01.pdf
  `-- image-01.jpg
```

Important:

- `FollowUpEvidence/` must exist (it can be empty only if reports have no `evidenceItems`).
- Each `followUpReport.evidenceItems[].source` must match a file name inside `FollowUpEvidence/`.

## Validation schemas

- `schema/checklist.schema.json`
- `schema/finding.schema.json`
- `schema/followup-report.schema.json`
- `schema/followup-source-finding.schema.json`

## Configuration

Core environment variables:

- `ALFRESCO_URL`
- `ALFRESCO_CANONICAL_JSON_PATH`
- `ALFRESCO_USERNAME`
- `ALFRESCO_PASSWORD`
- `ALFRESCO_USERNAME_FILE`
- `ALFRESCO_PASSWORD_FILE`
- `ALFRESCO_TIMEOUT_SECONDS` (default: `20`)
- `SEQ_API_URL` (default: `http://node-red:1880`)

Retry settings:

- `ALFRESCO_RETRY_TOTAL` (default: `3`)
- `ALFRESCO_RETRY_CONNECT` (default: `3`)
- `ALFRESCO_RETRY_STATUS` (default: `3`)
- `ALFRESCO_RETRY_BACKOFF_SECONDS` (default: `0.5`)

## Docker usage

```bash
cp .env.docker.example .env
cp docker/secrets/alfresco_username.txt.example docker/secrets/alfresco_username.txt
cp docker/secrets/alfresco_password.txt.example docker/secrets/alfresco_password.txt
# edit .env and docker/secrets/*.txt

docker compose up --build -d
```

Endpoints:

```text
http://127.0.0.1:8000/inspection-import
http://127.0.0.1:8000/followup-import
```

## Dry-run script

Use `run_dryrun.sh` to start the API, post a configured sample ZIP, print the response, and stop the server automatically.

```bash
./run_dryrun.sh
```

## Running tests

All tests:

```bash
venv/bin/python -m unittest -v
```

Selected tests:

```bash
venv/bin/python -m unittest tests/test_main_api.py -v
venv/bin/python -m unittest tests/test_transformer_process_session.py -v
```

## License

This project is licensed under the Apache License, Version 2.0.

- See `LICENSE` for the full license text.
- See `NOTICE` for attribution details.
- Copyright 2026 Fernando A. Casso Rodriguez.

## Error handling and troubleshooting

- `400 Uploaded file is not a valid ZIP`
  - Uploaded payload is not a readable ZIP file.
- `400 Missing checklist.json in ingestion payload`
  - Inspection ZIP is missing `checklist.json`.
- `400 Missing prior-findings.json in follow-up payload`
  - Follow-up ZIP is missing source findings file.
- `400 Missing followup-reports.json in follow-up payload`
  - Follow-up ZIP is missing reports file.
- `400 Missing FollowUpEvidence folder in follow-up payload`
  - Follow-up ZIP is missing required evidence directory.
- `422 ...`
  - JSON schema validation error for checklist, findings, or follow-up reports.
- `502 Alfresco request failed (...)`
  - Upstream Alfresco call failed after retry policy.

If `curl` returns `Failed to open/read local data`, use an absolute path for `@/path/to/file.zip`.
