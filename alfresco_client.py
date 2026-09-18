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
DEFAULT_LIST_PAGE_SIZE = 200

# Methods safe to retry automatically. GET/HEAD were previously excluded, so the
# follow-up sequence lookup got no retry at all.
DEFAULT_RETRY_METHODS = frozenset(["POST", "GET", "HEAD"])


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


class OperatorIdentityError(RuntimeError):
    """Raised when an operator ticket is missing, invalid or unverifiable."""


def resolve_ticket_identity(ticket):
    """Resolve an Alfresco ticket to the identity it belongs to.

    Returns ``{"userName", "displayName", "personId"}``. Raises
    ``OperatorIdentityError`` when the ticket is not accepted, so a caller can
    reject the request instead of writing unattributed or misattributed data.
    """

    if not ticket or not isinstance(ticket, str):
        raise OperatorIdentityError("Missing operator ticket")

    base_url = os.getenv("ALFRESCO_URL", DEFAULT_ALFRESCO_URL)
    timeout = float(os.getenv("ALFRESCO_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))

    try:
        response = requests.get(
            f"{base_url}/people/-me-",
            params={"alf_ticket": ticket},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise OperatorIdentityError(f"Could not reach Alfresco to verify the operator ticket: {exc}") from exc

    if response.status_code != 200:
        raise OperatorIdentityError(
            f"Alfresco rejected the operator ticket (status {response.status_code})"
        )

    try:
        entry = response.json().get("entry") or {}
    except ValueError as exc:
        raise OperatorIdentityError("Alfresco returned an unreadable identity response") from exc

    user_name = entry.get("userName") or entry.get("id")
    if not user_name:
        raise OperatorIdentityError("Alfresco identity response has no user name")

    display_name = " ".join(
        part for part in [entry.get("firstName"), entry.get("lastName")] if part
    ).strip()

    return {
        "userName": user_name,
        "displayName": display_name or user_name,
        "personId": entry.get("id"),
    }


class AlfrescoClient:

    def __init__(self, ticket=None):

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

        self.ticket = ticket or None
        self.session = requests.Session()

        if self.ticket:
            # Operator-authenticated writes: Alfresco resolves the ticket to the
            # inspector, so the documents it stores carry the inspector as
            # cm:creator/cm:modifier instead of the service account.
            self.session.params = {"alf_ticket": self.ticket}
        else:
            username = _read_required_setting("ALFRESCO_USERNAME", "/run/secrets/alfresco_username")
            password = _read_required_setting("ALFRESCO_PASSWORD", "/run/secrets/alfresco_password")
            self.session.auth = (username, password)

        self._ensured_specialty_folders = set()
        # Nodes created since begin_batch(), used to compensate a failed import.
        self._batch_created_ids = []
        self._batch_active = False

        retry = Retry(
            total=self.retry_total,
            connect=self.retry_connect,
            read=self.retry_read,
            status=self.retry_status,
            backoff_factor=self.retry_backoff_seconds,
            status_forcelist=DEFAULT_RETRY_STATUS_CODES,
            allowed_methods=DEFAULT_RETRY_METHODS,
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


    def _iter_children(self, relative_path):

        # CMIS listings are paginated; a single maxItems request silently
        # truncates, which previously capped the follow-up sequence lookup at
        # the first 1000 children.
        skip_count = 0

        while True:
            response = self.session.get(
                f"{self.base_url}/nodes/-root-/children",
                params={
                    "relativePath": relative_path,
                    "maxItems": DEFAULT_LIST_PAGE_SIZE,
                    "skipCount": skip_count,
                },
                timeout=self.timeout_seconds,
            )
            self._check_response(response)

            entries = response.json().get("list", {}).get("entries", [])
            for entry in entries:
                yield entry.get("entry", {})

            if len(entries) < DEFAULT_LIST_PAGE_SIZE:
                return

            skip_count += DEFAULT_LIST_PAGE_SIZE


    def _find_child_by_name(self, relative_path, name):

        for child in self._iter_children(relative_path):
            if child.get("name") == name:
                return child

        return None


    def _update_node_content(self, node_id, filename, payload, content_type):
        # Alfresco's v1 update-content endpoint takes the RAW bytes with the file's
        # own Content-Type. Sending multipart/form-data (which the create path uses,
        # and which `files=` produces) is rejected with 415 Unsupported Media Type -
        # so re-importing a payload that already exists failed here, while the
        # first import succeeded. `filename` stays in the signature because callers
        # pass it, but it is not part of this request.

        response = self.session.put(
            f"{self.base_url}/nodes/{node_id}/content",
            params={"majorVersion": "false"},
            data=payload,
            headers={"Content-Type": content_type},
            timeout=self.timeout_seconds,
        )
        self._check_response(response)
        return response.json()


    def _record_created(self, response_json):

        node_id = (response_json or {}).get("entry", {}).get("id")
        if node_id and self._batch_active:
            self._batch_created_ids.append(node_id)

        return response_json


    def begin_batch(self):

        """Start tracking nodes created by this import so they can be removed
        if a later step fails, instead of leaving a half-written inspection."""
        self._batch_created_ids = []
        self._batch_active = True


    def delete_nodes(self, node_ids):

        deleted = []

        for node_id in node_ids:
            try:
                response = self.session.delete(
                    f"{self.base_url}/nodes/{node_id}",
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                logger.warning("Could not delete node %s during rollback: %s", node_id, exc)
                continue

            if response.status_code in (204, 404):
                deleted.append(node_id)
            else:
                logger.warning(
                    "Could not delete node %s during rollback (status %s)", node_id, response.status_code
                )

        return deleted


    def rollback_batch(self):

        """Best-effort compensation: delete the nodes created since begin_batch()."""
        pending = list(reversed(self._batch_created_ids))
        self._batch_created_ids = []
        self._batch_active = False

        if pending:
            logger.warning("Rolling back %s document(s) from a failed import", len(pending))

        return self.delete_nodes(pending)


    def upload_json_document(self, filename, document, specialty_name):

        self._ensure_specialty_folder(specialty_name)

        payload = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        node_name = f"{filename}.json"
        relative_path = f"{self.canonical_json_path}/{specialty_name}"

        existing = self._find_child_by_name(relative_path, node_name)
        if existing:
            # Create-or-update keeps re-submitting the same ZIP idempotent, instead
            # of silently producing "Checklist ... (1).json" duplicates.
            updated = self._update_node_content(existing["id"], node_name, payload, "application/json")
            updated["updated"] = True
            return updated

        files = {"filedata": (node_name, payload, "application/json")}
        data = {
            "name": node_name,
            "nodeType": "cm:content",
            "relativePath": relative_path,
        }

        response = self.session.post(
            f"{self.base_url}/nodes/-root-/children",
            data=data,
            files=files,
            timeout=self.timeout_seconds,
        )

        # Lost a race with a concurrent import: update the node that won.
        if response.status_code == 409:
            existing = self._find_child_by_name(relative_path, node_name)
            if existing:
                updated = self._update_node_content(existing["id"], node_name, payload, "application/json")
                updated["updated"] = True
                return updated

        self._check_response(response)

        created = response.json()
        created["created"] = True
        return self._record_created(created)


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
        # Follow-up sequences are 1-based: an empty folder yields 01.
        max_seq = 0

        for child in self._iter_children(relative_path):
            name = child.get("name", "")
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

        relative_path = f"{self.canonical_json_path}/{specialty_name}"
        local_size = filepath.stat().st_size

        existing = self._find_child_by_name(relative_path, filepath.name)
        if existing and (existing.get("content") or {}).get("sizeInBytes") == local_size:
            # Same name and size: this is a re-import of the same evidence, so
            # leave the stored copy untouched.
            existing["skipped"] = True
            return existing

        # A new file, or a different file that happens to share the name. Let
        # Alfresco rename on collision rather than overwriting another
        # inspection's evidence under the same filename.
        with open(filepath, "rb") as evidence_file:
            files = {
                "filedata": (filepath.name, evidence_file)
            }

            data = {
                "name": filepath.name,
                "nodeType": "cm:content",
                "relativePath": relative_path,
                "autoRename": "true"
            }

            response = self._post(
                f"{self.base_url}/nodes/-root-/children",
                data=data,
                files=files
            )

        return self._record_created(response.json())


    def store_followup_evidence_file(self, specialty_name, filepath):
        return self.store_evidence_file(specialty_name, filepath)
