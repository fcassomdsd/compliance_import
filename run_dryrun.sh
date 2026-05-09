#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$ROOT_DIR/venv/bin/python"
#API_URL="http://127.0.0.1:8000/inspection-import"
API_URL="http://127.0.0.1:8000/followup-import"
#PAYLOAD_ZIP="$ROOT_DIR/example data/inspection_payload.zip"
PAYLOAD_ZIP="$ROOT_DIR/example data/followup_payload_VIG_2026-05-08T12-12-18.zip"

read_required_setting() {
  local env_name="$1"
  local default_secret_path="$2"
  local file_env_name="${env_name}_FILE"

  local file_path="${!file_env_name:-}"
  if [[ -n "$file_path" && -f "$file_path" ]]; then
    tr -d '\r' < "$file_path" | sed -e 's/[[:space:]]*$//'
    return 0
  fi

  if [[ -f "$default_secret_path" ]]; then
    tr -d '\r' < "$default_secret_path" | sed -e 's/[[:space:]]*$//'
    return 0
  fi

  if [[ -n "${!env_name:-}" ]]; then
    printf "%s" "${!env_name}"
    return 0
  fi

  return 1
}

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: Python venv executable not found at $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -f "$PAYLOAD_ZIP" ]]; then
  echo "Error: Payload zip not found at $PAYLOAD_ZIP" >&2
  exit 1
fi

if ! ALFRESCO_USERNAME_RESOLVED="$(read_required_setting "ALFRESCO_USERNAME" "/run/secrets/alfresco_username")"; then
  echo "Error: Missing ALFRESCO_USERNAME. Set ALFRESCO_USERNAME, ALFRESCO_USERNAME_FILE, or /run/secrets/alfresco_username" >&2
  exit 1
fi

if ! ALFRESCO_PASSWORD_RESOLVED="$(read_required_setting "ALFRESCO_PASSWORD" "/run/secrets/alfresco_password")"; then
  echo "Error: Missing ALFRESCO_PASSWORD. Set ALFRESCO_PASSWORD, ALFRESCO_PASSWORD_FILE, or /run/secrets/alfresco_password" >&2
  exit 1
fi

export ALFRESCO_USERNAME="$ALFRESCO_USERNAME_RESOLVED"
export ALFRESCO_PASSWORD="$ALFRESCO_PASSWORD_RESOLVED"

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
