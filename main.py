from fastapi import FastAPI, UploadFile, File
from fastapi import HTTPException
import tempfile
import zipfile
from pathlib import Path
from jsonschema.exceptions import ValidationError

from transformer import process_inspection

app = FastAPI(title="Inspection Import Service")


def _safe_extract(zip_ref, destination_dir):

    destination = Path(destination_dir).resolve()

    for zip_info in zip_ref.infolist():
        member_path = (destination / zip_info.filename).resolve()

        if not member_path.is_relative_to(destination):
            raise HTTPException(status_code=400, detail="Invalid ZIP payload: unsafe file path")

    zip_ref.extractall(destination)

@app.post("/inspection-import")
async def import_inspection(file: UploadFile = File(...)):

    try:
        with tempfile.TemporaryDirectory() as tmpdir:

            zip_path = f"{tmpdir}/inspection.zip"

            with open(zip_path, "wb") as f:
                f.write(await file.read())

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                _safe_extract(zip_ref, tmpdir)

            result = process_inspection(tmpdir)
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
