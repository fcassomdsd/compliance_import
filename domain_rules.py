"""Shared, cross-repo domain-rule loader.

The Nomenclatura document formats, the severity-to-deadline baseline and the
follow-up/closure vocabulary are published exactly once, in
``domain-rules/nomenclatura.spec.json`` (canonical copy owned by
compliance_cmis) and vendored byte-for-byte into this repository. Do not
reintroduce literal formats or day counts here: add them to the spec and its
conformance vectors.
"""

import json
import re
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parent / "domain-rules" / "nomenclatura.spec.json"

with SPEC_PATH.open(encoding="utf-8") as _spec_file:
    SPEC = json.load(_spec_file)


def id_pattern(name, key="pattern"):
    """Compile one of the spec's document-id patterns."""

    return re.compile(SPEC["ids"][name][key])


# Canonical AV-XXXX-T-####, with the AV- prefix optional on input (the importer
# has always accepted the bare XXXX-T-#### form).
INSPECTION_CODE_PATTERN = id_pattern("activity", "inputPattern")
FINDING_ID_PATTERN = id_pattern("finding")

SEVERITY_DAYS = {
    level["id"]: level["daysToSolution"] for level in SPEC["severity"]["levels"]
}

FOLLOW_UP_TYPES = tuple(SPEC["followUpTypes"]["canonical"])
FOLLOW_UP_TYPE_ALIASES = dict(SPEC["followUpTypes"]["aliases"])
DEFAULT_FOLLOW_UP_TYPE = SPEC["followUpTypes"]["default"]

CLOSURE_FOLLOW_UP_TYPE = SPEC["closureGate"]["requiredFollowUpType"]
CLOSURE_REQUIRES_EFFECTIVENESS = SPEC["closureGate"]["requiredEffectivenessConfirmed"]
CLOSURE_REJECTS_EFFECTIVENESS_WITH_OTHER_TYPES = SPEC["closureGate"][
    "rejectsEffectivenessConfirmedWithOtherTypes"
]


def normalize_follow_up_type(value):
    """Map a follow-up type (including the legacy alias) to the canonical one."""

    if isinstance(value, str):
        if value in FOLLOW_UP_TYPE_ALIASES:
            return FOLLOW_UP_TYPE_ALIASES[value]
        if value in FOLLOW_UP_TYPES:
            return value

    return DEFAULT_FOLLOW_UP_TYPE


def closure_policy(follow_up_type, effectiveness_confirmed):
    """Python mirror of compliance_cmis's validateClosurePolicy.

    Returns ``(should_close, error)``: a finding closes only on a
    "Closure Verification" follow-up with effectivenessConfirmed=true, and
    confirming effectiveness on any other type is an error.
    """

    should_close = (
        follow_up_type == CLOSURE_FOLLOW_UP_TYPE
        and effectiveness_confirmed is CLOSURE_REQUIRES_EFFECTIVENESS
    )

    error = None
    if (
        CLOSURE_REJECTS_EFFECTIVENESS_WITH_OTHER_TYPES
        and effectiveness_confirmed is True
        and follow_up_type != CLOSURE_FOLLOW_UP_TYPE
    ):
        error = (
            "Only Closure Verification type follow-ups can set "
            "effectivenessConfirmed to true for closure"
        )

    return should_close, error
