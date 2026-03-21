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


def process_inspection(path):

    checklist_path = _find_file(path, "checklist.json")

    if checklist_path is None:
        raise FileNotFoundError("Missing checklist.json in ingestion payload")

    with checklist_path.open() as f:
        checklist = json.load(f)

    findings = _load_findings(path)
    evidence_files = _find_evidence_files(path)

    validate_checklist(checklist)
    validate_findings(findings)

    alf = AlfrescoClient()
    domain = checklist["checklist"]["domain"]

    alf.store_checklist_document(checklist)

    for finding in findings:
        alf.store_finding_document(finding)

    for evidence_file in evidence_files:
        alf.store_evidence_file(domain, evidence_file)

    return {
        "inspectionId": checklist["checklist"]["inspectionId"],
        "findingsImported": len(findings),
        "evidenceImported": len(evidence_files)
    }
