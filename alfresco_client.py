import json
import os
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_ALFRESCO_URL = "http://localhost:8080/alfresco/api/-default-/public/alfresco/versions/1"
DEFAULT_CANONICAL_JSON_PATH = "Sites/vigilancia-de-la-so/documentLibrary/Inspecciones/Inspecciones/Datos de campo"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_RETRY_TOTAL = 3
DEFAULT_RETRY_CONNECT = 3
DEFAULT_RETRY_STATUS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5
DEFAULT_RETRY_STATUS_CODES = [429, 500, 502, 503, 504]


def _read_secret_value(path):

    secret_path = Path(path)

    if not secret_path.is_file():
        return None

    value = secret_path.read_text(encoding="utf-8").strip()
    return value or None


def _read_required_setting(env_name, default_secret_path):

    file_env_name = f"{env_name}_FILE"
    file_path = os.getenv(file_env_name)

    if file_path:
        value = _read_secret_value(file_path)
        if value:
            return value

    default_secret_value = _read_secret_value(default_secret_path)
    if default_secret_value:
        return default_secret_value

    env_value = os.getenv(env_name)
    if env_value:
        return env_value

    raise ValueError(
        f"Missing {env_name}. Set {env_name}, {file_env_name}, or mount secret at {default_secret_path}"
    )


class AlfrescoClient:

    def __init__(self):

        self.base_url = os.getenv("ALFRESCO_URL", DEFAULT_ALFRESCO_URL)
        self.canonical_json_path = os.getenv("ALFRESCO_CANONICAL_JSON_PATH", DEFAULT_CANONICAL_JSON_PATH)
        self.timeout_seconds = float(os.getenv("ALFRESCO_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        self.retry_total = int(os.getenv("ALFRESCO_RETRY_TOTAL", str(DEFAULT_RETRY_TOTAL)))
        self.retry_connect = int(os.getenv("ALFRESCO_RETRY_CONNECT", str(DEFAULT_RETRY_CONNECT)))
        self.retry_status = int(os.getenv("ALFRESCO_RETRY_STATUS", str(DEFAULT_RETRY_STATUS)))
        self.retry_backoff_seconds = float(
            os.getenv("ALFRESCO_RETRY_BACKOFF_SECONDS", str(DEFAULT_RETRY_BACKOFF_SECONDS))
        )

        username = _read_required_setting("ALFRESCO_USERNAME", "/run/secrets/alfresco_username")
        password = _read_required_setting("ALFRESCO_PASSWORD", "/run/secrets/alfresco_password")

        self.session = requests.Session()
        self.session.auth = (username, password)
        self._ensured_domain_folders = set()

        retry = Retry(
            total=self.retry_total,
            connect=self.retry_connect,
            read=0,
            status=self.retry_status,
            backoff_factor=self.retry_backoff_seconds,
            status_forcelist=DEFAULT_RETRY_STATUS_CODES,
            allowed_methods=frozenset(["POST"]),
            raise_on_status=False
        )

        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)


    def _ensure_domain_folder(self, domain):

        if domain in self._ensured_domain_folders:
            return

        payload = {
            "name": domain,
            "nodeType": "cm:folder",
            "relativePath": self.canonical_json_path
        }

        response = self.session.post(
            f"{self.base_url}/nodes/-root-/children",
            json=payload,
            timeout=self.timeout_seconds
        )

        if response.status_code != 409:
            self._check_response(response)

        self._ensured_domain_folders.add(domain)

    def _check_response(self, response):

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = response.status_code
            body = response.text.strip()
            body_excerpt = body[:500] if body else "<empty response body>"
            raise RuntimeError(f"Alfresco request failed ({status}): {body_excerpt}") from exc

        return response


    def _post(self, url, **kwargs):

        response = self.session.post(url, timeout=self.timeout_seconds, **kwargs)
        self._check_response(response)
        return response


    def upload_json_document(self, filename, document, domain):

        self._ensure_domain_folder(domain)

        payload = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")

        files = {
            "filedata": (f"{filename}.json", payload, "application/json")
        }

        data = {
            "name": f"{filename}.json",
            "nodeType": "cm:content",
            "relativePath": f"{self.canonical_json_path}/{domain}",
            "autoRename": "true"
        }

        r = self._post(
            f"{self.base_url}/nodes/-root-/children",
            data=data,
            files=files
        )

        return r.json()


    def store_checklist_document(self, checklist):

        inspection_id = checklist["checklist"]["inspectionCode"]
        domain = checklist["checklist"]["domain"]
        filename = f"Checklist {inspection_id} {domain}"
        return self.upload_json_document(filename, checklist, domain)


    def store_finding_document(self, finding):

        finding_id = finding["finding"]["findingId"]
        domain = finding["finding"]["domain"]
        filename = f"Finding {finding_id}"
        return self.upload_json_document(filename, finding, domain)


    def store_evidence_file(self, domain, filepath):

        self._ensure_domain_folder(domain)

        with open(filepath, "rb") as evidence_file:
            files = {
                "filedata": (filepath.name, evidence_file)
            }

            data = {
                "name": filepath.name,
                "nodeType": "cm:content",
                "relativePath": f"{self.canonical_json_path}/{domain}",
                "autoRename": "true"
            }

            response = self._post(
                f"{self.base_url}/nodes/-root-/children",
                data=data,
                files=files
            )

        return response.json()

    def create_inspection(self, inspection):

        payload = {
            "name": inspection["inspection"]["inspectionId"],
            "nodeType": "vso:inspection",
            "properties": {
                "vso:inspectionType": inspection["inspection"]["type"],
                "vso:startDate": inspection["inspection"]["startDate"]
            }
        }

        r = self._post(
            f"{self.base_url}/nodes/-root-/children",
            json=payload
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

        r = self._post(
            f"{self.base_url}/nodes/{parent}/children",
            json=payload
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

        r = self._post(
            f"{self.base_url}/nodes/{parent}/children",
            json=payload
        )

        return r.json()["entry"]["id"]


    def upload_evidence(self, parent, filepath, metadata):

        with open(filepath, "rb") as evidence_file:
            files = {
                "filedata": evidence_file
            }

            data = {
                "name": metadata["file"],
                "nodeType": "vso:evidenceItem"
            }

            r = self._post(
                f"{self.base_url}/nodes/{parent}/children",
                data=data,
                files=files
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

        r = self._post(
            f"{self.base_url}/nodes/{parent}/children",
            json=payload
        )

        return r.json()
