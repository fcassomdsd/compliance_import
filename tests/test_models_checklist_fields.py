import unittest

from models import validate_checklist


class ChecklistSchemaFieldsTests(unittest.TestCase):

    def test_accepts_location_name_icao_and_specialty_fields(self):
        checklist = {
            "schemaVersion": "1.0",
            "checklist": {
                "inspectionId": "inspection-1",
                "inspectionCode": "MDPP-2026-01",
                "domain": "VIG",
                "providerId": "provider-1",
                "locationName": "Aeropuerto Internacional Gregorio Luperon",
                "icaoCode": "MDPP",
                "specialtyId": "specialty-1",
                "specialtyCode": "VIG",
                "specialtyName": "Vigilancia",
            },
            "items": [
                {
                    "itemId": "item-1",
                    "itemCode": "VIG-0001",
                    "compliance": "Compliant",
                }
            ],
        }

        validate_checklist(checklist)


if __name__ == "__main__":
    unittest.main()
