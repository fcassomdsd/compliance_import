"""Tests for structured_logging -- the import service's JSON log format.

The redaction tests are the ones that matter most. `resolve_ticket_identity`
calls Alfresco with `params={"alf_ticket": ticket}` and
`AlfrescoClient._check_response` logs `response.request.url` on any failure,
so without redaction a rejected Alfresco ticket is written to stdout in full.
An Alfresco ticket is a bearer credential: anyone holding it is that user
until it expires.
"""

import json
import logging
import os
import unittest
from io import StringIO

import structured_logging as sl


def render(record_call, formatter=None):
    """Run one logging call through a formatter and return the parsed line."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter or sl.JsonFormatter())
    logger = logging.getLogger("test.structured")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    record_call(logger)
    return stream.getvalue().strip()


class RedactionTests(unittest.TestCase):
    def test_alfresco_ticket_is_stripped_from_a_logged_url(self):
        line = render(
            lambda lg: lg.warning(
                "Alfresco request failed (%s) for %s",
                401,
                "http://alfresco:8080/alfresco/s/api/people?alf_ticket=TICKET_deadbeef",
            )
        )
        self.assertNotIn("TICKET_deadbeef", line)
        self.assertIn("alf_ticket=[redacted]", json.loads(line)["msg"])

    def test_other_query_parameters_survive(self):
        # Redaction that ate the whole URL would make the log line useless for
        # the thing it is there for: knowing which request failed.
        msg = json.loads(
            render(lambda lg: lg.warning("failed for http://a/b?alf_ticket=T&nodeId=abc&page=2"))
        )["msg"]
        self.assertIn("nodeId=abc", msg)
        self.assertIn("page=2", msg)
        self.assertNotIn("=T&", msg)

    def test_every_named_secret_parameter_is_covered(self):
        for param in ("alf_ticket", "ticket", "password", "api_key", "apikey", "token", "key"):
            with self.subTest(param=param):
                self.assertEqual(sl.redact(f"http://a?{param}=s3cret"), f"http://a?{param}=[redacted]")

    def test_redaction_is_case_insensitive(self):
        self.assertEqual(sl.redact("http://a?ALF_TICKET=x"), "http://a?ALF_TICKET=[redacted]")

    def test_redaction_applies_to_the_text_formatter_too(self):
        # A ticket in a development log is still a live credential, and a
        # developer is more likely to paste a log excerpt into a chat than to
        # ship it anywhere.
        line = render(
            lambda lg: lg.warning("failed for http://a?alf_ticket=TICKET_x"),
            formatter=sl.TextFormatter(),
        )
        self.assertNotIn("TICKET_x", line)

    def test_redaction_tolerates_empty_input(self):
        self.assertIsNone(sl.redact(None))
        self.assertEqual(sl.redact(""), "")


class FormatTests(unittest.TestCase):
    def test_line_is_one_json_object_with_the_expected_fields(self):
        payload = json.loads(render(lambda lg: lg.info("hello")))
        self.assertEqual(payload["level"], "info")
        self.assertEqual(payload["service"], "compliance_import")
        self.assertEqual(payload["logger"], "test.structured")
        self.assertEqual(payload["msg"], "hello")
        self.assertTrue(payload["ts"].endswith("Z"))

    def test_timestamp_is_utc_not_local_time(self):
        # The timestamp is written with a trailing Z. logging's default
        # converter is localtime, so without an explicit UTC converter the
        # record claims UTC and carries the host's wall clock -- an error that
        # only surfaces while correlating an incident across machines.
        import datetime

        payload = json.loads(render(lambda lg: lg.info("when")))
        logged = datetime.datetime.strptime(payload["ts"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=datetime.timezone.utc
        )
        delta = abs((datetime.datetime.now(datetime.timezone.utc) - logged).total_seconds())
        self.assertLess(delta, 5, f"timestamp {payload['ts']} is not UTC")

    def test_extra_fields_become_their_own_keys(self):
        payload = json.loads(
            render(lambda lg: lg.info("imported", extra={"documents": 4, "inspection": "AV-ZZZZ-I-0001"}))
        )
        self.assertEqual(payload["documents"], 4)
        self.assertEqual(payload["inspection"], "AV-ZZZZ-I-0001")

    def test_an_unserializable_extra_is_stringified_rather_than_losing_the_line(self):
        payload = json.loads(render(lambda lg: lg.info("odd", extra={"thing": object()})))
        self.assertEqual(payload["msg"], "odd")
        self.assertIn("object", payload["thing"])

    def test_exceptions_are_reported_in_their_own_field(self):
        def boom(lg):
            try:
                raise ValueError("kaboom")
            except ValueError:
                lg.exception("import failed")

        payload = json.loads(render(boom))
        self.assertEqual(payload["msg"], "import failed")
        self.assertIn("kaboom", payload["error"])


class RequestIdTests(unittest.TestCase):
    def tearDown(self):
        sl.request_id_var.set("")

    def test_a_bound_request_id_appears_on_every_line(self):
        sl.bind_request_id("req-abc")
        payload = json.loads(render(lambda lg: lg.info("step one")))
        self.assertEqual(payload["request_id"], "req-abc")

    def test_no_request_id_field_when_none_is_bound(self):
        # Absent rather than empty: an empty label in Loki is still a label.
        self.assertNotIn("request_id", json.loads(render(lambda lg: lg.info("no context"))))

    def test_bind_generates_one_when_given_nothing(self):
        rid = sl.bind_request_id()
        self.assertTrue(rid)
        self.assertEqual(sl.request_id_var.get(), rid)

    def test_generated_ids_differ(self):
        self.assertNotEqual(sl.new_request_id(), sl.new_request_id())


class FormatSelectionTests(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_json_in_production_text_otherwise(self):
        os.environ.pop("LOG_FORMAT", None)
        os.environ["APP_ENV"] = "production"
        self.assertTrue(sl.use_json())
        os.environ["APP_ENV"] = "development"
        self.assertFalse(sl.use_json())

    def test_log_format_overrides_in_both_directions(self):
        os.environ["APP_ENV"] = "development"
        os.environ["LOG_FORMAT"] = "json"
        self.assertTrue(sl.use_json())
        os.environ["APP_ENV"] = "production"
        os.environ["LOG_FORMAT"] = "text"
        self.assertFalse(sl.use_json())

    def test_configure_logging_reformats_uvicorns_own_handlers(self):
        # basicConfig only reaches the root logger; uvicorn installs handlers
        # of its own that would otherwise keep writing text into the same
        # stream, leaving output that is mostly JSON and therefore not JSON.
        os.environ["LOG_FORMAT"] = "json"
        access = logging.getLogger("uvicorn.access")
        access.handlers = [logging.StreamHandler()]
        sl.configure_logging()
        for handler in access.handlers:
            self.assertIsInstance(handler.formatter, sl.JsonFormatter)


if __name__ == "__main__":
    unittest.main()
