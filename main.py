import os
import logging
from fastapi import FastAPI, Request, UploadFile, File
from fastapi import HTTPException
from fastapi.responses import JSONResponse
import tempfile
import zipfile
from pathlib import Path
from jsonschema.exceptions import ValidationError
from starlette.concurrency import run_in_threadpool

# Structured logging (P3.5). Replaces the previous basicConfig call, which
# only reached the root logger -- uvicorn's own handlers kept writing their
# text format to the same stream, and a stream that is 90% JSON is a stream
# a log aggregator cannot parse. This also strips Alfresco tickets out of
# logged URLs; see structured_logging.py for why that is a live leak and not
# a precaution.
from structured_logging import bind_request_id, configure_logging, new_request_id

configure_logging(level=logging.INFO)

from transformer import process_followup_payload, process_inspection
from alfresco_client import OperatorIdentityError, resolve_ticket_identity
from secret_config import assert_production_secrets, resolve_secret

# Refuse an insecure production configuration before the app object exists, so
# a misconfigured deployment fails at import time rather than serving requests.
# No-op unless APP_ENV=production, so development and the demo are unaffected.
assert_production_secrets()

app = FastAPI(title="Inspection Import Service")

# Strict by default: an import without a verified operator identity is rejected,
# so every canonical payload carries an authenticated inspector.
REQUIRE_OPERATOR_IDENTITY = os.getenv("REQUIRE_OPERATOR_IDENTITY", "true").strip().lower() not in (
    "false",
    "0",
    "no",
)

MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(400 * 1024 * 1024)))
MAX_EXTRACTED_TOTAL_SIZE = int(os.getenv("MAX_EXTRACTED_TOTAL_SIZE", str(500 * 1024 * 1024)))
MAX_EXTRACTED_FILE_SIZE = int(os.getenv("MAX_EXTRACTED_FILE_SIZE", str(50 * 1024 * 1024)))
MAX_COMPRESSION_RATIO = int(os.getenv("MAX_COMPRESSION_RATIO", "100"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.middleware("http")
async def _bind_request_id(request: Request, call_next):
    # An import is a multi-step operation that logs from several modules; with
    # no correlation id, telling one upload's lines from another's under
    # concurrent load means guessing from timestamps. Registered after the
    # API-key middleware in source order, which means it runs FIRST -- Starlette
    # applies middleware in reverse registration order -- so a rejected request
    # is still traceable.
    #
    # An inbound X-Request-Id is honoured so a trace can span the gateway and
    # this service, but it is length-capped: it ends up in every log line, and
    # an unbounded caller-supplied string in a log field is a way to make logs
    # expensive to store and unpleasant to read.
    incoming = (request.headers.get("X-Request-Id") or "").strip()[:64]
    request_id = bind_request_id(incoming or new_request_id())
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.middleware("http")
async def _require_api_key(request: Request, call_next):
    # /health must stay reachable without a key: it's what compose healthchecks and the
    # demo quickstart's readiness probe hit, and neither sends X-API-Key.
    if request.url.path == "/health":
        return await call_next(request)

    # Resolved by the platform-wide precedence (IMPORT_API_KEY_FILE ->
    # /run/secrets/import_api_key -> the environment variable), so the key can
    # be delivered as a file by a secret manager. Resolved per request rather
    # than cached at import so a rotated secret file is picked up without a
    # restart; it is a single small read from the page cache.
    api_key = resolve_secret("IMPORT_API_KEY")
    if api_key is None:
        # Development only: with no key configured the ingestion endpoints are
        # intentionally open. APP_ENV=production refuses to start in this state.
        return await call_next(request)

    request_key = request.headers.get("X-API-Key")
    if request_key != api_key:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    return await call_next(request)


def _validate_zip_bomb(zip_info):
    if zip_info.file_size > MAX_EXTRACTED_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File '{zip_info.filename}' exceeds maximum decompressed size "
                   f"({zip_info.file_size} > {MAX_EXTRACTED_FILE_SIZE})",
        )

    if zip_info.compress_size > 0 and zip_info.file_size > 0:
        ratio = zip_info.file_size / zip_info.compress_size
        if ratio > MAX_COMPRESSION_RATIO:
            raise HTTPException(
                status_code=400,
                detail=f"File '{zip_info.filename}' has suspicious compression ratio ({ratio:.1f}:1)",
            )


def _safe_extract(zip_ref, destination_dir):
    destination = Path(destination_dir).resolve()
    total_extracted = 0

    for zip_info in zip_ref.infolist():
        member_path = (destination / zip_info.filename).resolve()

        if not member_path.is_relative_to(destination):
            raise HTTPException(status_code=400, detail="Invalid ZIP payload: unsafe file path")

        _validate_zip_bomb(zip_info)

        total_extracted += zip_info.file_size
        if total_extracted > MAX_EXTRACTED_TOTAL_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"ZIP payload exceeds maximum total decompressed size "
                       f"({total_extracted} > {MAX_EXTRACTED_TOTAL_SIZE})",
            )

    zip_ref.extractall(destination)


UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024


async def _stream_upload_to_disk(file, destination, max_bytes):
    """Stream an upload to disk in chunks, enforcing a hard byte cap.

    The cap is checked as bytes arrive, so an oversized payload is rejected
    without ever being buffered whole in memory.
    """
    written = 0
    with open(destination, "wb") as out:
        while True:
            chunk = await file.read(UPLOAD_CHUNK_SIZE_BYTES)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds maximum size of {max_bytes} bytes",
                )
            out.write(chunk)

    if written == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    return written


def _extract_and_process(zip_path, destination_dir, processor, operator):
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        _safe_extract(zip_ref, destination_dir)

    return processor(destination_dir, operator)


async def _process_uploaded_zip(file, processor, operator):
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "inspection.zip")

        await _stream_upload_to_disk(file, zip_path, MAX_UPLOAD_SIZE_BYTES)

        # Extraction and the synchronous Alfresco client both block, so run them
        # in a worker thread: one slow import must not stall the event loop.
        return await run_in_threadpool(_extract_and_process, zip_path, tmpdir, processor, operator)


def _resolve_operator(request: Request):
    """Resolve the operator ticket to a verified identity.

    Blocking (it calls Alfresco), so callers run it in the threadpool. Missing
    tickets are rejected when REQUIRE_OPERATOR_IDENTITY is on; an invalid or
    expired ticket is always rejected.
    """
    ticket = (request.headers.get("X-Alfresco-Ticket") or "").strip()

    if not ticket:
        if REQUIRE_OPERATOR_IDENTITY:
            raise HTTPException(
                status_code=401,
                detail="X-Alfresco-Ticket header is required",
            )
        return None

    try:
        identity = resolve_ticket_identity(ticket)
    except OperatorIdentityError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    identity["ticket"] = ticket
    return identity


@app.post("/inspection-import")
async def import_inspection(request: Request, file: UploadFile = File(...)):
    operator = await run_in_threadpool(_resolve_operator, request)
    try:
        result = await _process_uploaded_zip(file, process_inspection, operator)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "status": "imported",
        "inspectionId": result["inspectionId"],
        "findingsImported": result["findingsImported"],
        "evidenceImported": result["evidenceImported"]
    }


@app.post("/followup-import")
async def import_followup(request: Request, file: UploadFile = File(...)):
    operator = await run_in_threadpool(_resolve_operator, request)
    try:
        result = await _process_uploaded_zip(file, process_followup_payload, operator)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "status": "imported",
        "followUpReportsImported": result["followUpReportsImported"],
        "followUpEvidenceImported": result["followUpEvidenceImported"],
        "followUpFilenames": result.get("followUpFilenames", []),
    }
