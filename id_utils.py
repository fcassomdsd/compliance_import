import re


def _parse_inspection_code(inspection_code):
    if not isinstance(inspection_code, str):
        return ("UNKN", "000")

    match = re.match(r"^([A-Z0-9]{4})-(\d{3})$", inspection_code)
    if not match:
        return ("UNKN", "000")

    return (match.group(1), match.group(2))


def build_checklist_id(inspection_code, specialty_code):
    icao, seq = _parse_inspection_code(inspection_code)
    normalized_specialty = specialty_code if isinstance(specialty_code, str) and specialty_code else "UNK"
    return f"CHK-{icao}{seq}-{normalized_specialty}"


def build_finding_id(inspection_code, specialty_code, finding_sequence):
    icao, seq = _parse_inspection_code(inspection_code)
    normalized_specialty = specialty_code if isinstance(specialty_code, str) and specialty_code else "UNK"
    normalized_finding_sequence = int(finding_sequence) if isinstance(finding_sequence, int) else 0
    return f"{icao}{seq}-{normalized_specialty}-{normalized_finding_sequence:02d}"


def build_corrective_action_id(finding_id, corrective_action_sequence):
    finding_segment = _finding_segment_for_followup_and_corrective_action(finding_id)
    normalized_sequence = int(corrective_action_sequence) if isinstance(corrective_action_sequence, int) else 0
    return f"CA-{finding_segment}-{normalized_sequence:02d}"


def build_followup_id(finding_id, followup_date):
    finding_segment = _finding_segment_for_followup_and_corrective_action(finding_id)
    return f"FU-{finding_segment}-{_format_followup_date_yy_mm_dd(followup_date)}"


def _finding_segment_for_followup_and_corrective_action(finding_id):
    if not isinstance(finding_id, str):
        return "UNKN000UNK-00"

    finding_match = re.match(r"^([A-Z0-9]{4}\d{3})-([A-Z0-9]{3,6})-(\d{2})$", finding_id)
    if not finding_match:
        return finding_id

    return f"{finding_match.group(1)}{finding_match.group(2)}-{finding_match.group(3)}"


def _format_followup_date_yy_mm_dd(followup_date):
    if not isinstance(followup_date, str):
        return "000000"

    date_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", followup_date)
    if not date_match:
        return "000000"

    return f"{date_match.group(1)[2:]}{date_match.group(2)}{date_match.group(3)}"
