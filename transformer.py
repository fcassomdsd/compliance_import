import json
from pathlib import Path

from alfresco_client import AlfrescoClient
from models import validate_checklist, validate_findings


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


def _enrich_findings_with_item_code(findings, checklist):

    item_id_to_code = {}
    checklist_data = checklist.get("checklist", {})
    checklist_specialty_id = checklist_data.get("specialtyId")
    checklist_specialty_code = checklist_data.get("specialtyCode")
    checklist_specialty_name = checklist_data.get("specialtyName")

    for item in checklist.get("items", []):
        if not isinstance(item, dict):
            continue

        item_id = item.get("itemId")
        item_code = item.get("itemCode")

        if item_id and item_code:
            item_id_to_code[item_id] = item_code

    for finding in findings:
        finding_data = finding.get("finding", {})
        item_id = finding_data.get("itemId")

        item_code = item_id_to_code.get(item_id)
        if item_code is None:
            raise ValueError(
                f"Could not map finding itemId '{item_id}' to a checklist itemCode"
            )

        finding_data["itemCode"] = item_code

        if "specialtyId" not in finding_data and checklist_specialty_id is not None:
            finding_data["specialtyId"] = checklist_specialty_id

        if "specialtyCode" not in finding_data and checklist_specialty_code is not None:
            finding_data["specialtyCode"] = checklist_specialty_code

        if "specialtyName" not in finding_data and checklist_specialty_name is not None:
            finding_data["specialtyName"] = checklist_specialty_name

    return findings


def process_inspection(path):

    checklist_path = _find_file(path, "checklist.json")

    if checklist_path is None:
        raise FileNotFoundError("Missing checklist.json in ingestion payload")

    with checklist_path.open() as f:
        checklist = json.load(f)

    checklist = _normalize_checklist_evidence(checklist)

    findings = _load_findings(path)
    evidence_files = _find_evidence_files(path)

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
