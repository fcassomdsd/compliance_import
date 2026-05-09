import json
from pathlib import Path

from alfresco_client import AlfrescoClient
from models import (
    validate_checklist,
    validate_findings,
    validate_followup_reports,
    validate_followup_source_findings,
)


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


def _load_followup_reports(root_path):

    reports_file = _find_file(root_path, "followup-reports.json")

    if reports_file is None:
        raise FileNotFoundError("Missing followup-reports.json in follow-up payload")

    with reports_file.open() as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("followup-reports.json must contain an array of report objects")

    return data


def _load_followup_source_findings(root_path):

    findings_file = _find_file(root_path, "prior-findings.json")

    if findings_file is None:
        raise FileNotFoundError("Missing prior-findings.json in follow-up payload")

    with findings_file.open() as f:
        data = json.load(f)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        return [data]

    raise ValueError("findings.json must contain an object or an array of objects")


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


def _find_followup_evidence_files(root_path):

    evidence_root = _find_file(root_path, "FollowUpEvidence")

    if evidence_root is None:
        candidate_dir = None
        for path in sorted(Path(root_path).rglob("*")):
            if path.is_dir() and path.name == "FollowUpEvidence":
                candidate_dir = path
                break
        evidence_root = candidate_dir

    if evidence_root is None or not evidence_root.is_dir():
        raise FileNotFoundError("Missing FollowUpEvidence folder in follow-up payload")

    evidence_files = []
    for file_path in sorted(evidence_root.rglob("*")):
        if file_path.is_file():
            evidence_files.append(file_path)

    return evidence_files


def _normalize_checklist_evidence(checklist):

    items = checklist.get("items")

    if not isinstance(items, list):
        return checklist

    for item in items:
        if not isinstance(item, dict):
            continue

        if "evidenceItems" not in item:
            continue

        evidence = item["evidenceItems"]

        if evidence is None:
            item["evidenceItems"] = []
            continue

        if isinstance(evidence, dict):
            item["evidenceItems"] = [evidence]

    return checklist


def _extract_question_text(item):

    for field_name in (
        "requirementText",
        "requirement",
        "questionText",
        "question",
        "text",
    ):
        value = item.get(field_name)
        if isinstance(value, str) and value.strip():
            return value

    return None


def _enrich_findings_with_item_code(findings, checklist):

    item_code_to_item = {}
    checklist_data = checklist.get("checklist", {})
    checklist_specialty_id = checklist_data.get("specialtyId")
    checklist_specialty_code = checklist_data.get("specialtyCode")
    checklist_specialty_name = checklist_data.get("specialtyName")
    checklist_provider_id = checklist_data.get("providerId")
    checklist_location_id = checklist_data.get("locationId")
    checklist_location_name = checklist_data.get("locationName")
    checklist_location_code = checklist_data.get("locationCode")

    for item in checklist.get("items", []):
        if not isinstance(item, dict):
            continue

        item_code = item.get("itemCode")

        if item_code:
            item_code_to_item[item_code] = item

    for finding in findings:
        finding_data = finding.get("finding", {})
        item_code = finding_data.get("checklistItemCode")

        item = item_code_to_item.get(item_code)
        if item is None:
            raise ValueError(
                "Could not map finding to checklist item using "
                f"checklistItemCode '{item_code}'"
            )

        mapped_item_code = item.get("itemCode")
        if mapped_item_code is None:
            raise ValueError(
                f"Could not map finding checklistItemCode '{item_code}' to a checklist itemCode"
            )

        finding_data["checklistItemCode"] = mapped_item_code
        requirement_text = _extract_question_text(item)
        if requirement_text is not None:
            finding_data["requirementBreached"] = requirement_text

        if "specialtyId" not in finding_data and checklist_specialty_id is not None:
            finding_data["specialtyId"] = checklist_specialty_id

        if "specialtyCode" not in finding_data and checklist_specialty_code is not None:
            finding_data["specialtyCode"] = checklist_specialty_code

        if "specialtyName" not in finding_data and checklist_specialty_name is not None:
            finding_data["specialtyName"] = checklist_specialty_name

        if "providerId" not in finding_data and checklist_provider_id is not None:
            finding_data["providerId"] = checklist_provider_id

        if "locationId" not in finding_data and checklist_location_id is not None:
            finding_data["locationId"] = checklist_location_id

        if "locationName" not in finding_data and checklist_location_name is not None:
            finding_data["locationName"] = checklist_location_name

        if "locationCode" not in finding_data and checklist_location_code is not None:
            finding_data["locationCode"] = checklist_location_code

    return findings


def _normalize_findings_for_followup(source_findings):

    normalized_findings = []

    for finding in source_findings:
        if not isinstance(finding, dict):
            continue

        if "finding" in finding and isinstance(finding["finding"], dict):
            normalized_findings.append(finding["finding"])
            continue

        normalized_findings.append(finding)

    return normalized_findings


def _build_followup_reports(source_findings, followup_reports):

    normalized_findings = _normalize_findings_for_followup(source_findings)
    finding_id_to_finding = {}

    for finding in normalized_findings:
        finding_id = finding.get("findingId")
        if finding_id:
            finding_id_to_finding[finding_id] = finding

    result = []

    for report in followup_reports:
        report_data = report.get("followUpReport", {})
        finding_id = report_data.get("findingId")

        source_finding = finding_id_to_finding.get(finding_id)
        if source_finding is None:
            raise ValueError(
                f"Could not map follow-up report findingId '{finding_id}' to findings.json"
            )

        corrective_action = source_finding.get("correctiveAction") or {}
        source_cap_id = corrective_action.get("capId")
        report_cap_id = report_data.get("capId")

        if source_cap_id and not report_cap_id:
            report_data["capId"] = source_cap_id
            report_cap_id = source_cap_id

        if source_cap_id and report_cap_id != source_cap_id:
            raise ValueError(
                f"Could not map follow-up report for findingId '{finding_id}': capId '{report_cap_id}' does not match source capId '{source_cap_id}'"
            )

        result.append(report)

    return result


def _validate_followup_evidence_sources(reports, evidence_files):

    evidence_name_to_file = {}

    for evidence_file in evidence_files:
        evidence_name_to_file[evidence_file.name] = evidence_file

    for report in reports:
        report_data = report.get("followUpReport", {})
        finding_id = report_data.get("findingId")

        evidence_items = report_data.get("evidenceItems") or []
        for evidence in evidence_items:
            source_name = evidence.get("source")
            if source_name not in evidence_name_to_file:
                raise FileNotFoundError(
                    f"Missing FollowUpEvidence file '{source_name}' referenced by follow-up report findingId '{finding_id}'"
                )

    return evidence_name_to_file


def process_inspection(path):

    checklist_path = _find_file(path, "checklist.json")

    if checklist_path is None:
        raise FileNotFoundError("Missing checklist.json in ingestion payload")

    with checklist_path.open() as f:
        checklist = json.load(f)

    checklist = _normalize_checklist_evidence(checklist)

    findings = _load_findings(path)
    evidence_files = _find_evidence_files(path)

    validate_checklist(checklist)
    validate_findings(findings)

    findings = _enrich_findings_with_item_code(findings, checklist)

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


def process_followup_payload(path):

    source_findings = _load_followup_source_findings(path)
    followup_reports = _load_followup_reports(path)
    evidence_files = _find_followup_evidence_files(path)

    validate_followup_source_findings(source_findings)
    validate_followup_reports(followup_reports)

    reports = _build_followup_reports(source_findings, followup_reports)
    _validate_followup_evidence_sources(reports, evidence_files)

    normalized_findings = _normalize_findings_for_followup(source_findings)
    finding_id_to_specialty_name = {}
    for finding in normalized_findings:
        finding_id = finding.get("findingId")
        specialty_name = finding.get("specialtyName")
        if finding_id and specialty_name:
            finding_id_to_specialty_name[finding_id] = specialty_name

    alf = AlfrescoClient()
    followup_filenames = []

    for report in reports:
        report_data = report.get("followUpReport", {})
        finding_id = report_data.get("findingId")
        specialty_name = finding_id_to_specialty_name.get(finding_id)
        if specialty_name is None:
            raise ValueError(
                f"Could not map follow-up report findingId '{finding_id}' to a specialtyName"
            )

        store_result = alf.store_followup_report_document(report, specialty_name)
        if isinstance(store_result, dict):
            stored_filename = store_result.get("storedFilename")
            if stored_filename:
                followup_filenames.append(stored_filename)

    uploaded_evidence = 0
    evidence_name_to_file = {file_path.name: file_path for file_path in evidence_files}

    for report in reports:
        report_data = report.get("followUpReport", {})
        finding_id = report_data.get("findingId")
        specialty_name = finding_id_to_specialty_name.get(finding_id)

        evidence_items = report_data.get("evidenceItems") or []
        for evidence in evidence_items:
            evidence_source = evidence.get("source")
            evidence_file = evidence_name_to_file.get(evidence_source)
            if evidence_file is None:
                continue

            alf.store_followup_evidence_file(specialty_name, evidence_file)
            uploaded_evidence += 1

    return {
        "followUpReportsImported": len(reports),
        "followUpEvidenceImported": uploaded_evidence,
        "followUpFilenames": followup_filenames,
    }
