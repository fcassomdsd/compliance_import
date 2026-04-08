import unittest

from transformer import _enrich_findings_with_item_code, _normalize_checklist_evidence


MISSING = object()


class NormalizeChecklistEvidenceTests(unittest.TestCase):

    def _base_checklist(self, evidence_value):
        item = {
            "itemId": "item-1",
            "itemCode": "VIG-0001",
            "compliance": "Compliant",
        }

        if evidence_value is not MISSING:
            item["evidence"] = evidence_value

        return {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "id-1",
                "inspectionCode": "ABCD-2026-01",
                "domain": "VIG",
                "providerId": "provider-1",
            },
            "items": [item],
        }

    def test_wraps_object_evidence_into_array(self):
        checklist = self._base_checklist(
            {
                "evidenceId": "EV-0001",
                "evidenceType": "image",
                "evidenceSource": "photo.jpg",
            }
        )

        normalized = _normalize_checklist_evidence(checklist)

        self.assertIsInstance(normalized["items"][0]["evidence"], list)
        self.assertEqual(1, len(normalized["items"][0]["evidence"]))
        self.assertEqual("EV-0001", normalized["items"][0]["evidence"][0]["evidenceId"])

    def test_keeps_array_evidence_unchanged(self):
        checklist = self._base_checklist(
            [
                {
                    "evidenceId": "EV-0001",
                    "evidenceType": "image",
                    "evidenceSource": "photo.jpg",
                },
                {
                    "evidenceId": "EV-0002",
                    "evidenceType": "document",
                    "evidenceSource": "doc.txt",
                },
            ]
        )

        normalized = _normalize_checklist_evidence(checklist)

        self.assertEqual(2, len(normalized["items"][0]["evidence"]))
        self.assertEqual("EV-0002", normalized["items"][0]["evidence"][1]["evidenceId"])

    def test_converts_null_evidence_to_empty_array(self):
        checklist = self._base_checklist(None)

        normalized = _normalize_checklist_evidence(checklist)

        self.assertEqual([], normalized["items"][0]["evidence"])

    def test_leaves_missing_evidence_missing(self):
        checklist = self._base_checklist(MISSING)

        normalized = _normalize_checklist_evidence(checklist)

        self.assertNotIn("evidence", normalized["items"][0])


class EnrichFindingsWithItemCodeTests(unittest.TestCase):

    def test_adds_item_code_from_checklist_item_id(self):
        checklist = {
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "VIG-0001",
                    "compliance": "Compliant",
                }
            ]
        }
        findings = [
            {
                "schemaVersion": "1.0",
                "finding": {
                    "findingId": "ABCD-VIG-2026-01",
                    "domain": "VIG",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Location",
                    "itemId": "item-1",
                    "description": "desc",
                },
            }
        ]

        enriched = _enrich_findings_with_item_code(findings, checklist)

        self.assertEqual("VIG-0001", enriched[0]["finding"]["itemCode"])

    def test_raises_when_finding_item_id_has_no_checklist_match(self):
        checklist = {
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "VIG-0001",
                    "compliance": "Compliant",
                }
            ]
        }
        findings = [
            {
                "schemaVersion": "1.0",
                "finding": {
                    "findingId": "ABCD-VIG-2026-01",
                    "domain": "VIG",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Location",
                    "itemId": "item-2",
                    "description": "desc",
                },
            }
        ]

        with self.assertRaises(ValueError):
            _enrich_findings_with_item_code(findings, checklist)


if __name__ == "__main__":
    unittest.main()
