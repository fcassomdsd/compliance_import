import json
import re
from pathlib import Path

from alfresco_client import AlfrescoClient
from models import validate_checklist, validate_findings, validate_session


def _find_file(root_path, filename):

    matches = sorted(Path(root_path).rglob(filename))

    if not matches:
        return None

    return matches[0]


def _load_findings(root_path):

    findings_file = _find_file(root_path, "findings.json")

    if findings_file is not None:
        with findings_file.open() as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            return [data]

        raise ValueError("findings.json must contain an object or an array of objects")

    findings = []

    for finding_path in sorted(Path(root_path).rglob("finding*.json")):
        if finding_path.name == "findings.json":
            continue

        with finding_path.open() as f:
            findings.append(json.load(f))

    return findings


def _load_session(root_path):

    session_file = _find_file(root_path, "session.json")

    if session_file is None:
        return None

    with session_file.open() as f:
        return json.load(f)


def _find_evidence_files(root_path):

    evidence_files = []

    for file_path in sorted(Path(root_path).rglob("*")):
        if not file_path.is_file():
            continue

        if file_path.name == "inspection.zip":
            continue

        if file_path.suffix.lower() == ".json":
            continue

        evidence_files.append(file_path)

    return evidence_files


def _normalize_checklist_evidence(checklist):

    items = checklist.get("items")

    if not isinstance(items, list):
        return checklist

    for item in items:
        if not isinstance(item, dict):
            continue

        if "evidence" not in item:
            continue

        evidence = item["evidence"]

        if evidence is None:
            item["evidence"] = []
            continue

        if isinstance(evidence, dict):
            item["evidence"] = [evidence]

    return checklist


def _extract_question_text(item):

    for field_name in ("requirement", "questionText", "question", "text"):
        value = item.get(field_name)
        if isinstance(value, str) and value.strip():
            return value

    return None


def _extract_date(value):

    if not isinstance(value, str):
        return None

    match = re.match(r"^(\d{4}-\d{2}-\d{2})", value)
    if not match:
        return None

    return match.group(1)


def _build_findings_from_session(session_data, checklist):

    summary = session_data.get("summary", {})
    responses = session_data.get("responses", {})

    checklist_data = checklist.get("checklist", {})
    items = checklist.get("items", [])

    item_id_to_item = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("itemId")
        if item_id:
            item_id_to_item[item_id] = item

    inspection_code = checklist_data.get("inspectionCode", "")
    specialty_code = checklist_data.get("specialtyCode", "")

    inspection_prefix = inspection_code.split("-")[0] if "-" in inspection_code else "UNKN"
    inspection_year = inspection_code.split("-")[1] if len(inspection_code.split("-")) > 1 else "0000"

    date_issued = _extract_date(summary.get("lastUpdated"))

    findings = []
    counter = 0

    for response in responses.values():
        if not isinstance(response, dict):
            continue

        item_id = response.get("id")
        if not item_id:
            continue

        details = response.get("nonConformityDetails") or {}
        if not isinstance(details, dict):
            details = {}

        description = details.get("description") or response.get("comments")
        finding_level = details.get("findingLevel")

        if not description or not finding_level:
            continue

        item = item_id_to_item.get(item_id)
        if item is None:
            raise ValueError(
                f"Could not map session response id '{item_id}' to a checklist item"
            )

        counter += 1
        finding_id = f"{inspection_prefix}-{specialty_code}-{inspection_year}-{counter:02d}"

        finding_data = {
            "findingId": finding_id,
            "specialtyId": checklist_data.get("specialtyId"),
            "specialtyCode": checklist_data.get("specialtyCode"),
            "specialtyName": checklist_data.get("specialtyName"),
            "providerId": checklist_data.get("providerId"),
            "locationId": checklist_data.get("locationId") or summary.get("locationId"),
            "locationName": checklist_data.get("locationName"),
            "locationCode": checklist_data.get("icaoCode"),
            "itemId": item_id,
            "itemCode": item.get("itemCode"),
            "requirementBreached": _extract_question_text(item),
            "findingLevel": finding_level,
            "description": description,
            "riskLevel": details.get("riskLevel"),
        }

        if date_issued is not None:
            finding_data["dateIssued"] = date_issued

        findings.append(
            {
                "schemaVersion": "1.0",
                "finding": finding_data,
            }
        )

    return findings


def _enrich_findings_with_item_code(findings, checklist):

    item_id_to_item = {}
    checklist_data = checklist.get("checklist", {})
    checklist_specialty_id = checklist_data.get("specialtyId")
    checklist_specialty_code = checklist_data.get("specialtyCode")
    checklist_specialty_name = checklist_data.get("specialtyName")
    checklist_location_code = checklist_data.get("icaoCode")

    for item in checklist.get("items", []):
        if not isinstance(item, dict):
            continue

        item_id = item.get("itemId")

        if item_id:
            item_id_to_item[item_id] = item

    for finding in findings:
        finding_data = finding.get("finding", {})
        item_id = finding_data.get("itemId")

        item = item_id_to_item.get(item_id)
        if item is None:
            raise ValueError(
                f"Could not map finding itemId '{item_id}' to a checklist itemCode"
            )

        item_code = item.get("itemCode")
        if item_code is None:
            raise ValueError(
                f"Could not map finding itemId '{item_id}' to a checklist itemCode"
            )

        finding_data["itemCode"] = item_code
        requirement_text = _extract_question_text(item)
        if requirement_text is not None:
            finding_data["requirementBreached"] = requirement_text

        if "specialtyId" not in finding_data and checklist_specialty_id is not None:
            finding_data["specialtyId"] = checklist_specialty_id

        if "specialtyCode" not in finding_data and checklist_specialty_code is not None:
            finding_data["specialtyCode"] = checklist_specialty_code

        if "specialtyName" not in finding_data and checklist_specialty_name is not None:
            finding_data["specialtyName"] = checklist_specialty_name

        if "locationCode" not in finding_data and checklist_location_code is not None:
            finding_data["locationCode"] = checklist_location_code

    return findings


def process_inspection(path):

    checklist_path = _find_file(path, "checklist.json")

    if checklist_path is None:
        raise FileNotFoundError("Missing checklist.json in ingestion payload")

    with checklist_path.open() as f:
        checklist = json.load(f)

    checklist = _normalize_checklist_evidence(checklist)

    findings = _load_findings(path)
    session_data = _load_session(path)
    evidence_files = _find_evidence_files(path)

    if session_data is not None:
        validate_session(session_data)
        findings = _build_findings_from_session(session_data, checklist)

    findings = _enrich_findings_with_item_code(findings, checklist)

    validate_checklist(checklist)
    validate_findings(findings)

    alf = AlfrescoClient()
    specialty_name = checklist["checklist"]["specialtyName"]

    alf.store_checklist_document(checklist)

    for finding in findings:
        alf.store_finding_document(finding)

    for evidence_file in evidence_files:
        alf.store_evidence_file(specialty_name, evidence_file)

    return {
        "inspectionId": checklist["checklist"]["inspectionId"],
        "findingsImported": len(findings),
        "evidenceImported": len(evidence_files)
    }
