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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from transformer import process_followup_payload, process_inspection

app = FastAPI(title="Inspection Import Service")

MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(400 * 1024 * 1024)))
MAX_EXTRACTED_TOTAL_SIZE = int(os.getenv("MAX_EXTRACTED_TOTAL_SIZE", str(500 * 1024 * 1024)))
MAX_EXTRACTED_FILE_SIZE = int(os.getenv("MAX_EXTRACTED_FILE_SIZE", str(50 * 1024 * 1024)))
MAX_COMPRESSION_RATIO = int(os.getenv("MAX_COMPRESSION_RATIO", "100"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.middleware("http")
async def _require_api_key(request: Request, call_next):
    api_key = os.environ.get("IMPORT_API_KEY")
    if api_key is None:
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


def _extract_and_process(zip_path, destination_dir, processor):
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        _safe_extract(zip_ref, destination_dir)

    return processor(destination_dir)


async def _process_uploaded_zip(file, processor):
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "inspection.zip")

        await _stream_upload_to_disk(file, zip_path, MAX_UPLOAD_SIZE_BYTES)

        # Extraction and the synchronous Alfresco client both block, so run them
        # in a worker thread: one slow import must not stall the event loop.
        return await run_in_threadpool(_extract_and_process, zip_path, tmpdir, processor)


@app.post("/inspection-import")
async def import_inspection(file: UploadFile = File(...)):
    try:
        result = await _process_uploaded_zip(file, process_inspection)
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
async def import_followup(file: UploadFile = File(...)):
    try:
        result = await _process_uploaded_zip(file, process_followup_payload)
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
