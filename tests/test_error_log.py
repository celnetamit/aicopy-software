"""Error-log capture, storage, retention and admin access.

Errors used to be `print()` calls and bare `except Exception: pass`, so a broken
provider key, a failing export or a JavaScript fault looked identical to normal
operation. These tests cover the capture paths that replaced that.
"""

import json
import os
import re
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Imported first: this module configures the test environment (dev auth tokens,
# test database) before it imports webapp.
from tests.test_webapp_api import WsgiTestClient  # noqa: E402

import webapp  # noqa: E402
from app_store import AppStore  # noqa: E402


class ErrorFingerprintTests(unittest.TestCase):
    """Repeats of one fault must collapse instead of flooding the table."""

    def setUp(self):
        self.store = AppStore(database_url="", data_dir=tempfile.mkdtemp(prefix="errlog-"))

    def test_varying_ids_and_numbers_collapse_to_one_row(self):
        for index in range(5):
            self.store.record_error_event(
                code="TASK_PROCESS_FAILED",
                source="route:process",
                message=f"Task {index} failed after {index}s (id ab12cd34ef56{index})",
                exception_type="RuntimeError",
            )
        rows = self.store.list_error_events()
        self.assertEqual(len(rows), 1, "near-identical failures were not deduplicated")
        self.assertEqual(rows[0]["occurrence_count"], 5)

    def test_different_codes_stay_separate(self):
        self.store.record_error_event(code="A_FAILED", source="s", message="boom")
        self.store.record_error_event(code="B_FAILED", source="s", message="boom")
        self.assertEqual(len(self.store.list_error_events()), 2)

    def test_recurrence_outside_the_window_starts_a_new_row(self):
        self.store.record_error_event(code="X", source="s", message="same")
        stale = int(time.time()) - AppStore.ERROR_DEDUPE_WINDOW_SECONDS - 60
        self.store._execute("UPDATE error_events SET last_seen_at = ?", (stale,))

        self.store.record_error_event(code="X", source="s", message="same")
        rows = self.store.list_error_events()
        self.assertEqual(len(rows), 2, "a recurrence long after the window should open a new row")
        self.assertEqual(rows[0]["occurrence_count"], 1)

    def test_traceback_is_withheld_from_list_views(self):
        self.store.record_error_event(
            code="X", source="s", message="m", traceback_text="Traceback (most recent call last): ..."
        )
        self.assertNotIn("traceback", self.store.list_error_events()[0])
        self.assertIn("traceback", self.store.list_error_events(include_traceback=True)[0])
        event_id = self.store.list_error_events()[0]["id"]
        self.assertIn("Traceback", self.store.get_error_event(event_id)["traceback"])

    def test_oversized_fields_are_truncated(self):
        self.store.record_error_event(
            code="X", source="s", message="m" * 10_000, traceback_text="t" * 50_000
        )
        row = self.store.get_error_event(self.store.list_error_events()[0]["id"])
        self.assertLessEqual(len(row["message"]), AppStore.MAX_MESSAGE_CHARS)
        self.assertLessEqual(len(row["traceback"]), AppStore.MAX_TRACEBACK_CHARS)

    def test_summary_and_filters(self):
        self.store.record_error_event(code="A", source="one", message="a", level="ERROR")
        self.store.record_error_event(code="B", source="two", message="b", level="WARNING")
        summary = self.store.summarize_error_events()
        self.assertEqual(summary["distinct_faults"], 2)
        self.assertEqual(summary["by_level"], {"ERROR": 1, "WARNING": 1})
        self.assertEqual(len(self.store.list_error_events(level="WARNING")), 1)
        self.assertEqual(len(self.store.list_error_events(source="one")), 1)
        self.assertEqual(len(self.store.list_error_events(code="B")), 1)

    def test_purge_respects_cutoff(self):
        self.store.record_error_event(code="A", source="s", message="a")
        self.assertEqual(self.store.purge_error_events(before_ts=int(time.time()) - 3600), 0)
        self.assertEqual(len(self.store.list_error_events()), 1)
        self.assertEqual(self.store.purge_error_events(), 1)
        self.assertEqual(len(self.store.list_error_events()), 0)


class RouteCaptureTests(unittest.TestCase):
    """The plugin must capture both raised exceptions and returned 5xx bodies."""

    @classmethod
    def setUpClass(cls):
        # Routes registered here persist on the shared app; give them unique paths.
        @webapp.app.get("/api/__test_raises")
        def _raises():
            raise RuntimeError("deliberate test explosion")

        @webapp.app.get("/api/__test_returns_500")
        def _returns_500():
            return webapp._json_response(
                webapp._error_payload("DELIBERATE_SERVER_ERROR", "handled but fatal"), status=500
            )

        @webapp.app.get("/api/__test_returns_400")
        def _returns_400():
            return webapp._json_response(
                webapp._error_payload("DELIBERATE_CLIENT_ERROR", "bad input"), status=400
            )

    def setUp(self):
        webapp._STORE.clear_all_for_tests()
        self.client = WsgiTestClient(webapp.app)

    def test_unhandled_exception_becomes_500_and_is_recorded(self):
        status, payload = self.client.request("GET", "/api/__test_raises")
        self.assertEqual(status, 500)
        self.assertEqual(payload.get("error_code"), "INTERNAL_ERROR")
        self.assertNotIn("deliberate test explosion", json.dumps(payload), "internals leaked to the client")

        events = webapp._STORE.list_error_events(include_traceback=True)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["code"], "UNHANDLED_ROUTE_ERROR")
        self.assertEqual(event["exception_type"], "RuntimeError")
        self.assertEqual(event["status_code"], 500)
        self.assertIn("deliberate test explosion", event["message"])
        self.assertIn("Traceback", event["traceback"])
        self.assertIn("/api/__test_raises", event["request_path"])

    def test_returned_5xx_is_recorded_with_its_own_code(self):
        status, _ = self.client.request("GET", "/api/__test_returns_500")
        self.assertEqual(status, 500)
        events = webapp._STORE.list_error_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "DELIBERATE_SERVER_ERROR")
        self.assertEqual(events[0]["message"], "handled but fatal")

    def test_4xx_is_not_recorded(self):
        status, _ = self.client.request("GET", "/api/__test_returns_400")
        self.assertEqual(status, 400)
        self.assertEqual(
            webapp._STORE.list_error_events(), [], "handled client errors must not pollute the error log"
        )

    def test_normal_responses_are_not_recorded(self):
        status, _ = self.client.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(webapp._STORE.list_error_events(), [])

    def test_redirects_still_work_through_the_plugin(self):
        status, _ = self.client.request_text("GET", "/")
        self.assertEqual(status, 302, "HTTPResponse control flow was swallowed by the capture plugin")


class AdminErrorApiTests(unittest.TestCase):
    def setUp(self):
        webapp._STORE.clear_all_for_tests()
        self.client = WsgiTestClient(webapp.app)

    def _login(self, email):
        status, payload = self.client.request("POST", "/api/auth/google-login", {"id_token": f"test:{email}"})
        self.assertEqual(status, 200)
        return payload

    def test_error_log_requires_admin(self):
        self._login("writer@conwiz.in")
        for method, path, body in (
            ("GET", "/api/admin/error-events", None),
            ("GET", "/api/admin/error-events/abc", None),
            ("POST", "/api/admin/error-events/purge", {}),
        ):
            with self.subTest(path=path):
                status, _ = self.client.request(method, path, body)
                self.assertEqual(status, 403)

    def test_admin_reads_list_summary_and_detail(self):
        webapp._STORE.record_error_event(
            code="EXPORT_VARIANT_FAILED",
            source="export",
            message="Could not generate track_changes export",
            level="WARNING",
            traceback_text="Traceback: ...",
            context={"mode": "track_changes"},
        )
        self._login("amit@conwiz.in")

        status, payload = self.client.request("GET", "/api/admin/error-events")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(len(payload["events"]), 1)
        self.assertNotIn("traceback", payload["events"][0], "list view must not ship tracebacks")
        self.assertEqual(payload["summary"]["distinct_faults"], 1)
        self.assertIn("retention_days", payload)
        self.assertIn("log_file", payload)

        event_id = payload["events"][0]["id"]
        status, detail = self.client.request("GET", f"/api/admin/error-events/{event_id}")
        self.assertEqual(status, 200)
        self.assertIn("Traceback", detail["event"]["traceback"])
        self.assertEqual(detail["event"]["context"], {"mode": "track_changes"})

    def test_missing_event_returns_404(self):
        self._login("amit@conwiz.in")
        status, payload = self.client.request("GET", "/api/admin/error-events/not-a-real-id")
        self.assertEqual(status, 404)
        self.assertEqual(payload.get("error_code"), "ERROR_EVENT_NOT_FOUND")

    def test_purge_clears_the_log_and_is_audited(self):
        webapp._STORE.record_error_event(code="A", source="s", message="a")
        self._login("amit@conwiz.in")
        status, payload = self.client.request("POST", "/api/admin/error-events/purge", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["removed"], 1)
        self.assertEqual(webapp._STORE.list_error_events(), [])
        events = webapp._STORE.list_audit_events(event_type="admin_error_events_purged")
        self.assertEqual(len(events), 1)


class ClientErrorReportingTests(unittest.TestCase):
    def setUp(self):
        webapp._STORE.clear_all_for_tests()
        self.client = WsgiTestClient(webapp.app)
        self.client.request("POST", "/api/auth/google-login", {"id_token": "test:writer@conwiz.in"})

    def test_script_error_is_recorded_with_context(self):
        status, payload = self.client.request(
            "POST",
            "/api/client-errors",
            {
                "kind": "error",
                "message": "Cannot read properties of null (reading 'value')",
                "stack": "at renderPreview (app-preview.js:412:9)",
                "source": "/app-preview.js",
                "line": 412,
                "page": "/tasks/abc",
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("recorded"))

        events = webapp._STORE.list_error_events(source="client")
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["code"], "CLIENT_SCRIPT_ERROR")
        self.assertEqual(event["request_path"], "/tasks/abc")
        self.assertEqual(event["request_method"], "CLIENT")
        self.assertIn("renderPreview", event["context"]["stack"])

    def test_unhandled_rejection_gets_its_own_code(self):
        self.client.request(
            "POST", "/api/client-errors", {"kind": "unhandledrejection", "message": "NetworkError"}
        )
        self.assertEqual(webapp._STORE.list_error_events()[0]["code"], "CLIENT_UNHANDLED_REJECTION")

    def test_empty_message_is_rejected_without_recording(self):
        status, payload = self.client.request("POST", "/api/client-errors", {"message": "   "})
        self.assertEqual(status, 400)
        self.assertEqual(payload.get("error_code"), "CLIENT_ERROR_MESSAGE_REQUIRED")
        self.assertEqual(webapp._STORE.list_error_events(), [])

    def test_reporting_requires_authentication(self):
        anonymous = WsgiTestClient(webapp.app)
        status, _ = anonymous.request("POST", "/api/client-errors", {"message": "boom"})
        self.assertEqual(status, 401)


class ErrorReporterAssetTests(unittest.TestCase):
    """The beacon must load first and stay dependency-free."""

    def setUp(self):
        self.client = WsgiTestClient(webapp.app)

    def test_reporter_is_loaded_before_every_other_app_script(self):
        for route in ("/tasks", "/admin-dashboard"):
            status, html = self.client.request_text("GET", route)
            self.assertEqual(status, 200)
            reporter_at = html.index("/app-error-reporter.js")
            for other in ("/app-api.js", "/app-state.js", "/app.js"):
                with self.subTest(route=route, other=other):
                    self.assertLess(reporter_at, html.index(other), f"{other} loads before the error reporter")

    def test_reporter_has_no_app_dependencies(self):
        path = os.path.join(os.path.dirname(__file__), "..", "web", "app-error-reporter.js")
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("addEventListener('error'", source)
        self.assertIn("unhandledrejection", source)

        # Strip comments so the file's own prose about being dependency-free
        # does not satisfy the check it describes.
        code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
        self.assertNotIn("ManuscriptApi", code, "the beacon must work even when the API client failed to load")
        self.assertNotIn("ManuscriptEditorApp", code)

    def test_admin_error_panel_renders_on_every_shell(self):
        for route in ("/tasks", "/admin-dashboard"):
            status, html = self.client.request_text("GET", route)
            self.assertEqual(status, 200)
            for marker in ("admin-errors-body", "admin-refresh-errors-btn", "admin-purge-errors-btn", "/admin/errors.js"):
                with self.subTest(route=route, marker=marker):
                    self.assertIn(marker, html)


if __name__ == "__main__":
    unittest.main()
