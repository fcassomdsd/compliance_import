import unittest

from id_utils import (
    build_checklist_id,
    build_corrective_action_id,
    build_finding_id,
    build_followup_id_seq,
)


class IdUtilsTests(unittest.TestCase):

    def test_build_checklist_id_uses_required_nomenclature(self):
        self.assertEqual("LV-MDSDA0002-COM", build_checklist_id("MDSD-A-0002", "COM"))

    def test_build_finding_id_uses_required_nomenclature(self):
        self.assertEqual("H-MDSDA0002-COM-001", build_finding_id("MDSD-A-0002", "COM", 1))

    def test_build_finding_id_pads_sequence_to_three_digits(self):
        self.assertEqual("H-MDSDA0002-COM-042", build_finding_id("MDSD-A-0002", "COM", 42))

    def test_build_corrective_action_id_uses_required_nomenclature(self):
        self.assertEqual(
            "P-MDSDA0002-COM001-01",
            build_corrective_action_id("H-MDSDA0002-COM-001", 1),
        )

    def test_build_followup_id_seq_uses_required_nomenclature(self):
        self.assertEqual(
            "S-MDSDA0002-COM001-01",
            build_followup_id_seq("H-MDSDA0002-COM-001", 1),
        )

    def test_build_followup_id_seq_pads_sequence_to_two_digits(self):
        self.assertEqual(
            "S-MDSDA0002-COM001-03",
            build_followup_id_seq("H-MDSDA0002-COM-001", 3),
        )

    def test_sequences_are_one_based(self):
        self.assertEqual(
            "P-MDSDA0002-COM001-01",
            build_corrective_action_id("H-MDSDA0002-COM-001", 0),
        )
        self.assertEqual(
            "S-MDSDA0002-COM001-01",
            build_followup_id_seq("H-MDSDA0002-COM-001", 0),
        )
        self.assertEqual("H-MDSDA0002-COM-001", build_finding_id("MDSD-A-0002", "COM", 0))

    def test_build_checklist_id_rejects_legacy_inspection_code(self):
        with self.assertRaises(ValueError):
            build_checklist_id("MDPP-001", "SUR")

    def test_corrective_action_id_rejects_legacy_finding_id(self):
        with self.assertRaises(ValueError):
            build_corrective_action_id("MDPP001-VIG-01", 1)


if __name__ == "__main__":
    unittest.main()
