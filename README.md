# Compliance Import Service

FastAPI service for ingesting one Checklist and zero or more Findings, validating them against JSON schemas, and storing canonical JSON documents in Alfresco.

Storage behavior:
- Creates/uses a domain folder under the canonical base path.
- Stores checklist JSON, finding JSON, and evidence files in that domain folder.

## Local Dry-Run

### Prerequisites
- Python virtual environment exists at `venv/`
- Dependencies installed from `requirements.txt`
- Test payload ZIP exists at `example data/inspection_payload.zip`
- Environment variables configured:
  - `ALFRESCO_USERNAME`
  - `ALFRESCO_PASSWORD`
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

### Run
From the repository root:

```bash
./run_dryrun.sh
```

### Expected response
A successful run returns JSON similar to:

```json
{"status":"imported","inspectionId":"a01kkq3s90jeabsj7dp8ddnz4qf","findingsImported":2,"evidenceImported":0}
```

## Payload contract
- Exactly one checklist JSON: `checklist.json`
- Zero or more findings using either:
  - `findings.json` containing an array (or one object), or
  - multiple files matching `finding*.json`
- Zero or more evidence files (any non-JSON files in the ZIP payload)

### Identifier fields
- `checklist.inspectionCode`: `XXXX-YYYY-NN` (example: `MDPP-2026-01`)
- `items[].itemCode`: `DDD-NNNN` (example: `VIG-0030`)
- `finding.findingId`: `XXXX-DDD-YYYY-NN` (example: `MDPP-VIG-2026-01`)

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
