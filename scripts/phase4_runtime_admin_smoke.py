#!/usr/bin/env python3
"""Phase 4 smoke checks for admin/runtime wiring and async task-run lifecycle."""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import tempfile
local_tmp = os.path.join(ROOT_DIR, "data", "tmp")
os.makedirs(local_tmp, exist_ok=True)
tempfile.tempdir = local_tmp

os.environ.setdefault("MANUSCRIPT_EDITOR_DEV_TEST_TOKENS", "1")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(ROOT_DIR, 'data', 'manuscript_editor_smoke.sqlite3')}")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import webapp  # noqa: E402


class WsgiTestClient:
    def __init__(self, app):
        self.app = app
        self.cookies = {}

    def request(self, method: str, path: str, payload: Dict | None = None, query: Dict | None = None):
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
        environ["wsgi.input"] = __import__("io").BytesIO(body)
        if body:
            environ["CONTENT_TYPE"] = "application/json"
        if self.cookies:
            environ["HTTP_COOKIE"] = "; ".join(f"{key}={value}" for key, value in self.cookies.items())

        meta = {}

        def start_response(status, headers, exc_info=None):
            meta["status"] = status
            meta["headers"] = headers

        result = self.app(environ, start_response)
        response_body = b"".join(result)
        if hasattr(result, "close"):
            result.close()

        for header_name, header_value in meta.get("headers", []):
            if str(header_name).lower() != "set-cookie":
                continue
            cookie_pair = header_value.split(";", 1)[0]
            cookie_name, cookie_value = cookie_pair.split("=", 1)
            self.cookies[cookie_name] = cookie_value

        status_code = int(str(meta.get("status", "500")).split(" ", 1)[0])
        text = response_body.decode("utf-8") if response_body else ""
        data = json.loads(text) if text else {}
        return status_code, data


def fail(message: str) -> int:
    print(f"[FAIL] {message}")
    return 1


def assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def login(client: WsgiTestClient, email: str):
    status, payload = client.request("POST", "/api/auth/google-login", {"id_token": f"test:{email}"})
    assert_true(status == 200 and payload.get("success"), f"Login failed for {email}: {status} {payload}")


def main() -> int:
    try:
        webapp._STORE.clear_all_for_tests()

        admin = WsgiTestClient(webapp.app)
        login(admin, "amit@conwiz.in")

        status, payload = admin.request("GET", "/api/admin/global-settings")
        assert_true(status == 200 and payload.get("success"), f"admin global-settings read failed: {status} {payload}")

        updated = {
            "editing": {
                "editing_mode": "clarity",
                "tone": "business",
                "rewrite_strength": "moderate",
                "explain_edits": True,
                "domain_profile": "engineering",
            },
            "ai": {
                "enabled": False,
                "provider": "ollama",
                "model": "llama3.1",
                "ollama_host": "http://localhost:11434",
            },
        }
        status, payload = admin.request("POST", "/api/admin/global-settings", {"settings": updated})
        assert_true(status == 200 and payload.get("success"), f"admin global-settings update failed: {status} {payload}")

        user = WsgiTestClient(webapp.app)
        login(user, "writer@conwiz.in")

        status, payload = user.request("GET", "/api/settings/runtime")
        assert_true(status == 200 and payload.get("success"), f"runtime settings fetch failed: {status} {payload}")
        editing = (payload.get("settings") or {}).get("editing") or {}
        assert_true(editing.get("editing_mode") == "clarity", f"editing_mode mismatch: {editing.get('editing_mode')}")
        assert_true(editing.get("tone") == "business", f"tone mismatch: {editing.get('tone')}")
        assert_true(editing.get("rewrite_strength") == "moderate", f"rewrite_strength mismatch: {editing.get('rewrite_strength')}")
        assert_true(bool(editing.get("explain_edits")) is True, f"explain_edits mismatch: {editing.get('explain_edits')}")

        status, payload = user.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "smoke.txt", "content": "This are smoke test sentence."},
        )
        assert_true(status == 200 and payload.get("success"), f"upload failed: {status} {payload}")
        task_id = str(payload.get("task_id") or "")
        assert_true(bool(task_id), "task_id missing after upload")

        status, payload = user.request(
            "POST",
            f"/api/tasks/{task_id}/process",
            {"async": True, "options": {"ai": {"enabled": False}}},
        )
        assert_true(status == 202 and payload.get("success") and payload.get("queued"), f"async process queue failed: {status} {payload}")
        task_run = payload.get("task_run") or {}
        assert_true(bool(task_run.get("id")), f"task_run missing in async response: {payload}")

        deadline = time.time() + 30
        last_status = ""
        while time.time() < deadline:
            status, payload = user.request("GET", f"/api/tasks/{task_id}/process-status")
            assert_true(status == 200 and payload.get("success"), f"process-status failed: {status} {payload}")
            run = payload.get("task_run") or {}
            assert_true(bool(run.get("id")), "task_run missing in process-status response")
            last_status = str(run.get("status") or "")
            if last_status in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(0.5)

        assert_true(last_status == "SUCCEEDED", f"async run did not succeed, final status={last_status}")
        print("[OK] Phase 4 runtime/admin smoke checks passed.")
        return 0
    except Exception as exc:  # pragma: no cover - script guard
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
