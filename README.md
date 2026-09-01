# Compliance Import Service

FastAPI service that imports inspection and follow-up payloads from ZIP files, validates JSON content against schemas, enriches records, and stores canonical documents in Alfresco.

## What this service does

- Exposes three endpoints:
  - `GET /health`
  - `POST /inspection-import`
  - `POST /followup-import`
- Supports optional API key authentication via `X-API-Key` header (configured with `IMPORT_API_KEY`).
- Validates incoming JSON using the schemas in `schema/`.
- Performs domain transformations (for example, finding enrichment from checklist data).
- Protects against ZIP bombs and enforces upload size limits.
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

If `IMPORT_API_KEY` is configured, include the `X-API-Key` header:

```bash
curl -X POST "http://127.0.0.1:8000/inspection-import" \
  -H "X-API-Key: your-api-key" \
  -F "file=@/absolute/path/to/inspection_payload.zip"
```

Without API key configured (development mode):

```bash
curl -X POST "http://127.0.0.1:8000/inspection-import" \
  -F "file=@/absolute/path/to/inspection_payload.zip"

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
    "FollowUp H-MDPPI0001-SUR-001 01.json"
  ]
}
```

`followUpFilenames` helps clients reference the exact JSON documents created in Alfresco.

## ID formats (Nomenclatura)

All identifiers follow the platform-wide naming standard. `XXXX` is the 4-character ICAO
location code, `T` the activity-type letter, `EEE` the specialty code, `#` a digit.

| Content type | Format | Example |
|---|---|---|
| Actividad de vigilancia (`inspectionCode`) | `XXXX-T-####` | `MDPP-I-0001` |
| Lista de verificación (`checklistId`) | `LV-XXXXT####-EEE` | `LV-MDPPI0001-SUR` |
| Hallazgo (`findingId`) | `H-XXXXT####-EEE-###` | `H-MDPPI0001-SUR-001` |
| Plan de acciones correctivas (`capId`) | `P-XXXXT####-EEE###-##` | `P-MDPPI0001-SUR001-01` |
| Seguimiento (`followUpId`) | `S-XXXXT####-EEE###-##` | `S-MDPPI0001-SUR001-01` |

Notes:

- `XXXXT####` is the activity code with dashes stripped (`MDPP-I-0001` → `MDPPI0001`).
  The activity code is independent of any site-visit code.
- Activity types: `A` Auditoría, `I` Inspección, `M` Monitoreo, `D` Revisión documental,
  `S` Análisis de suceso.
- Specialty codes are 3–4 uppercase letters: `APR, AVIS, FAU, PAV, SSEI, AIM, ATS, COM,
  ECNS, EMET, FIS, MET, NAV, SAR, SUR, DPR`.
- Finding sequences are 3 digits and **1-based** (`001` is the first finding); CAP and
  follow-up sequences are 2 digits and 1-based (`01` is the first).
- Alfresco document names embed the canonical ID: `Checklist <checklistId>.json`,
  `Finding <findingId>.json`, `FollowUp <findingId> <NN>.json`.

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
  - if source finding has `correctiveAction.capId` (format `P-XXXXT####-EEE###-##`) and the
    report omits `capId`, it is backfilled
  - if both exist and differ, import fails
- Follow-up JSON filenames use sequence-based naming:
  - `FollowUp <findingId> <NN>.json` (for example `FollowUp H-MDPPI0001-SUR-001 01.json`)
  - the sequence is 1-based; the first follow-up for a finding is `01`
  - the stored `followUpId` is regenerated from that sequence as `S-XXXXT####-EEE###-##`,
    overwriting any temporary ID supplied in the payload

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

- `ALFRESCO_URL` (default: `http://proxy:8080/alfresco/api/-default-/public/alfresco/versions/1`)
- `ALFRESCO_CANONICAL_JSON_PATH` (default: `Sites/vigilancia-de-la-so/documentLibrary/Vigilancia/Datos de campo`)
- `ALFRESCO_USERNAME`
- `ALFRESCO_PASSWORD`
- `ALFRESCO_USERNAME_FILE`
- `ALFRESCO_PASSWORD_FILE`
- `ALFRESCO_TIMEOUT_SECONDS` (default: `20`)

Authentication:

- `IMPORT_API_KEY` — if set, all requests must include `X-API-Key` header matching this value

Upload limits:

- `MAX_UPLOAD_SIZE_BYTES` (default: `419430400` — 400 MB)
- `MAX_EXTRACTED_TOTAL_SIZE` (default: `524288000` — 500 MB)
- `MAX_EXTRACTED_FILE_SIZE` (default: `52428800` — 50 MB)
- `MAX_COMPRESSION_RATIO` (default: `100`)

Retry settings:

- `ALFRESCO_RETRY_TOTAL` (default: `3`)
- `ALFRESCO_RETRY_CONNECT` (default: `3`)
- `ALFRESCO_RETRY_READ` (default: `1`)
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

- `401 Invalid or missing API key`
  - `IMPORT_API_KEY` is configured but the request did not include a matching `X-API-Key` header.
- `400 Uploaded file is not a valid ZIP`
  - Uploaded payload is not a readable ZIP file.
- `400 ZIP payload exceeds maximum total decompressed size`
  - The total extracted size of all files in the ZIP exceeds `MAX_EXTRACTED_TOTAL_SIZE`.
- `400 File exceeds maximum decompressed size`
  - A single file in the ZIP exceeds `MAX_EXTRACTED_FILE_SIZE`.
- `400 File has suspicious compression ratio`
  - A file's compression ratio exceeds `MAX_COMPRESSION_RATIO` (possible ZIP bomb).
- `400 Invalid ZIP payload: unsafe file path`
  - ZIP contains a path traversal attempt (e.g., `../escape.txt`).
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
