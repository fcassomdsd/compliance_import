from fastapi import FastAPI, UploadFile, File
import tempfile
import zipfile
import json
from transformer import process_inspection

app = FastAPI(title="Inspection Import Service")

@app.post("/inspection-import")
async def import_inspection(file: UploadFile = File(...)):

    with tempfile.TemporaryDirectory() as tmpdir:

        zip_path = f"{tmpdir}/inspection.zip"

        with open(zip_path, "wb") as f:
            f.write(await file.read())

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(tmpdir)

        result = process_inspection(tmpdir)

    return {"status": "imported", "inspectionId": result}
