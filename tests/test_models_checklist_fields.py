import unittest

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
