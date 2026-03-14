import requests

ALFRESCO_URL = "http://localhost:8080/alfresco/api/-default-/public/alfresco/versions/1"
AUTH = ("admin","admin")


class AlfrescoClient:

    def create_inspection(self, inspection):

        payload = {
            "name": inspection["inspection"]["inspectionId"],
            "nodeType": "vso:inspection",
            "properties": {
                "vso:inspectionType": inspection["inspection"]["type"],
                "vso:startDate": inspection["inspection"]["startDate"]
            }
        }

        r = requests.post(
            f"{ALFRESCO_URL}/nodes/-root-/children",
            json=payload,
            auth=AUTH
        )

        return r.json()["entry"]["id"]


    def create_checklist(self, parent, checklist):

        payload = {
            "name": checklist["name"],
            "nodeType": "vso:inspectionChecklist",
            "properties": {
                "vso:checklistId": checklist["checklistId"]
            }
        }

        r = requests.post(
            f"{ALFRESCO_URL}/nodes/{parent}/children",
            json=payload,
            auth=AUTH
        )

        return r.json()["entry"]["id"]


    def create_checklist_item(self, parent, item):

        payload = {
            "name": item["itemId"],
            "nodeType": "vso:checklistItem",
            "properties": {
                "vso:itemId": item["itemId"],
                "vso:complianceStatus": item["compliance"],
                "vso:requirementText": item.get("requirement")
            }
        }

        r = requests.post(
            f"{ALFRESCO_URL}/nodes/{parent}/children",
            json=payload,
            auth=AUTH
        )

        return r.json()["entry"]["id"]


    def upload_evidence(self, parent, filepath, metadata):

        files = {
            "filedata": open(filepath, "rb")
        }

        data = {
            "name": metadata["file"],
            "nodeType": "vso:evidenceItem"
        }

        r = requests.post(
            f"{ALFRESCO_URL}/nodes/{parent}/children",
            data=data,
            files=files,
            auth=AUTH
        )

        return r.json()


    def create_finding(self, parent, finding):

        payload = {
            "name": "Finding",
            "nodeType": "vso:finding",
            "properties": {
                "vso:findingLevel": finding["level"],
                "vso:description": finding["description"]
            }
        }

        r = requests.post(
            f"{ALFRESCO_URL}/nodes/{parent}/children",
            json=payload,
            auth=AUTH
        )

        return r.json()
