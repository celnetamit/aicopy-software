import io
import json
import os
import tempfile
import unittest
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
local_tmp = os.path.join(ROOT_DIR, "data", "tmp")
os.makedirs(local_tmp, exist_ok=True)
tempfile.tempdir = local_tmp

os.environ.setdefault("MANUSCRIPT_EDITOR_DEV_TEST_TOKENS", "1")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(ROOT_DIR, 'data', 'manuscript_editor_test.sqlite3')}")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")

import webapp


class WsgiTestClient:
    def __init__(self, app):
        self.app = app
        self.cookies = {}

    def request(self, method, path, payload=None, query=None):
        body = b""
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        environ = {}
        setup_testing_defaults(environ)
        environ["REQUEST_METHOD"] = method.upper()

        path_info = path
        query_string = ""
        if "?" in path:
            path_info, query_string = path.split("?", 1)
        if query:
            encoded = urlencode(query)
            query_string = f"{query_string}&{encoded}" if query_string else encoded

        environ["PATH_INFO"] = path_info
        environ["QUERY_STRING"] = query_string
        environ["CONTENT_LENGTH"] = str(len(body))
        environ["wsgi.input"] = io.BytesIO(body)
        if body:
            environ["CONTENT_TYPE"] = "application/json"

        if self.cookies:
            environ["HTTP_COOKIE"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())

        meta = {}

        def start_response(status, headers, exc_info=None):
            meta["status"] = status
            meta["headers"] = headers

        result = self.app(environ, start_response)
        response_body = b"".join(result)
        if hasattr(result, "close"):
            result.close()

        for header_name, header_value in meta.get("headers", []):
            if header_name.lower() != "set-cookie":
                continue
            cookie_pair = header_value.split(";", 1)[0]
            cookie_name, cookie_value = cookie_pair.split("=", 1)
            self.cookies[cookie_name] = cookie_value

        data = json.loads(response_body.decode("utf-8") or "{}")
        status_code = int(str(meta.get("status", "500")).split(" ", 1)[0])
        return status_code, data


class AdminJournalsApiTests(unittest.TestCase):
    def setUp(self):
        webapp._STORE.clear_all_for_tests()
        self.client = WsgiTestClient(webapp.app)

    def _login(self, email):
        status, payload = self.client.request("POST", "/api/auth/google-login", {"id_token": f"test:{email}"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

    def test_admin_journal_crud_and_task_recommendations(self):
        self._login("amit@conwiz.in")

        status, payload = self.client.request("POST", "/api/admin/journals", {
            "name": "Clinical Cardio Journal",
            "scope": "cardiology clinical outcomes",
            "keywords": ["cardiology", "heart", "clinical"],
            "subject_areas": ["Cardiology"],
            "article_types": ["clinical trial"],
            "quartile": "Q1",
            "open_access": True,
        })
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        journal_id = payload["journal"]["id"]

        status, payload = self.client.request("GET", "/api/admin/journals")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("journals"))

        status, payload = self.client.request("PUT", f"/api/admin/journals/{journal_id}", {"publisher": "STM House"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["journal"].get("publisher"), "STM House")

        status, upload = self.client.request("POST", "/api/tasks/upload-text", {
            "file_name": "m1.txt",
            "content": "A cardiology clinical trial manuscript with heart outcome analysis and cohort validation."
        })
        self.assertEqual(status, 200)
        task_id = upload.get("task_id")

        status, process = self.client.request("POST", f"/api/tasks/{task_id}/process", {
            "options": {
                "online_reference_validation": False,
                "online_reference_serper_fallback": False,
                "auto_resolve_unresolved_references": False,
                "ai": {"enabled": False}
            }
        })
        self.assertEqual(status, 200)
        self.assertTrue(process.get("success"))
        self.assertIn("journal_recommendations", process)

        status, task = self.client.request("GET", f"/api/tasks/{task_id}")
        self.assertEqual(status, 200)
        reports = task.get("task", {}).get("reports", {})
        self.assertIn("journal_recommendations", reports)

        status, payload = self.client.request("DELETE", f"/api/admin/journals/{journal_id}")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

    def test_non_admin_cannot_access(self):
        self._login("user@conwiz.in")
        status, _ = self.client.request("GET", "/api/admin/journals")
        self.assertEqual(status, 403)

    def test_admin_journal_import_export_csv(self):
        self._login("amit@conwiz.in")
        csv_text = (
            "Name,Category,Submission URL,Focus & Scope,Keywords,Primary Domains\n"
            "\"Import Journal\",Computer/IT,https://submit.example,\"AI and systems\",\"ai,ml,systems\",\"Artificial Intelligence, Systems\"\n"
        )
        status, payload = self.client.request("POST", "/api/admin/journals/import", {"csv_text": csv_text})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertGreaterEqual(int(payload.get("created") or 0), 1)

        status, payload = self.client.request("GET", "/api/admin/journals/export")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertIn("csv_text", payload)
        self.assertIn("Import Journal", str(payload.get("csv_text") or ""))


if __name__ == "__main__":
    unittest.main()
