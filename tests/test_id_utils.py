import unittest

from id_utils import (
    build_checklist_id,
    build_corrective_action_id,
    build_finding_id,
    build_followup_id,
)


class IdUtilsTests(unittest.TestCase):

    def test_build_checklist_id_uses_required_nomenclature(self):
        self.assertEqual("CHK-MDPP001-AYVIS", build_checklist_id("MDPP-001", "AYVIS"))

    def test_build_finding_id_uses_required_nomenclature(self):
        self.assertEqual("MDPP001-AYVIS-01", build_finding_id("MDPP-001", "AYVIS", 1))

    def test_build_corrective_action_id_uses_required_nomenclature(self):
        self.assertEqual(
            "CA-MDPP001AYVIS-01-01",
            build_corrective_action_id("MDPP001-AYVIS-01", 1),
        )

    def test_build_followup_id_uses_required_nomenclature(self):
        self.assertEqual(
            "FU-MDPP001AYVIS-01-260401",
            build_followup_id("MDPP001-AYVIS-01", "2026-04-01T10:00:00.000Z"),
        )

    def test_build_followup_id_uses_zero_date_when_invalid(self):
        self.assertEqual(
            "FU-MDPP001AYVIS-01-000000",
            build_followup_id("MDPP001-AYVIS-01", "not-a-date"),
        )


if __name__ == "__main__":
    unittest.main()
