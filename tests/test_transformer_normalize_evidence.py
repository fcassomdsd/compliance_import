import unittest

from id_utils import build_finding_id
from transformer import (
    _enrich_findings_with_item_code,
    _normalize_checklist_evidence,
)


MISSING = object()
ABCD_FINDING_ID = build_finding_id("ABCD-001", "VIG", 1)


class NormalizeChecklistEvidenceTests(unittest.TestCase):

    def _base_checklist(self, evidence_value):
        item = {
            "itemId": "item-1",
            "itemCode": "VIG-0001",
            "compliance": "Compliant",
        }

        if evidence_value is not MISSING:
            item["evidenceItems"] = evidence_value

        return {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "id-1",
                "inspectionCode": "ABCD-001",
                "specialtyId": "specialty-1",
                "specialtyCode": "VIG",
                "specialtyName": "Vigilancia",
                "providerId": "provider-1",
            },
            "items": [item],
        }

    def test_wraps_object_evidence_into_array(self):
        checklist = self._base_checklist(
            {
                "evidenceId": "EV-0001",
                "evidenceType": "image",
                "source": "photo.jpg",
            }
        )

        normalized = _normalize_checklist_evidence(checklist)

        self.assertIsInstance(normalized["items"][0]["evidenceItems"], list)
        self.assertEqual(1, len(normalized["items"][0]["evidenceItems"]))
        self.assertEqual("EV-0001", normalized["items"][0]["evidenceItems"][0]["evidenceId"])

    def test_keeps_array_evidence_unchanged(self):
        checklist = self._base_checklist(
            [
                {
                    "evidenceId": "EV-0001",
                    "evidenceType": "image",
                    "source": "photo.jpg",
                },
                {
                    "evidenceId": "EV-0002",
                    "evidenceType": "document",
                    "source": "doc.txt",
                },
            ]
        )

        normalized = _normalize_checklist_evidence(checklist)

        self.assertEqual(2, len(normalized["items"][0]["evidenceItems"]))
        self.assertEqual("EV-0002", normalized["items"][0]["evidenceItems"][1]["evidenceId"])

    def test_converts_null_evidence_to_empty_array(self):
        checklist = self._base_checklist(None)

        normalized = _normalize_checklist_evidence(checklist)

        self.assertEqual([], normalized["items"][0]["evidenceItems"])

    def test_leaves_missing_evidence_missing(self):
        checklist = self._base_checklist(MISSING)

        normalized = _normalize_checklist_evidence(checklist)

        self.assertNotIn("evidenceItems", normalized["items"][0])


class EnrichFindingsWithItemCodeTests(unittest.TestCase):

    def test_adds_checklist_item_code_from_checklist_item_code(self):
        checklist = {
            "checklist": {
                "locationCode": "MDPP",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "VIG-0001",
                    "requirement": "Requirement text",
                    "compliance": "Compliant",
                }
            ]
        }
        findings = [
            {
                "schemaVersion": "1.0",
                "finding": {
                    "findingId": ABCD_FINDING_ID,
                    "specialtyId": "specialty-1",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Location",
                    "checklistItemCode": "VIG-0001",
                    "description": "desc",
                },
            }
        ]

        enriched = _enrich_findings_with_item_code(findings, checklist)

        self.assertEqual("VIG-0001", enriched[0]["finding"]["checklistItemCode"])
        self.assertEqual("MDPP", enriched[0]["finding"]["locationCode"])
        self.assertEqual("Requirement text", enriched[0]["finding"]["requirementBreached"])

    def test_raises_when_finding_checklist_item_code_has_no_checklist_match(self):
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
                    "findingId": ABCD_FINDING_ID,
                    "specialtyId": "specialty-1",
                    "providerId": "provider-1",
                    "locationId": "location-1",
                    "locationName": "Location",
                    "checklistItemCode": "VIG-0002",
                    "description": "desc",
                },
            }
        ]

        with self.assertRaises(ValueError):
            _enrich_findings_with_item_code(findings, checklist)

    def test_maps_finding_by_checklist_item_code(self):
        checklist = {
            "checklist": {
                "locationCode": "MDPP",
                "providerId": "provider-1",
                "locationId": "location-1",
                "locationName": "Location",
                "specialtyId": "specialty-1",
                "specialtyCode": "VIG",
                "specialtyName": "Vigilancia",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "VIG-0001",
                    "requirementText": "Requirement text",
                    "complianceStatus": "Compliant",
                }
            ]
        }
        findings = [
            {
                "schemaVersion": "1.0",
                "finding": {
                    "findingId": ABCD_FINDING_ID,
                    "checklistItemCode": "VIG-0001",
                    "description": "desc",
                },
            }
        ]

        enriched = _enrich_findings_with_item_code(findings, checklist)

        self.assertEqual("provider-1", enriched[0]["finding"]["providerId"])
        self.assertEqual("location-1", enriched[0]["finding"]["locationId"])
        self.assertEqual("Location", enriched[0]["finding"]["locationName"])
        self.assertEqual("MDPP", enriched[0]["finding"]["locationCode"])
        self.assertEqual("Requirement text", enriched[0]["finding"]["requirementBreached"])


if __name__ == "__main__":
    unittest.main()
