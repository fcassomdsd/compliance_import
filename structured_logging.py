"""Structured JSON logging for the import service (P3.5).

Until now every line this service wrote was free text
(``%(asctime)s %(levelname)s %(name)s: %(message)s``), which a log
aggregator can store and little else: you can grep it, but you cannot ask
for "errors in the last hour" or "everything for this upload" without a
parser per message shape.

Three things this does beyond reformatting.

**Uvicorn's loggers are reconfigured too.** ``logging.basicConfig`` only
touches the root logger, and uvicorn installs its own handlers on
``uvicorn``, ``uvicorn.error`` and ``uvicorn.access``. Left alone they keep
writing their own text format to the same stream, and Promtail parses a
container's output as one format or the other -- a stream that is 90% JSON
is a stream that is not JSON.

**A request id is attached to every line.** An import is a multi-step
operation that logs from several modules; without a correlation id, telling
one upload's lines from another's under concurrent load means guessing from
timestamps.

**Alfresco tickets are stripped from logged URLs.** This is a live leak, not
a hypothetical: ``resolve_ticket_identity`` calls Alfresco with
``params={"alf_ticket": ticket}``, and ``AlfrescoClient._check_response``
logs ``response.request.url`` on any failure -- so today a rejected ticket
is written to stdout in full. An Alfresco ticket is a bearer credential;
anyone holding it is that user until it expires. It was survivable while
logs stayed on one host and is not once they are shipped to an aggregator,
so the redaction happens in the formatter, where it cannot be forgotten at
a call site.
"""

import json
import logging
import os
import re
import time
import uuid
from contextvars import ContextVar

SERVICE = "compliance_import"

# The request id in scope for the current task. A ContextVar rather than a
# thread local because this is an asyncio application: several requests share
# a thread, and a thread local would hand them each other's ids.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Query parameters whose values are credentials. alf_ticket is the one that
# actually appears in this service's logs today; the rest are here so that a
# future URL carrying one is covered before anyone notices.
_SECRET_PARAMS = ("alf_ticket", "ticket", "password", "api_key", "apikey", "token", "key")
_SECRET_QUERY_RE = re.compile(
    r"(?i)\b(" + "|".join(_SECRET_PARAMS) + r")=([^&\s\"']+)"
)

# Attributes LogRecord always carries. Anything else on a record was put
# there by a caller (`logger.info(..., extra={...})`) and is worth keeping as
# its own field.
#
# `color_message` is the exception, and it is uvicorn's: every uvicorn log
# record carries an ANSI-coloured duplicate of its own message under that
# name. Keeping it doubles the size of every uvicorn line and fills the field
# with escape sequences, for a second copy of text already in `msg`.
_STANDARD_ATTRS = frozenset(
    """args asctime created exc_info exc_text filename funcName levelname levelno
    lineno module msecs message msg name pathname process processName relativeCreated
    stack_info thread threadName taskName color_message""".split()
)


def redact(text):
    """Replace the value of any credential-bearing query parameter."""
    if not text:
        return text
    return _SECRET_QUERY_RE.sub(lambda m: f"{m.group(1)}=[redacted]", str(text))


class JsonFormatter(logging.Formatter):
    # UTC, because the timestamps below are written with a trailing Z.
    # logging's default converter is localtime, so without this the record
    # would claim UTC and carry the host's wall clock -- the kind of error
    # that only surfaces while correlating an incident across machines,
    # which is the worst possible moment to find it.
    converter = time.gmtime

    def format(self, record):
        payload = {
            # A real timestamp rather than logging's default local-time
            # string: an aggregator collating several hosts needs an
            # unambiguous instant, and %(asctime)s is neither ISO 8601 nor
            # timezone-qualified.
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "service": SERVICE,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }

        rid = getattr(record, "request_id", "") or request_id_var.get()
        if rid:
            payload["request_id"] = rid

        if record.exc_info:
            payload["error"] = redact(self.formatException(record.exc_info))

        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key in payload or key.startswith("_"):
                continue
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                value = str(value)
            payload[key] = redact(value) if isinstance(value, str) else value

        try:
            return json.dumps(payload, default=str)
        except (TypeError, ValueError):
            # Never lose a line to a formatting problem -- most often an
            # error report, which is when losing it hurts most.
            return json.dumps(
                {"ts": payload["ts"], "level": payload["level"], "service": SERVICE,
                 "msg": payload["msg"], "logging_error": "record could not be serialized"}
            )


class TextFormatter(logging.Formatter):
    """The previous format, with the same redaction applied.

    Redaction is not a JSON-mode feature: a ticket in a development log is
    still a live credential, and a developer is far more likely to paste a
    log excerpt into a ticket or a chat than to ship it anywhere.
    """

    def __init__(self):
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")

    def format(self, record):
        return redact(super().format(record))


def use_json():
    explicit = os.getenv("LOG_FORMAT", "").strip().lower()
    if explicit == "json":
        return True
    if explicit == "text":
        return False
    return os.getenv("APP_ENV", "").strip().lower() == "production"


def configure_logging(level=logging.INFO):
    """Install the formatter on the root logger and on uvicorn's own."""
    formatter = JsonFormatter() if use_json() else TextFormatter()

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Uvicorn installs handlers of its own before this runs in a normal
    # `uvicorn main:app` start, and they do not go through basicConfig.
    # Point them at the same formatter rather than removing them, so
    # uvicorn's own start-up and access lines stay in the stream -- in the
    # same format as everything else.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        for h in lg.handlers:
            h.setFormatter(formatter)

    return "json" if isinstance(formatter, JsonFormatter) else "text"


def new_request_id():
    return uuid.uuid4().hex[:16]


def bind_request_id(value=None):
    """Bind a request id for the current context, returning it."""
    rid = value or new_request_id()
    request_id_var.set(rid)
    return rid
