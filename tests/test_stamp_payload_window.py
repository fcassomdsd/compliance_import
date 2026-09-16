"""The demo payloads are templates: their dates must be derivable from a seeded window.

`atrocore-docker/sql/seed-demo-dataset.sql` computes the site visit's window from the day
it runs, while a committed ZIP freezes its dates the day it is written — and the inspection
*window* lives on the Alfresco folder, copied there from the payload by the canonical
import. So `atrocore-docker/scripts/demo-quickstart.sh` stamps each payload with the window
it read back from the seeded visit before importing it, using
`scripts/stamp-payload-window.py`.

These tests pin that derivation to the tracked payloads: the window lands exactly on the
target, the findings keep their distance from the window's last day, the follow-up stays
after it, evidence is copied through untouched, the template is never modified, and the
result still validates against this service's schemas.
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from models import (
    validate_checklist,
    validate_findings,
    validate_followup_reports,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_DIR = REPO_ROOT / "example data"
STAMP_SCRIPT = REPO_ROOT / "scripts" / "stamp-payload-window.py"

INSPECTION_PAYLOADS = ("demo_inspection_payload.zip", "demo_met_inspection_payload.zip")
FOLLOWUP_PAYLOAD = "demo_followup_payload.zip"

FOLLOW_UP_LAG_DAYS = 13


def load_stamper():
    spec = importlib.util.spec_from_file_location("stamp_payload_window", STAMP_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stamper = load_stamper()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_stamper(argv):
    """Call the script as the quickstart does, without its progress output in the log."""
    with contextlib.redirect_stdout(io.StringIO()):
        return stamper.main(argv)


def read_json(archive, name):
    return json.loads(archive.read(name))


class StampPayloadWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stamp-payload-window-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def stamped(self, name, start, end):
        destination = self.tmp / name
        run_stamper(
            [
                str(EXAMPLE_DIR / name),
                str(destination),
                "--start",
                start,
                "--end",
                end,
            ]
        )
        return destination

    def test_every_demo_payload_carries_something_to_stamp(self):
        for name in INSPECTION_PAYLOADS + (FOLLOWUP_PAYLOAD,):
            with self.subTest(payload=name):
                # `stamp` raises SystemExit when a ZIP holds none of the date-bearing
                # entries, which is how a payload built wrongly would surface here.
                self.stamped(name, "2027-03-04", "2027-03-05")

    def test_the_source_template_is_never_modified(self):
        for name in INSPECTION_PAYLOADS + (FOLLOWUP_PAYLOAD,):
            with self.subTest(payload=name):
                before = digest(EXAMPLE_DIR / name)
                self.stamped(name, "2027-03-04", "2027-03-05")
                self.assertEqual(before, digest(EXAMPLE_DIR / name))

    def test_inspection_windows_and_finding_dates_land_on_the_target(self):
        for name in INSPECTION_PAYLOADS:
            with self.subTest(payload=name):
                stamped = self.stamped(name, "2027-03-04", "2027-03-05")
                with zipfile.ZipFile(stamped) as archive:
                    checklist = read_json(archive, "checklist.json")
                    validate_checklist(checklist)
                    self.assertEqual("2027-03-04", checklist["checklist"]["startDate"])
                    self.assertEqual("2027-03-05", checklist["checklist"]["endDate"])

                    if "findings.json" not in archive.namelist():
                        continue
                    findings = read_json(archive, "findings.json")
                    validate_findings(findings)
                    for entry in findings:
                        # The template issues its findings on the inspection's last day,
                        # and stamping keeps that relationship rather than the fixed date.
                        self.assertEqual("2027-03-05", entry["finding"]["dateIssued"])

    def test_a_longer_window_still_ends_on_its_last_day(self):
        stamped = self.stamped(INSPECTION_PAYLOADS[0], "2027-03-04", "2027-03-06")
        with zipfile.ZipFile(stamped) as archive:
            checklist = read_json(archive, "checklist.json")
            self.assertEqual("2027-03-04", checklist["checklist"]["startDate"])
            self.assertEqual("2027-03-06", checklist["checklist"]["endDate"])
            for entry in read_json(archive, "findings.json"):
                self.assertEqual("2027-03-06", entry["finding"]["dateIssued"])

    def test_the_follow_up_is_dated_after_the_window_ends(self):
        stamped = self.stamped(FOLLOWUP_PAYLOAD, "2027-03-04", "2027-03-05")
        with zipfile.ZipFile(stamped) as archive:
            reports = read_json(archive, "followup-reports.json")
            validate_followup_reports(reports)
            expected = "2027-03-18"  # the window's last day + 13
            for entry in reports:
                self.assertEqual(expected, entry["followUpReport"]["followUpDate"])

    def test_stamping_the_same_window_twice_changes_nothing(self):
        first = self.stamped(INSPECTION_PAYLOADS[0], "2027-03-04", "2027-03-05")
        second = self.tmp / "again.zip"
        run_stamper(
            [
                str(first),
                str(second),
                "--start",
                "2027-03-04",
                "--end",
                "2027-03-05",
            ]
        )
        with zipfile.ZipFile(first) as a, zipfile.ZipFile(second) as b:
            self.assertEqual(read_json(a, "checklist.json"), read_json(b, "checklist.json"))
            self.assertEqual(read_json(a, "findings.json"), read_json(b, "findings.json"))

    def test_evidence_and_entry_names_survive_the_rewrite(self):
        for name in INSPECTION_PAYLOADS + (FOLLOWUP_PAYLOAD,):
            with self.subTest(payload=name):
                stamped = self.stamped(name, "2027-03-04", "2027-03-05")
                with zipfile.ZipFile(EXAMPLE_DIR / name) as source, zipfile.ZipFile(stamped) as result:
                    self.assertEqual(source.namelist(), result.namelist())
                    for entry in source.namelist():
                        if entry.endswith(".json"):
                            continue
                        self.assertEqual(
                            source.read(entry),
                            result.read(entry),
                            f"{name}: {entry} was rewritten, but only the JSON entries carry dates",
                        )

    def test_a_zip_with_no_payload_entry_is_rejected(self):
        nameless = self.tmp / "not-a-payload.zip"
        with zipfile.ZipFile(nameless, "w") as archive:
            archive.writestr("Evidence/ATS-operations-manual-extract.txt", "DEMO EVIDENCE\n")
        with self.assertRaises(SystemExit):
            run_stamper(
                [
                    str(nameless),
                    str(self.tmp / "out.zip"),
                    "--start",
                    "2027-03-04",
                    "--end",
                    "2027-03-05",
                ]
            )

    def test_a_backwards_window_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.stamped(INSPECTION_PAYLOADS[0], "2027-03-05", "2027-03-04")


if __name__ == "__main__":
    unittest.main()
