import json
from jsonschema import validate

def validate_inspection(data):

    with open("schema/inspection.schema.json") as f:
        schema = json.load(f)

    validate(instance=data, schema=schema)
