import unittest

from jsonschema.exceptions import ValidationError

from models import validate_checklist


class ChecklistSchemaFieldsTests(unittest.TestCase):

    def test_accepts_location_name_location_code_and_specialty_fields(self):
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "inspection-1",
                "inspectionCode": "MDPP-I-0001",
                "specialtyId": "specialty-1",
                "providerId": "provider-1",
                "locationName": "Aeropuerto Internacional Gregorio Luperon",
                "locationCode": "MDPP",
                "specialtyCode": "SUR",
                "specialtyName": "Vigilancia",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "SUR-0001",
                    "compliance": "Compliant",
                }
            ],
        }

        validate_checklist(checklist)

    def test_accepts_inspection_window_dates(self):
        # The checklist app exports the field-recorded inspection window so
        # Alfresco can date the inspection folder, which in turn dates every
        # checklist item (items carry no date of their own). completionDate is
        # kept for compatibility.
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "inspection-1",
                "inspectionCode": "MDPP-I-0001",
                "specialtyId": "specialty-1",
                "providerId": "provider-1",
                "specialtyCode": "SUR",
                "specialtyName": "Vigilancia",
                "startDate": "2025-03-26",
                "endDate": "2025-03-27",
                "completionDate": "2025-03-27",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "SUR-0001",
                    "compliance": "Compliant",
                }
            ],
        }

        validate_checklist(checklist)

    def test_rejects_a_non_string_inspection_window_date(self):
        # "format": "date" is enforced by models._format_checker; a non-string is
        # rejected by the declared type before the format check applies.
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "inspection-1",
                "inspectionCode": "MDPP-I-0001",
                "specialtyId": "specialty-1",
                "providerId": "provider-1",
                "specialtyCode": "SUR",
                "specialtyName": "Vigilancia",
                "startDate": 20250326,
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "SUR-0001",
                    "compliance": "Compliant",
                }
            ],
        }

        with self.assertRaises(ValidationError):
            validate_checklist(checklist)

    def test_rejects_a_malformed_date_string(self):
        # Regression guard: without a FormatChecker a string like this validated
        # clean and reached Alfresco as a malformed date.
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "inspection-1",
                "inspectionCode": "MDPP-I-0001",
                "specialtyId": "specialty-1",
                "providerId": "provider-1",
                "specialtyCode": "SUR",
                "specialtyName": "Vigilancia",
                "startDate": "NOT-A-DATE",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "SUR-0001",
                    "compliance": "Compliant",
                }
            ],
        }

        with self.assertRaises(ValidationError):
            validate_checklist(checklist)

    def test_accepts_new_item_field_names(self):
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "inspection-1",
                "inspectionCode": "MDPP-I-0001",
                "specialtyId": "specialty-1",
                "providerId": "provider-1",
                "specialtyCode": "SUR",
                "specialtyName": "Vigilancia",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "SUR-0001",
                    "requirementText": "Pregunta",
                    "itemVerificationMethod": "Verificar documentos",
                    "inspectorComment": "Comentario",
                    "complianceStatus": "Non-Compliant",
                    "nominalRisk": "Medium",
                    "evidenceItems": [
                        {
                            "evidenceId": "EV-0001-01",
                            "evidenceType": "image",
                            "source": "photo.jpg",
                            "hashValue": "18e26a6fc16cc22afc597fca15168806cd4afc12d9b4fe03ea7c258911996405",
                            "immutable": True,
                            "sealedDate": "2026-04-16T14:52:35.331Z",
                        }
                    ],
                }
            ],
        }

        validate_checklist(checklist)


if __name__ == "__main__":
    unittest.main()
