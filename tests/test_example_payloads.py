"""The tracked demo payloads must validate against this service's own schemas.

They are the contract documentation for `/inspection-import` and `/followup-import`, and they are
what `atrocore-docker/scripts/demo-quickstart.sh` posts — so a payload that stops validating turns
the documented demo path into a `422` that nothing else catches.

There are two inspection payloads because the demo dataset seeds two inspections (ATS and MET).
The inspection *window* only exists once canonical documents have been imported for an inspection
— it lives on the Alfresco inspection folder — so a seeded inspection with no payload has items
that cannot be dated and drop out of the year-filtered reports. These tests keep both windows and
every evidence reference honest.
"""

import json
import unittest
import zipfile
from pathlib import Path

from models import (
    validate_checklist,
    validate_findings,
    validate_followup_reports,
    validate_followup_source_findings,
)

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "example data"

INSPECTION_PAYLOADS = ("demo_inspection_payload.zip", "demo_met_inspection_payload.zip")
FOLLOWUP_PAYLOAD = "demo_followup_payload.zip"


class DemoPayloadTests(unittest.TestCase):
    def test_the_demo_payloads_are_tracked(self):
        for name in INSPECTION_PAYLOADS + (FOLLOWUP_PAYLOAD,):
            self.assertTrue((EXAMPLE_DIR / name).is_file(), f"{name} is missing")

    def test_inspection_payloads_validate_and_date_their_inspection(self):
        for name in INSPECTION_PAYLOADS:
            with self.subTest(payload=name):
                with zipfile.ZipFile(EXAMPLE_DIR / name) as archive:
                    names = set(archive.namelist())
                    self.assertIn("checklist.json", names)

                    checklist = json.loads(archive.read("checklist.json"))
                    validate_checklist(checklist)

                    context = checklist["checklist"]
                    for field in ("inspectionCode", "specialtyName", "startDate", "endDate"):
                        self.assertTrue(context.get(field), f"{name}: checklist.{field} is empty")

                    if "findings.json" in names:
                        validate_findings(json.loads(archive.read("findings.json")))

                    for item in checklist["items"]:
                        for evidence in item.get("evidenceItems", []):
                            self.assertIn(
                                f"Evidence/{evidence['source']}",
                                names,
                                f"{name}: {item['itemCode']} references an evidence file that is not in the ZIP",
                            )

    def test_followup_payload_validates(self):
        with zipfile.ZipFile(EXAMPLE_DIR / FOLLOWUP_PAYLOAD) as archive:
            names = set(archive.namelist())
            validate_followup_reports(json.loads(archive.read("followup-reports.json")))
            validate_followup_source_findings(json.loads(archive.read("prior-findings.json")))
            self.assertTrue(
                any(entry.startswith("FollowUpEvidence/") for entry in names),
                "the follow-up payload needs a FollowUpEvidence/ folder (not Evidence/)",
            )


if __name__ == "__main__":
    unittest.main()
