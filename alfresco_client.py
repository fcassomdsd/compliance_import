import json
import logging
import os
from pathlib import Path

import requests
from id_utils import build_checklist_id, build_followup_id_seq
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEFAULT_ALFRESCO_URL = "http://proxy:8080/alfresco/api/-default-/public/alfresco/versions/1"
DEFAULT_CANONICAL_JSON_PATH = "Sites/vigilancia-de-la-so/documentLibrary/Vigilancia/Datos de campo"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_RETRY_TOTAL = 3
DEFAULT_RETRY_CONNECT = 3
DEFAULT_RETRY_STATUS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5
DEFAULT_RETRY_READ = 1
DEFAULT_RETRY_STATUS_CODES = [429, 500, 502, 503, 504]
DEFAULT_FOLLOWUP_SEQ_MAX_RETRIES = 5


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
        self.retry_read = int(os.getenv("ALFRESCO_RETRY_READ", str(DEFAULT_RETRY_READ)))
        self.retry_status = int(os.getenv("ALFRESCO_RETRY_STATUS", str(DEFAULT_RETRY_STATUS)))
        self.retry_backoff_seconds = float(
            os.getenv("ALFRESCO_RETRY_BACKOFF_SECONDS", str(DEFAULT_RETRY_BACKOFF_SECONDS))
        )

        username = _read_required_setting("ALFRESCO_USERNAME", "/run/secrets/alfresco_username")
        password = _read_required_setting("ALFRESCO_PASSWORD", "/run/secrets/alfresco_password")

        self.session = requests.Session()
        self.session.auth = (username, password)
        self._ensured_specialty_folders = set()

        retry = Retry(
            total=self.retry_total,
            connect=self.retry_connect,
            read=self.retry_read,
            status=self.retry_status,
            backoff_factor=self.retry_backoff_seconds,
            status_forcelist=DEFAULT_RETRY_STATUS_CODES,
            allowed_methods=frozenset(["POST"]),
            raise_on_status=False
        )

        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)


    def _ensure_specialty_folder(self, specialty_name):

        if specialty_name in self._ensured_specialty_folders:
            return

        payload = {
            "name": specialty_name,
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

        self._ensured_specialty_folders.add(specialty_name)

    def _check_response(self, response):

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = response.status_code
            logger.warning("Alfresco request failed (%s) for %s", status, response.request.url)
            raise RuntimeError(f"Alfresco request failed ({status})") from exc

        return response


    def _post(self, url, **kwargs):

        response = self.session.post(url, timeout=self.timeout_seconds, **kwargs)
        self._check_response(response)
        return response


    def upload_json_document(self, filename, document, specialty_name):

        self._ensure_specialty_folder(specialty_name)

        payload = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")

        files = {
            "filedata": (f"{filename}.json", payload, "application/json")
        }

        data = {
            "name": f"{filename}.json",
            "nodeType": "cm:content",
            "relativePath": f"{self.canonical_json_path}/{specialty_name}",
            "autoRename": "true"
        }

        r = self._post(
            f"{self.base_url}/nodes/-root-/children",
            data=data,
            files=files
        )

        return r.json()


    def store_checklist_document(self, checklist):

        checklist_data = checklist["checklist"]
        specialty_name = checklist_data["specialtyName"]
        checklist_id = checklist_data.get("checklistId") or build_checklist_id(
            checklist_data["inspectionCode"],
            checklist_data["specialtyCode"],
        )
        filename = f"Checklist {checklist_id}"
        return self.upload_json_document(filename, checklist, specialty_name)


    def store_finding_document(self, finding):

        finding_id = finding["finding"]["findingId"]
        specialty_name = finding["finding"]["specialtyName"]
        filename = f"Finding {finding_id}"
        return self.upload_json_document(filename, finding, specialty_name)


    def _resolve_next_followup_seq(self, relative_path, prefix):
        response = self.session.get(
            f"{self.base_url}/nodes/-root-/children",
            params={
                "relativePath": relative_path,
                "maxItems": 1000,
            },
            timeout=self.timeout_seconds,
        )
        self._check_response(response)

        entries = response.json().get("list", {}).get("entries", [])
        # Follow-up sequences are 1-based: an empty folder yields 01.
        max_seq = 0

        for entry in entries:
            name = entry.get("entry", {}).get("name", "")
            if not name.startswith(prefix):
                continue

            base = name[len(prefix):].lstrip()
            if "." in base:
                base = base.split(".")[0]

            try:
                seq = int(base.strip())
                if seq > max_seq:
                    max_seq = seq
            except (ValueError, TypeError):
                continue

        return max_seq + 1


    def _upload_followup_json(self, filename, document, specialty_name):

        self._ensure_specialty_folder(specialty_name)

        payload = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")

        files = {
            "filedata": (f"{filename}.json", payload, "application/json")
        }

        data = {
            "name": f"{filename}.json",
            "nodeType": "cm:content",
            "relativePath": f"{self.canonical_json_path}/{specialty_name}",
        }

        response = self.session.post(
            f"{self.base_url}/nodes/-root-/children",
            data=data,
            files=files,
            timeout=self.timeout_seconds,
        )

        if response.status_code == 409:
            return None

        self._check_response(response)
        return response.json()


    def store_followup_report_document(self, followup_report, specialty_name):

        report_data = followup_report["followUpReport"]
        finding_id = report_data["findingId"]
        relative_path = f"{self.canonical_json_path}/{specialty_name}"
        prefix = f"FollowUp {finding_id}"

        for _attempt in range(DEFAULT_FOLLOWUP_SEQ_MAX_RETRIES):
            seq = self._resolve_next_followup_seq(relative_path, prefix)
            report_data["followUpId"] = build_followup_id_seq(finding_id, seq)
            filename = f"{prefix} {seq:02d}"

            result = self._upload_followup_json(filename, followup_report, specialty_name)
            if result is not None:
                result["storedFilename"] = f"{filename}.json"
                return result

        raise RuntimeError(
            f"Failed to store follow-up for finding '{finding_id}' after "
            f"{DEFAULT_FOLLOWUP_SEQ_MAX_RETRIES} attempts due to sequence conflicts"
        )


    def store_evidence_file(self, specialty_name, filepath):

        self._ensure_specialty_folder(specialty_name)

        with open(filepath, "rb") as evidence_file:
            files = {
                "filedata": (filepath.name, evidence_file)
            }

            data = {
                "name": filepath.name,
                "nodeType": "cm:content",
                "relativePath": f"{self.canonical_json_path}/{specialty_name}",
                "autoRename": "true"
            }

            response = self._post(
                f"{self.base_url}/nodes/-root-/children",
                data=data,
                files=files
            )

        return response.json()


    def store_followup_evidence_file(self, specialty_name, filepath):
        return self.store_evidence_file(specialty_name, filepath)
