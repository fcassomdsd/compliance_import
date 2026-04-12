# Compliance Import Service

FastAPI service for ingesting one Checklist and zero or more Findings, validating them against JSON schemas, and storing canonical JSON documents in Alfresco.

Storage behavior:
- Creates/uses a specialtyName folder under the canonical base path.
- Stores checklist JSON, finding JSON, and evidence files in that specialtyName folder.

## Local Dry-Run

### Prerequisites
- Python virtual environment exists at `venv/`
- Dependencies installed from `requirements.txt`
- Test payload ZIP exists at `example data/inspection_payload.zip`
- Alfresco credentials configured using one of:
  - Docker secret files mounted at `/run/secrets/alfresco_username` and `/run/secrets/alfresco_password`
  - `ALFRESCO_USERNAME_FILE` and `ALFRESCO_PASSWORD_FILE`
  - `ALFRESCO_USERNAME` and `ALFRESCO_PASSWORD`
  - Optional: `ALFRESCO_URL`, `ALFRESCO_CANONICAL_JSON_PATH`, `ALFRESCO_TIMEOUT_SECONDS`
  - Optional retry/backoff:
    - `ALFRESCO_RETRY_TOTAL` (default `3`)
    - `ALFRESCO_RETRY_CONNECT` (default `3`)
    - `ALFRESCO_RETRY_STATUS` (default `3`)
    - `ALFRESCO_RETRY_BACKOFF_SECONDS` (default `0.5`)

Example:

```bash
export ALFRESCO_USERNAME="admin"
export ALFRESCO_PASSWORD="admin"
export ALFRESCO_RETRY_TOTAL="3"
export ALFRESCO_RETRY_BACKOFF_SECONDS="0.5"
```

## Docker

### Files added
- `Dockerfile`
- `docker-compose.yml`
- `.env.docker.example`
- `docker/secrets/alfresco_username.txt.example`
- `docker/secrets/alfresco_password.txt.example`

### Run with Docker Compose
From the repository root:

```bash
cp .env.docker.example .env
cp docker/secrets/alfresco_username.txt.example docker/secrets/alfresco_username.txt
cp docker/secrets/alfresco_password.txt.example docker/secrets/alfresco_password.txt
# edit .env and docker/secrets/*.txt with real values

docker compose up --build -d
```

Service endpoint:

```text
http://127.0.0.1:8000/inspection-import
```

### Credential resolution order
The app reads Alfresco credentials in this order for each setting (`ALFRESCO_USERNAME`, `ALFRESCO_PASSWORD`):

1. `ALFRESCO_*_FILE`
2. Docker default secret path in `/run/secrets/...`
3. `ALFRESCO_*` environment variable

If none is provided, startup fails with a clear error message.

### Run
From the repository root:

```bash
./run_dryrun.sh
```

### Run unit tests
From the repository root:

```bash
venv/bin/python -m unittest -v
```

Run only the evidence normalization tests:

```bash
venv/bin/python -m unittest tests/test_transformer_normalize_evidence.py -v
```

### Expected response
A successful run returns JSON similar to:

```json
{"status":"imported","inspectionId":"a01kkq3s90jeabsj7dp8ddnz4qf","findingsImported":2,"evidenceImported":0}
```

## Payload contract
- Exactly one checklist JSON: `checklist.json`
- Findings can be provided in one of two ways:
  - `session.json` using the current mobile session schema (responses/nonConformityDetails), or
  - explicit findings using either:
  - `findings.json` containing an array (or one object), or
  - multiple files matching `finding*.json`
- Zero or more evidence files (any non-JSON files in the ZIP payload)
- `checklist.items[].evidence` is an optional array of evidence objects
- Legacy single-object `checklist.items[].evidence` is accepted and normalized to a one-item array during import
- Checklist metadata supports `locationName` (renamed from legacy `location`), `icaoCode`, `specialtyId`, `specialtyCode`, and `specialtyName`
- `finding.requirementBreached` is auto-populated from the corresponding checklist item question text (`requirement`)

### Identifier fields
- `checklist.inspectionCode`: `XXXX-YYYY-NN` (example: `MDPP-2026-01`)
- `items[].itemCode`: `DDD-NNNN` (example: `VIG-0030`)
- `finding.findingId`: `XXXX-DDD-YYYY-NN` (example: `MDPP-VIG-2026-01`)
- `finding.itemCode`: `DDD-NNNN` and is populated during import by matching `finding.itemId` to `checklist.items[].itemId`
- `finding.locationCode`: populated during import from `checklist.checklist.icaoCode`
- `finding.findingLevel`: one of `Non-Compliance`, `Observation`, `Recommendation`

## Schemas
- Checklist schema: `schema/checklist.schema.json`
- Finding schema: `schema/finding.schema.json`

## Troubleshooting

- **500 `Missing checklist.json in ingestion payload`**
  - Ensure the uploaded ZIP contains `checklist.json` at any folder depth.
  - Ensure the checklist JSON matches `schema/checklist.schema.json`.

- **Validation error for findings**
  - Use either `findings.json` (object or array) or one/more `finding*.json` files.
  - Ensure each finding object matches `schema/finding.schema.json`.

- **Evidence files are not copied**
  - Ensure evidence files are included in the uploaded ZIP as non-JSON files.
  - Confirm API response field `evidenceImported` is greater than `0`.

- **`curl: (26) Failed to open/read local data`**
  - Use an absolute path for ZIP uploads when the current directory is uncertain.
  - Example: `-F "file=@/absolute/path/to/inspection_payload.zip"`.

- **Dry-run script cannot find venv/python**
  - Verify the executable exists at `venv/bin/python`.
  - Recreate venv and install dependencies if needed.

- **Connection refused on `127.0.0.1:8000`**
  - Confirm the API is running or re-run `./run_dryrun.sh`.
  - Check for port conflicts and stop any previous server process on `8000`.

- **502 with `Alfresco request failed (...)`**
  - Verify `ALFRESCO_URL`, credentials, and Alfresco availability.
  - Confirm the target folder path exists and user has permissions.
  - For transient errors (`429`, `5xx`), retries/backoff are applied automatically.
