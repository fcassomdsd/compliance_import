import json
from alfresco_client import AlfrescoClient
from models import validate_inspection


def process_inspection(path):

    with open(f"{path}/inspection.json") as f:
        inspection = json.load(f)

    validate_inspection(inspection)

    alf = AlfrescoClient()

    inspection_node = alf.create_inspection(inspection)

    checklist_node = alf.create_checklist(
        inspection_node,
        inspection["checklist"]
    )

    for item in inspection["items"]:

        item_node = alf.create_checklist_item(checklist_node, item)

        if "evidence" in item:
            for ev in item["evidence"]:

                file_path = f"{path}/evidence/{ev['file']}"

                alf.upload_evidence(item_node, file_path, ev)

        if "finding" in item:
            alf.create_finding(item_node, item["finding"])

    return inspection["inspection"]["inspectionId"]
