from domain_rules import FINDING_ID_PATTERN, INSPECTION_CODE_PATTERN

# INSPECTION_CODE_PATTERN/FINDING_ID_PATTERN are the canonical Nomenclatura
# patterns, loaded from the shared domain-rule spec. Activity codes are
# AV-XXXX-T-#### platform-wide; the AV- prefix is optional on input because
# this service has always accepted the bare XXXX-T-#### form.

DEFAULT_SPECIALTY_CODE = "UNK"


def _parse_inspection_code(inspection_code):
    if not isinstance(inspection_code, str):
        raise ValueError(
            f"inspection_code must be a string, got {type(inspection_code).__name__}"
        )

    match = INSPECTION_CODE_PATTERN.match(inspection_code)
    if not match:
        raise ValueError(
            f"inspection_code '{inspection_code}' does not match expected format AV-XXXX-T-#### "
            f"(the AV- prefix is optional)"
        )

    return (match.group(1), match.group(2), match.group(3))


def _compact_activity_code(inspection_code):
    icao, activity_type, sequence = _parse_inspection_code(inspection_code)
    return f"{icao}{activity_type}{sequence}"


def _normalize_specialty_code(specialty_code):
    if isinstance(specialty_code, str) and specialty_code:
        return specialty_code

    return DEFAULT_SPECIALTY_CODE


def _normalize_sequence(sequence):
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        return 1

    return max(1, sequence)


def build_checklist_id(inspection_code, specialty_code):
    compact_activity = _compact_activity_code(inspection_code)
    return f"LV-{compact_activity}-{_normalize_specialty_code(specialty_code)}"


def build_finding_id(inspection_code, specialty_code, finding_sequence):
    compact_activity = _compact_activity_code(inspection_code)
    normalized_specialty = _normalize_specialty_code(specialty_code)
    normalized_finding_sequence = _normalize_sequence(finding_sequence)
    return f"H-{compact_activity}-{normalized_specialty}-{normalized_finding_sequence:03d}"


def build_corrective_action_id(finding_id, corrective_action_sequence):
    finding_segment = _finding_segment_for_followup_and_corrective_action(finding_id)
    normalized_sequence = _normalize_sequence(corrective_action_sequence)
    return f"P-{finding_segment}-{normalized_sequence:02d}"


def build_followup_id_seq(finding_id, seq):
    finding_segment = _finding_segment_for_followup_and_corrective_action(finding_id)
    seq_int = int(seq) if isinstance(seq, (int, str)) and str(seq).lstrip("-").isdigit() else 1
    return f"S-{finding_segment}-{max(1, seq_int):02d}"


def _finding_segment_for_followup_and_corrective_action(finding_id):
    if not isinstance(finding_id, str):
        raise ValueError(
            f"finding_id must be a string, got {type(finding_id).__name__}"
        )

    finding_match = FINDING_ID_PATTERN.match(finding_id)
    if not finding_match:
        raise ValueError(
            f"finding_id '{finding_id}' does not match expected format H-XXXXT####-EEE-###"
        )

    return f"{finding_match.group(1)}-{finding_match.group(2)}{finding_match.group(3)}"
