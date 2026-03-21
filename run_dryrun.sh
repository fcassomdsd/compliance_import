#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$ROOT_DIR/venv/bin/python"
API_URL="http://127.0.0.1:8000/inspection-import"
PAYLOAD_ZIP="$ROOT_DIR/example data/inspection_payload.zip"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: Python venv executable not found at $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -f "$PAYLOAD_ZIP" ]]; then
  echo "Error: Payload zip not found at $PAYLOAD_ZIP" >&2
  exit 1
fi

if [[ -z "${ALFRESCO_USERNAME:-}" || -z "${ALFRESCO_PASSWORD:-}" ]]; then
  echo "Error: ALFRESCO_USERNAME and ALFRESCO_PASSWORD must be set in the environment" >&2
  exit 1
fi

cd "$ROOT_DIR"

"$PYTHON_BIN" -m uvicorn main:app --host 127.0.0.1 --port 8000 > /tmp/compliance_import_dryrun.log 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

for _ in {1..30}; do
  if curl -sS "http://127.0.0.1:8000/docs" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

echo "POST $API_URL"
RESPONSE="$(curl -sS -X POST "$API_URL" -F "file=@$PAYLOAD_ZIP")"
echo "$RESPONSE"
