"""WSGI tests for authenticated Manuscript Editor web app."""

import base64
import io
import json
import math
import os
import tempfile
import time
import unittest
import zipfile
from unittest.mock import Mock, patch
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

from docx import Document

from chicago_editor import ChicagoEditor


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
local_tmp = os.path.join(ROOT_DIR, "data", "tmp")
os.makedirs(local_tmp, exist_ok=True)
tempfile.tempdir = local_tmp

os.environ.setdefault("MANUSCRIPT_EDITOR_DEV_TEST_TOKENS", "1")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(ROOT_DIR, 'data', 'manuscript_editor_test.sqlite3')}")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")

import webapp  # noqa: E402


class WsgiTestClient:
    def __init__(self, app):
        self.app = app
        self.cookies = {}

    def request(self, method, path, payload=None, query=None, headers=None):
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
            environ["HTTP_COOKIE"] = "; ".join(f"{key}={value}" for key, value in self.cookies.items())

        if headers:
            for raw_name, raw_value in headers.items():
                if raw_name is None or raw_value is None:
                    continue
                name = str(raw_name).strip()
                if not name:
                    continue
                key = name.upper().replace("-", "_")
                if key not in ("CONTENT_TYPE", "CONTENT_LENGTH") and not key.startswith("HTTP_"):
                    key = "HTTP_" + key
                environ[key] = str(raw_value)

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

        text = response_body.decode("utf-8") if response_body else ""
        data = json.loads(text) if text else {}
        status_code = int(str(meta.get("status", "500")).split(" ", 1)[0])
        return status_code, data

    def request_text(self, method, path, payload=None, query=None, headers=None):
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
            environ["HTTP_COOKIE"] = "; ".join(f"{key}={value}" for key, value in self.cookies.items())

        if headers:
            for raw_name, raw_value in headers.items():
                if raw_name is None or raw_value is None:
                    continue
                name = str(raw_name).strip()
                if not name:
                    continue
                key = name.upper().replace("-", "_")
                if key not in ("CONTENT_TYPE", "CONTENT_LENGTH") and not key.startswith("HTTP_"):
                    key = "HTTP_" + key
                environ[key] = str(raw_value)

        meta = {}

        def start_response(status, headers, exc_info=None):
            meta["status"] = status
            meta["headers"] = headers

        result = self.app(environ, start_response)
        response_body = b"".join(result)
        if hasattr(result, "close"):
            result.close()

        status_code = int(str(meta.get("status", "500")).split(" ", 1)[0])
        text = response_body.decode("utf-8") if response_body else ""
        return status_code, text

    def request_bytes(self, method, path, payload=None, query=None, headers=None):
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
            environ["HTTP_COOKIE"] = "; ".join(f"{key}={value}" for key, value in self.cookies.items())

        if headers:
            for raw_name, raw_value in headers.items():
                if raw_name is None or raw_value is None:
                    continue
                name = str(raw_name).strip()
                if not name:
                    continue
                key = name.upper().replace("-", "_")
                if key not in ("CONTENT_TYPE", "CONTENT_LENGTH") and not key.startswith("HTTP_"):
                    key = "HTTP_" + key
                environ[key] = str(raw_value)

        meta = {}

        def start_response(status, headers, exc_info=None):
            meta["status"] = status
            meta["headers"] = headers

        result = self.app(environ, start_response)
        response_body = b"".join(result)
        if hasattr(result, "close"):
            result.close()

        status_code = int(str(meta.get("status", "500")).split(" ", 1)[0])
        headers_dict = {str(k).lower(): str(v) for k, v in meta.get("headers", [])}
        return status_code, response_body, headers_dict


class AuthenticatedWebAppApiTests(unittest.TestCase):
    def setUp(self):
        webapp._STORE.clear_all_for_tests()
        with ChicagoEditor._SHARED_ONLINE_VALIDATION_CACHE_LOCK:
            ChicagoEditor._SHARED_ONLINE_VALIDATION_CACHE.clear()
        with ChicagoEditor._SHARED_ONLINE_LOOKUP_METRICS_LOCK:
            ChicagoEditor._SHARED_ONLINE_LOOKUP_METRICS = ChicagoEditor._default_online_lookup_metrics()
            ChicagoEditor._SHARED_ONLINE_LOOKUP_METRICS_UPDATED_AT = 0
        self.client = WsgiTestClient(webapp.app)
        self._old_local_login_enabled = webapp.ENABLE_LOCAL_MANUAL_LOGIN

    def tearDown(self):
        webapp.ENABLE_LOCAL_MANUAL_LOGIN = self._old_local_login_enabled

    def _login(self, email="user@conwiz.in"):
        status, payload = self.client.request(
            "POST",
            "/api/auth/google-login",
            {"id_token": f"test:{email}"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertIn("user", payload)
        return payload["user"]

    @staticmethod
    def _offline_processing_options():
        """Stable process options for local endpoint tests without network calls."""
        return {
            "spelling": True,
            "sentence_case": True,
            "punctuation": True,
            "chicago_style": True,
            "online_reference_validation": False,
            "online_reference_serper_fallback": False,
            "auto_resolve_unresolved_references": False,
            "ai": {"enabled": False},
        }

    @staticmethod
    def _force_offline_runtime_settings():
        runtime = webapp._read_global_runtime_settings()
        editing = runtime.get("editing") if isinstance(runtime.get("editing"), dict) else {}
        editing = dict(editing)
        editing["online_reference_validation"] = False
        editing["online_reference_serper_fallback"] = False
        editing["auto_resolve_unresolved_references"] = False
        runtime["editing"] = editing
        ai = runtime.get("ai") if isinstance(runtime.get("ai"), dict) else {}
        ai = dict(ai)
        ai["enabled"] = False
        runtime["ai"] = ai
        normalized = webapp._normalize_global_runtime_settings(runtime)
        webapp._STORE.upsert_app_setting(
            key=webapp.APP_SETTING_KEY_GLOBAL_RUNTIME,
            value=normalized,
            updated_by_user_id="",
        )

    def test_blocked_domain_cannot_login(self):
        status, payload = self.client.request(
            "POST",
            "/api/auth/google-login",
            {"id_token": "test:blocked@example.com"},
        )
        self.assertEqual(status, 403)
        self.assertFalse(payload.get("success"))
        self.assertEqual(payload.get("error_code"), "AUTH_DOMAIN_BLOCKED")

    def test_auth_me_requires_login_then_succeeds(self):
        status, payload = self.client.request("GET", "/api/auth/me")
        self.assertEqual(status, 401)
        self.assertFalse(payload.get("success"))

        user = self._login("staff@conwiz.in")
        status, payload = self.client.request("GET", "/api/auth/me")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload["user"]["email"], "staff@conwiz.in")
        self.assertEqual(payload["user"]["role"], user["role"])

    def test_local_manual_login_disabled_by_default(self):
        status, payload = self.client.request(
            "POST",
            "/api/auth/local-login",
            {"username": "admin", "password": "password"},
        )
        self.assertEqual(status, 403)
        self.assertFalse(payload.get("success"))
        self.assertEqual(payload.get("error_code"), "AUTH_LOCAL_LOGIN_DISABLED")

    def test_local_manual_login_succeeds_when_enabled(self):
        webapp.ENABLE_LOCAL_MANUAL_LOGIN = True
        status, payload = self.client.request(
            "POST",
            "/api/auth/local-login",
            {"username": "admin", "password": "password"},
            headers={"X-Forwarded-For": "127.0.0.1"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload["user"]["role"], "ADMIN")

        status, payload = self.client.request("GET", "/api/auth/me")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload["user"]["role"], "ADMIN")

    def test_admin_dashboard_route_renders_admin_shell(self):
        status, html = self.client.request_text("GET", "/admin-dashboard")
        self.assertEqual(status, 200)
        self.assertIn('id="admin-panel-backdrop"', html)
        self.assertIn('admin-dashboard-active', html)
        self.assertIn('class="setup-wizard-backdrop" id="admin-panel-backdrop"', html)
        self.assertNotIn('class="setup-wizard-backdrop hidden" id="admin-panel-backdrop"', html)
        self.assertNotIn("{{", html)

    def test_root_redirects_to_tasks_dashboard(self):
        environ = {}
        setup_testing_defaults(environ)
        environ["REQUEST_METHOD"] = "GET"
        environ["PATH_INFO"] = "/"
        meta = {}

        def start_response(status, headers, exc_info=None):
            meta["status"] = status
            meta["headers"] = headers

        result = webapp.app(environ, start_response)
        body = b"".join(result)
        if hasattr(result, "close"):
            result.close()

        self.assertEqual(int(str(meta.get("status", "500")).split(" ", 1)[0]), 302)
        headers = dict(meta.get("headers", []))
        self.assertEqual(headers.get("Location"), "/tasks")
        self.assertEqual(body, b"")

    def test_tasks_dashboard_route_renders_dashboard_shell(self):
        status, html = self.client.request_text("GET", "/tasks")
        self.assertEqual(status, 200)
        self.assertIn('class="tasks-dashboard-route"', html)
        self.assertIn("<title>Manuscript Editor - Tasks</title>", html)
        self.assertIn("Task Dashboard", html)
        self.assertNotIn('id="preview-text"', html)
        self.assertNotIn('id="process-btn"', html)
        self.assertNotIn("{{", html)

    def test_task_detail_route_renders_task_detail_shell(self):
        status, html = self.client.request_text("GET", "/tasks/example-task-id")
        self.assertEqual(status, 200)
        self.assertIn('class="task-detail-route"', html)
        self.assertIn('data-task-route-id="example-task-id"', html)
        self.assertIn("<title>Manuscript Editor - Task Detail</title>", html)
        self.assertLess(html.index("/app-api.js"), html.index("/eel.js"))
        self.assertIn("/pages/task-detail.js", html)
        self.assertIn('id="preview-text"', html)
        self.assertIn('id="process-btn"', html)
        self.assertIn('id="admin-setting-online-reference-validation-admin-cap"', html)
        self.assertIn('id="admin-setting-auto-resolve-unresolved-references"', html)
        self.assertNotIn("{{", html)

    def test_task_detail_rerun_unresolved_button_has_safe_label_and_tooltip(self):
        status, html = self.client.request_text("GET", "/tasks/example-task-id")
        self.assertEqual(status, 200)
        self.assertIn('id="rerun-unresolved-btn"', html)
        self.assertIn("Rerun Unresolved Refs (Safe)", html)
        self.assertIn("Rerun only unresolved references using safe settings", html)
        self.assertIn('id="assistant-unresolved-panel"', html)
        self.assertIn('id="assistant-unresolved-sort"', html)
        self.assertIn('id="assistant-unresolved-rerun-btn"', html)
        self.assertIn('id="assistant-unresolved-rerun-autofixable-btn"', html)
        self.assertIn('id="assistant-export-unresolved-btn"', html)
        self.assertIn('id="assistant-prompt-panel"', html)
        self.assertIn('data-assistant-prompt="next_step"', html)
        self.assertIn('data-assistant-prompt="export"', html)
        self.assertIn('id="assistant-guided-action-card"', html)
        self.assertIn('id="assistant-guided-run-btn"', html)
        self.assertNotIn("{{ASSISTANT_PANEL_FRAGMENT}}", html)

    def test_admin_dashboard_contains_new_reference_automation_controls(self):
        status, html = self.client.request_text("GET", "/admin-dashboard")
        self.assertEqual(status, 200)
        self.assertIn('id="admin-setting-online-reference-validation-admin-cap"', html)
        self.assertIn('id="admin-setting-auto-resolve-unresolved-references"', html)
        self.assertIn('id="admin-setting-ollama-generate-timeout-seconds"', html)
        self.assertIn('id="admin-setting-ollama-health-timeout-seconds"', html)
        self.assertIn('id="admin-setting-ollama-retry-count"', html)
        self.assertIn('id="admin-setting-ollama-retry-backoff-seconds"', html)
        self.assertIn('id="admin-setting-ollama-fallback-model-retry"', html)
        self.assertIn('id="admin-reference-unresolved-trend-summary"', html)
        self.assertIn('id="admin-reference-diagnostics-trends-output"', html)

    def test_version_endpoint_and_footer_use_shared_version_source(self):
        version_file = os.path.join(os.path.dirname(__file__), "..", "VERSION")
        with open(version_file, "r", encoding="utf-8") as handle:
            expected_version = handle.read().strip()
        self.assertTrue(expected_version)

        status, payload = self.client.request("GET", "/api/version")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("version"), expected_version)
        self.assertEqual(payload.get("asset_version"), f"v{expected_version}")

        status, html = self.client.request_text("GET", "/tasks/example-task-id")
        self.assertEqual(status, 200)
        self.assertIn(f"v{expected_version}", html)

    def test_packaging_defaults_read_shared_version_file(self):
        version_file = os.path.join(os.path.dirname(__file__), "..", "VERSION")
        with open(version_file, "r", encoding="utf-8") as handle:
            expected_version = handle.read().strip()
        self.assertTrue(expected_version)

        linux_script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "linux", "build_deb.sh")
        with open(linux_script_path, "r", encoding="utf-8") as handle:
            linux_script = handle.read()
        self.assertIn('DEFAULT_VERSION="$(tr -d', linux_script)
        self.assertIn('${ROOT_DIR}/VERSION', linux_script)
        self.assertIn('VERSION="${1:-${DEFAULT_VERSION}}"', linux_script)

        windows_iss_path = os.path.join(os.path.dirname(__file__), "..", "packaging", "windows", "ManuscriptEditor.iss")
        with open(windows_iss_path, "r", encoding="utf-8") as handle:
            windows_iss = handle.read()
        self.assertIn('#define MyAppVersion Trim(FileRead("..\\..\\VERSION"))', windows_iss)
        self.assertIn("AppVersion={#MyAppVersion}", windows_iss)
        self.assertIn("OutputBaseFilename=ManuscriptEditor_Setup_{#MyAppVersion}", windows_iss)

        version_check_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "check_version_consistency.py")
        with open(version_check_path, "r", encoding="utf-8") as handle:
            version_check = handle.read()
        self.assertIn("version_info.APP_VERSION == version", version_check)
        self.assertIn("FileRead", version_check)
        self.assertIn("build_deb.sh 1.0.0", version_check)

    def test_dependency_lock_is_used_for_release_installs(self):
        root_dir = os.path.join(os.path.dirname(__file__), "..")
        lock_path = os.path.join(root_dir, "requirements.lock")
        with open(lock_path, "r", encoding="utf-8") as handle:
            lock_lines = [
                line.strip()
                for line in handle
                if line.strip() and not line.strip().startswith("#")
            ]

        self.assertIn("Eel==0.17.0", lock_lines)
        self.assertIn("python-docx==1.1.2", lock_lines)
        self.assertIn("requests==2.31.0", lock_lines)
        self.assertTrue(all("==" in line for line in lock_lines))

        with open(os.path.join(root_dir, "requirements-build.txt"), "r", encoding="utf-8") as handle:
            build_requirements = handle.read()
        self.assertIn("-r requirements.lock", build_requirements)
        self.assertNotIn("-r requirements.txt", build_requirements)

        with open(os.path.join(root_dir, "Dockerfile"), "r", encoding="utf-8") as handle:
            dockerfile = handle.read()
        self.assertIn("requirements.lock", dockerfile)
        self.assertIn("pip install -r requirements.lock", dockerfile)

        with open(os.path.join(root_dir, "scripts", "linux", "build_deb.sh"), "r", encoding="utf-8") as handle:
            deb_script = handle.read()
        self.assertIn("requirements.lock", deb_script)
        self.assertIn("DEPENDENCY_FILE", deb_script)

        with open(os.path.join(root_dir, "scripts", "run_quality_checks.sh"), "r", encoding="utf-8") as handle:
            quality_gate = handle.read()
        self.assertIn("scripts/check_dependency_lock.py", quality_gate)

    def test_reference_validation_diagnostics_includes_admin_cap_setting(self):
        self._login("admin@conwiz.in")
        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request(
            "POST",
            "/api/auth/google-login",
            {"id_token": "test:amit@conwiz.in"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        status, payload = admin_client.request("GET", "/api/admin/reference-validation-diagnostics")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        diagnostics = payload.get("diagnostics") or {}
        runtime = diagnostics.get("global_runtime") or {}
        self.assertIn("online_reference_validation_admin_cap", runtime)
        self.assertEqual(int(runtime.get("online_reference_validation_admin_cap", 0)), 150)
        self.assertIn("unresolved_trends", diagnostics)

    def test_rerun_unresolved_frontend_has_direct_process_fallback_path(self):
        assistant_js_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-assistant.js")
        with open(assistant_js_path, "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("rerun_unresolved_references_fallback", source)
        self.assertIn("assistant_reprocess_task", source)
        self.assertIn("api.tasks.process", source)
        self.assertIn("'process_document'", source)
        self.assertIn("Used direct fallback", source)
        self.assertIn("buildUnresolvedRerunDelta", source)
        self.assertIn("Unresolved references rerun complete. Before:", source)

    def test_corrections_panel_renders_rerun_unresolved_delta_chips(self):
        preview_js_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-preview.js")
        with open(preview_js_path, "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("Unresolved Delta:", source)
        self.assertIn("Rerun Regression:", source)
        self.assertIn("Unresolved reason:", source)

    def test_unresolved_references_panel_actions_are_wired(self):
        assistant_js_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-assistant.js")
        with open(assistant_js_path, "r", encoding="utf-8") as handle:
            assistant_source = handle.read()
        self.assertIn("collectUnresolvedReferenceItemsFromState", assistant_source)
        self.assertIn("exportUnresolvedReferencesReport", assistant_source)
        self.assertIn("unresolved_references_", assistant_source)

        settings_panel_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-settings-panel.js")
        with open(settings_panel_path, "r", encoding="utf-8") as handle:
            settings_panel_source = handle.read()
        self.assertIn("assistantUnresolvedRerunBtn", settings_panel_source)
        self.assertIn("assistantUnresolvedRerunAutofixableBtn", settings_panel_source)
        self.assertIn("assistantExportUnresolvedBtn", settings_panel_source)
        self.assertIn("assistantUnresolvedSort", settings_panel_source)
        self.assertIn("assistantQuickPromptButtons", settings_panel_source)
        self.assertIn("askAssistantQuickPrompt", settings_panel_source)

    def test_assistant_quick_prompts_are_wired(self):
        assistant_js_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-assistant.js")
        with open(assistant_js_path, "r", encoding="utf-8") as handle:
            assistant_source = handle.read()
        self.assertIn("getAssistantQuickPromptMessage", assistant_source)
        self.assertIn("What should I do next for this task?", assistant_source)
        self.assertIn("Is this task ready to export?", assistant_source)
        self.assertIn("askAssistantQuickPrompt", assistant_source)
        self.assertIn("prepareAssistantGuidedAction", assistant_source)
        self.assertIn("Review action card", assistant_source)

        assistant_fragment_path = os.path.join(os.path.dirname(__file__), "..", "web", "fragments", "assistant_panel.html")
        with open(assistant_fragment_path, "r", encoding="utf-8") as handle:
            assistant_fragment = handle.read()
        self.assertIn('id="assistant-prompt-panel"', assistant_fragment)
        self.assertIn('id="assistant-guided-action-card"', assistant_fragment)
        self.assertIn('id="assistant-unresolved-panel"', assistant_fragment)

    def test_frontend_api_client_is_loaded_and_bridge_uses_it(self):
        api_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-api.js")
        with open(api_path, "r", encoding="utf-8") as handle:
            api_source = handle.read()
        self.assertIn("window.ManuscriptApi", api_source)
        self.assertIn("requestJson", api_source)
        self.assertIn("admin:", api_source)
        self.assertIn("assistant:", api_source)
        self.assertIn("legacy:", api_source)
        self.assertIn("runtime:", api_source)

        bridge_path = os.path.join(os.path.dirname(__file__), "..", "web", "eel_web_bridge.js")
        with open(bridge_path, "r", encoding="utf-8") as handle:
            bridge_source = handle.read()
        self.assertIn("window.ManuscriptApi", bridge_source)
        self.assertIn("apiClient.getJson", bridge_source)
        self.assertIn("apiClient.postJson", bridge_source)
        self.assertNotIn("function responseToJson", bridge_source)

        auth_admin_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-auth-admin.js")
        with open(auth_admin_path, "r", encoding="utf-8") as handle:
            auth_admin_source = handle.read()
        self.assertIn("function callApiOrEel", auth_admin_source)
        self.assertIn("api.auth.googleLogin", auth_admin_source)
        self.assertIn("appAuth.adminGlobalSettings", auth_admin_source)
        self.assertIn("appAuth.adminReferenceDiagnostics", auth_admin_source)
        self.assertEqual(auth_admin_source.count("typeof eel !=="), 1)

        admin_global_path = os.path.join(os.path.dirname(__file__), "..", "web", "admin", "global-settings.js")
        with open(admin_global_path, "r", encoding="utf-8") as handle:
            admin_global_source = handle.read()
        self.assertIn("api.admin.globalSettings", admin_global_source)
        self.assertIn("api.admin.validateAiProvider", admin_global_source)

        api_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-api.js")
        with open(api_path, "r", encoding="utf-8") as handle:
            api_source = handle.read()
        self.assertIn("processStatus: function (taskId)", api_source)
        self.assertIn("async: Boolean(input.async)", api_source)

        admin_reference_path = os.path.join(os.path.dirname(__file__), "..", "web", "admin", "reference-diagnostics.js")
        with open(admin_reference_path, "r", encoding="utf-8") as handle:
            admin_reference_source = handle.read()
        self.assertIn("api.admin.referenceValidationDiagnostics", admin_reference_source)

        app_js_path = os.path.join(os.path.dirname(__file__), "..", "web", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as handle:
            app_source = handle.read()
        self.assertIn("function callApiOrEel", app_source)
        self.assertIn("api.tasks.uploadText", app_source)
        self.assertIn("api.tasks.process", app_source)
        self.assertIn("appMain.editorRuntime", app_source)
        self.assertIn("assistantAction('assistantReprocessCurrentTask')", app_source)
        self.assertIn("api.legacy.exportFile", app_source)
        self.assertEqual(app_source.count("typeof eel !=="), 1)

        assistant_js_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-assistant.js")
        with open(assistant_js_path, "r", encoding="utf-8") as handle:
            assistant_source = handle.read()
        self.assertIn("app.assistant = assistantActions", assistant_source)
        self.assertIn("api.assistant.reprocessTask", assistant_source)

        quality_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "run_quality_checks.sh")
        with open(quality_path, "r", encoding="utf-8") as handle:
            quality_source = handle.read()
        self.assertIn("python3 scripts/check_version_consistency.py", quality_source)
        self.assertIn("node --check web/app-api.js", quality_source)
        self.assertIn("node --check web/app-assistant.js", quality_source)
        self.assertIn("node --check web/app-auth-admin.js", quality_source)
        self.assertIn("node --check web/app-router.js", quality_source)
        self.assertIn("node --check web/app-settings.js", quality_source)
        self.assertIn("node --check web/app-settings-panel.js", quality_source)
        self.assertIn("node --check web/admin/runtime.js", quality_source)
        self.assertIn("node --check web/admin/audit.js", quality_source)
        self.assertIn("node --check web/admin/users.js", quality_source)
        self.assertIn("node --check web/admin/global-settings.js", quality_source)
        self.assertIn("node --check web/admin/reference-diagnostics.js", quality_source)
        self.assertIn("node --check web/admin/panel.js", quality_source)
        self.assertIn("node --check web/pages/tasks.js", quality_source)
        self.assertIn("node --check web/pages/task-detail.js", quality_source)

    def test_route_specific_page_modules_are_loaded_and_own_page_controls(self):
        status, tasks_html = self.client.request_text("GET", "/tasks")
        self.assertEqual(status, 200)
        self.assertIn('class="tasks-dashboard-route"', tasks_html)
        self.assertIn("/pages/tasks.js", tasks_html)
        self.assertIn("/pages/task-detail.js", tasks_html)
        self.assertIn("/app-settings-panel.js", tasks_html)
        self.assertIn("/admin/runtime.js", tasks_html)
        self.assertIn("/admin/audit.js", tasks_html)
        self.assertIn("/admin/users.js", tasks_html)
        self.assertIn("/admin/global-settings.js", tasks_html)
        self.assertIn("/admin/reference-diagnostics.js", tasks_html)
        self.assertIn("/admin/panel.js", tasks_html)
        self.assertIn("/app-assistant.js", tasks_html)
        self.assertIn('id="assistant-guided-action-card"', tasks_html)
        self.assertNotIn("{{ASSISTANT_PANEL_FRAGMENT}}", tasks_html)
        self.assertLess(tasks_html.index("/app-auth-admin.js"), tasks_html.index("/admin/runtime.js"))
        self.assertLess(tasks_html.index("/admin/runtime.js"), tasks_html.index("/admin/audit.js"))
        self.assertLess(tasks_html.index("/admin/audit.js"), tasks_html.index("/admin/users.js"))
        self.assertLess(tasks_html.index("/admin/users.js"), tasks_html.index("/admin/global-settings.js"))
        self.assertLess(tasks_html.index("/admin/global-settings.js"), tasks_html.index("/admin/reference-diagnostics.js"))
        self.assertLess(tasks_html.index("/admin/reference-diagnostics.js"), tasks_html.index("/admin/panel.js"))
        self.assertLess(tasks_html.index("/admin/panel.js"), tasks_html.index("/app-preview.js"))
        self.assertLess(tasks_html.index("/app-settings.js"), tasks_html.index("/app-settings-panel.js"))
        self.assertLess(tasks_html.index("/app-settings-panel.js"), tasks_html.index("/pages/tasks.js"))
        self.assertLess(tasks_html.index("/pages/tasks.js"), tasks_html.index("/app.js"))
        self.assertLess(tasks_html.index("/app.js"), tasks_html.index("/app-assistant.js"))
        self.assertLess(tasks_html.index("/app-assistant.js"), tasks_html.index("/app-router.js"))

        tasks_page_path = os.path.join(os.path.dirname(__file__), "..", "web", "pages", "tasks.js")
        with open(tasks_page_path, "r", encoding="utf-8") as handle:
            tasks_page_source = handle.read()
        self.assertIn("root.pages.tasks", tasks_page_source)
        self.assertIn("root.authAdmin", tasks_page_source)
        self.assertIn("isTasksDashboardRoute", tasks_page_source)
        self.assertIn("bindUploadControls", tasks_page_source)
        self.assertIn("renderTaskHistory", tasks_page_source)
        self.assertIn("bindTaskHistoryNavigation", tasks_page_source)
        self.assertIn("auth.navigateToTask", tasks_page_source)
        self.assertIn("handleSelectedFile", tasks_page_source)

        detail_page_path = os.path.join(os.path.dirname(__file__), "..", "web", "pages", "task-detail.js")
        with open(detail_page_path, "r", encoding="utf-8") as handle:
            detail_page_source = handle.read()
        self.assertIn("root.pages.taskDetail", detail_page_source)
        self.assertIn("root.authAdmin", detail_page_source)
        self.assertIn("isDetailWorkspaceRoute", detail_page_source)
        self.assertIn("bindEditorControls", detail_page_source)
        self.assertIn("bindPreviewControls", detail_page_source)
        self.assertIn("hydrateCurrentRouteTaskIfNeeded", detail_page_source)
        self.assertIn("bootstrapEditorSurface", detail_page_source)
        self.assertIn("handlePageShow", detail_page_source)
        self.assertIn("renderRunStagesFromState", detail_page_source)

        settings_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-settings.js")
        with open(settings_path, "r", encoding="utf-8") as handle:
            settings_source = handle.read()
        self.assertIn("appSettingsRoot.settings", settings_source)
        self.assertIn("syncReferenceValidationToggleState", settings_source)
        self.assertNotIn("function bindSettingsEvents", settings_source)
        self.assertNotIn("addEventListener", settings_source)
        self.assertNotIn("settingsDom.dropZone.addEventListener('drop'", settings_source)
        self.assertNotIn("settingsDom.processBtn.addEventListener", settings_source)
        self.assertNotIn("document.querySelectorAll('.tab[data-tab]')", settings_source)

        settings_panel_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-settings-panel.js")
        with open(settings_panel_path, "r", encoding="utf-8") as handle:
            settings_panel_source = handle.read()
        self.assertIn("root.settingsPanel", settings_panel_source.replace("appSettingsPanelRoot.", "root."))
        self.assertIn("bindAiProviderEvents", settings_panel_source)
        self.assertIn("settingsPanelDom.aiProvider.addEventListener", settings_panel_source)
        self.assertIn("bindAdminPanelEvents", settings_panel_source)
        self.assertIn("bindAssistantPanelEvents", settings_panel_source)

        auth_admin_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-auth-admin.js")
        with open(auth_admin_path, "r", encoding="utf-8") as handle:
            auth_admin_source = handle.read()
        self.assertIn("appAuth.pages.tasks", auth_admin_source)
        self.assertIn("appAuth.pages.taskDetail", auth_admin_source)
        self.assertIn("appAuth.adminRuntime", auth_admin_source)
        self.assertIn("appAuth.adminUsers", auth_admin_source)
        self.assertIn("appAuth.adminAudit", auth_admin_source)
        self.assertIn("appAuth.adminGlobalSettings", auth_admin_source)
        self.assertIn("appAuth.adminReferenceDiagnostics", auth_admin_source)
        self.assertIn("appAuth.adminPanel", auth_admin_source)
        self.assertNotIn("taskHistoryEl.querySelectorAll('.task-history-item", auth_admin_source)
        self.assertNotIn("api.admin.globalSettings", auth_admin_source)
        self.assertNotIn("api.admin.referenceValidationDiagnostics", auth_admin_source)
        self.assertNotIn("api.admin.validateAiProvider", auth_admin_source)

        admin_runtime_path = os.path.join(os.path.dirname(__file__), "..", "web", "admin", "runtime.js")
        with open(admin_runtime_path, "r", encoding="utf-8") as handle:
            admin_runtime_source = handle.read()
        self.assertIn("appAdminRuntimeRoot.adminRuntime", admin_runtime_source)
        self.assertIn("refreshRuntimeSettings", admin_runtime_source)
        self.assertIn("buildProcessingOptionsFromRuntimeSettings", admin_runtime_source)

        admin_users_path = os.path.join(os.path.dirname(__file__), "..", "web", "admin", "users.js")
        with open(admin_users_path, "r", encoding="utf-8") as handle:
            admin_users_source = handle.read()
        self.assertIn("appAdminUsersRoot.adminUsers", admin_users_source)
        self.assertIn("renderAdminUsers", admin_users_source)
        self.assertIn("updateAdminUserStatus", admin_users_source)

        admin_audit_path = os.path.join(os.path.dirname(__file__), "..", "web", "admin", "audit.js")
        with open(admin_audit_path, "r", encoding="utf-8") as handle:
            admin_audit_source = handle.read()
        self.assertIn("appAdminAuditRoot.adminAudit", admin_audit_source)
        self.assertIn("renderAdminAudit", admin_audit_source)
        self.assertIn("refreshAdminAudit", admin_audit_source)

        admin_global_path = os.path.join(os.path.dirname(__file__), "..", "web", "admin", "global-settings.js")
        with open(admin_global_path, "r", encoding="utf-8") as handle:
            admin_global_source = handle.read()
        self.assertIn("appAdminGlobalRoot.adminGlobalSettings", admin_global_source)
        self.assertIn("loadAdminGlobalSettings", admin_global_source)
        self.assertIn("validateAdminAiProvider", admin_global_source)
        self.assertIn("api.admin.globalSettings", admin_global_source)

        admin_reference_path = os.path.join(os.path.dirname(__file__), "..", "web", "admin", "reference-diagnostics.js")
        with open(admin_reference_path, "r", encoding="utf-8") as handle:
            admin_reference_source = handle.read()
        self.assertIn("appAdminReferenceRoot.adminReferenceDiagnostics", admin_reference_source)
        self.assertIn("refreshAdminReferenceValidationDiagnostics", admin_reference_source)
        self.assertIn("resetAdminReferenceValidationDiagnostics", admin_reference_source)
        self.assertIn("api.admin.referenceValidationDiagnostics", admin_reference_source)

        admin_panel_path = os.path.join(os.path.dirname(__file__), "..", "web", "admin", "panel.js")
        with open(admin_panel_path, "r", encoding="utf-8") as handle:
            admin_panel_source = handle.read()
        self.assertIn("appAdminPanelRoot.adminPanel", admin_panel_source)
        self.assertIn("openAdminPanel", admin_panel_source)
        self.assertIn("renderAdminDocxStructureSummary", admin_panel_source)

        app_js_path = os.path.join(os.path.dirname(__file__), "..", "web", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as handle:
            app_source = handle.read()
        self.assertNotIn("mainAuth.checkAuthenticatedUser();", app_source)
        self.assertIn("api.tasks.process(taskId, options, { async: true })", app_source)
        self.assertIn("api.tasks.processStatus(safeTaskId)", app_source)
        self.assertIn("completeTrackedProcessingFromPayload", app_source)
        self.assertIn("response.success && response.queued", app_source)

        router_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-router.js")
        with open(router_path, "r", encoding="utf-8") as handle:
            router_source = handle.read()
        self.assertIn("root.router", router_source)
        self.assertIn("function getRouteName", router_source)
        self.assertIn("initRouteModules", router_source)
        self.assertIn("bootstrapRouteSurface", router_source)
        self.assertIn("taskDetailPage.bootstrapEditorSurface", router_source)
        self.assertIn("callAuth('checkAuthenticatedUser')", router_source)
        self.assertIn("window.addEventListener('pageshow', handlePageShow)", router_source)

    def test_json_response_sanitizes_non_finite_numbers(self):
        response = webapp._json_response({"value": math.nan, "nested": {"score": math.inf}})
        payload = json.loads(response.body)
        self.assertIsNone(payload["value"])
        self.assertIsNone(payload["nested"]["score"])

    def test_request_options_override_global_runtime_ai_flags(self):
        runtime = webapp._normalize_global_runtime_settings(
            {
                "editing": {
                    "online_reference_validation": True,
                    "online_reference_serper_fallback": True,
                    "auto_resolve_unresolved_references": True,
                },
                "ai": {
                    "enabled": True,
                    "provider": "ollama",
                    "model": "llama3.1",
                    "section_wise": True,
                },
            }
        )
        request_options = {
            "online_reference_validation": False,
            "online_reference_serper_fallback": False,
            "auto_resolve_unresolved_references": False,
            "ai": {
                "enabled": False,
                "provider": "gemini",
                "model": "gemini-1.5-flash",
                "section_wise": False,
            },
        }

        merged = webapp._apply_global_runtime_settings(request_options, runtime)

        self.assertFalse(bool(merged.get("online_reference_validation")))
        self.assertFalse(bool(merged.get("online_reference_serper_fallback")))
        self.assertFalse(bool(merged.get("auto_resolve_unresolved_references")))
        self.assertFalse(bool((merged.get("ai") or {}).get("enabled")))
        self.assertEqual(str((merged.get("ai") or {}).get("provider")), "gemini")
        self.assertEqual(str((merged.get("ai") or {}).get("model")), "gemini-1.5-flash")
        self.assertFalse(bool((merged.get("ai") or {}).get("section_wise")))

    def test_upload_process_and_download_round_trip(self):
        self._force_offline_runtime_settings()
        self._login("writer@conwiz.in")

        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "sample.txt", "content": "This are sample text."},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        task_id = payload.get("task_id")
        self.assertTrue(task_id)

        status, payload = self.client.request(
            "POST",
            f"/api/tasks/{task_id}/process",
            {"options": self._offline_processing_options()},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("task_id"), task_id)
        self.assertIn("prose_only_diff", payload)
        self.assertIsInstance(payload.get("prose_only_diff"), str)
        self.assertIn("strict_cmos_issues", payload)
        self.assertIsInstance(payload.get("strict_cmos_issues"), dict)

        status, payload = self.client.request("GET", f"/api/tasks/{task_id}/download", query={"type": "clean"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertIn("base64_data", payload)
        self.assertIn("task_diagnostics", payload)
        self.assertIsInstance(payload.get("task_diagnostics"), dict)
        self.assertIn("autopilot_audit", payload)
        self.assertIsInstance(payload.get("autopilot_audit"), dict)
        exported_bytes = base64.b64decode(payload["base64_data"])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as output_handle:
            output_path = output_handle.name
        try:
            with open(output_path, "wb") as outfile:
                outfile.write(exported_bytes)
            self.assertTrue(zipfile.is_zipfile(output_path))
            with zipfile.ZipFile(output_path) as archive:
                names = set(archive.namelist())
                self.assertIn("[Content_Types].xml", names)
                self.assertIn("word/document.xml", names)
                self.assertIn("word/_rels/document.xml.rels", names)
        finally:
            os.unlink(output_path)

        status, payload = self.client.request("GET", "/api/tasks")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertGreaterEqual(len(payload.get("tasks", [])), 1)

    def test_async_process_route_returns_job_and_status(self):
        self._login("writer@conwiz.in")

        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "sample.txt", "content": "This are sample text."},
        )
        self.assertEqual(status, 200)
        task_id = payload.get("task_id")
        self.assertTrue(task_id)

        status, payload = self.client.request(
            "POST",
            f"/api/tasks/{task_id}/process",
            {
                "async": True,
                "options": {
                    "spelling": True,
                    "sentence_case": True,
                    "punctuation": True,
                    "chicago_style": True,
                    "ai": {"enabled": False},
                },
            },
        )
        self.assertEqual(status, 202)
        self.assertTrue(payload.get("success"))
        self.assertTrue(payload.get("queued"))
        self.assertEqual(payload.get("task_id"), task_id)
        self.assertIn((payload.get("job") or {}).get("status"), {"PENDING", "RUNNING", "SUCCEEDED"})

        status, payload = self.client.request("GET", f"/api/tasks/{task_id}/process-status")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("task_id"), task_id)
        self.assertIn("job", payload)
        self.assertIn((payload.get("job") or {}).get("status"), {"PENDING", "RUNNING", "SUCCEEDED", "FAILED"})
        self.assertIn("task_run", payload)
        task_run = payload.get("task_run") or {}
        self.assertTrue(task_run.get("id"))

    def test_autopilot_route_returns_job_and_status(self):
        self._login("writer@conwiz.in")

        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "autopilot.txt", "content": "This are sample text."},
        )
        self.assertEqual(status, 200)
        task_id = payload.get("task_id")
        self.assertTrue(task_id)

        status, payload = self.client.request(
            "POST",
            f"/api/tasks/{task_id}/autopilot",
            {
                "options": {
                    "ai": {"enabled": False},
                    "automation": {
                        "auto_heal_bibliography": False,
                        "heal_when_reference_issues_at_least": 99,
                    },
                }
            },
        )
        self.assertEqual(status, 202)
        self.assertTrue(payload.get("success"))
        self.assertTrue(payload.get("queued"))
        self.assertEqual(payload.get("task_id"), task_id)
        self.assertIn((payload.get("job") or {}).get("status"), {"PENDING", "RUNNING", "SUCCEEDED"})

        status, payload = self.client.request("GET", f"/api/tasks/{task_id}/process-status")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("task_id"), task_id)
        self.assertIn("job", payload)
        self.assertIn((payload.get("job") or {}).get("status"), {"PENDING", "RUNNING", "SUCCEEDED", "FAILED"})
        self.assertIn("task_run", payload)
        task_run = payload.get("task_run") or {}
        self.assertTrue(task_run.get("id"))

        status_token = str((task_run.get("status") or "")).upper()
        self.assertIn(status_token, {"PENDING", "RUNNING", "SUCCEEDED", "FAILED"})

    @patch("webapp._process_task")
    def test_autopilot_retries_once_on_transient_failure_and_persists_audit(self, mock_process_task):
        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request("POST", "/api/auth/google-login", {"id_token": "test:amit@conwiz.in"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        status, payload = admin_client.request(
            "POST",
            "/api/admin/global-settings",
            {
                "settings": {
                    "editing": {
                        "autopilot_auto_heal_bibliography": False,
                        "autopilot_heal_when_reference_issues_at_least": 99,
                    },
                    "ai": {"enabled": False},
                }
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        self._login("writer@conwiz.in")
        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "autopilot-retry.txt", "content": "This are sample text."},
        )
        self.assertEqual(status, 200)
        task_id = str(payload.get("task_id") or "")
        self.assertTrue(task_id)

        attempts = {"count": 0}

        def _mocked_process_task(_context, _task, _options):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("timeout while contacting provider")
            return {
                "success": True,
                "task_id": task_id,
                "text": "This is sample text.",
                "full_corrected_text": "This is sample text.",
                "word_count": 4,
                "citation_reference_report": {"issue_count": 0},
                "processing_audit": {"mode": "rule_only", "summary": {}},
            }

        mock_process_task.side_effect = _mocked_process_task

        status, payload = self.client.request(
            "POST",
            f"/api/tasks/{task_id}/autopilot",
            {
                "options": {
                    "ai": {"enabled": False},
                    "automation": {
                        "min_overall_confidence_for_autocomplete": 1.01,
                        "min_reference_confidence_for_autoheal": 0.0,
                        "auto_heal_bibliography": True,
                        "heal_when_reference_issues_at_least": 0,
                    },
                }
            },
        )
        self.assertEqual(status, 202)
        self.assertTrue(payload.get("success"))
        self.assertTrue(payload.get("queued"))

        final_status = ""
        for _ in range(120):
            status, status_payload = self.client.request("GET", f"/api/tasks/{task_id}/process-status")
            self.assertEqual(status, 200)
            final_status = str(((status_payload.get("task_run") or {}).get("status") or "")).upper()
            if final_status in {"SUCCEEDED", "FAILED"}:
                break
            time.sleep(0.05)
        self.assertEqual(final_status, "SUCCEEDED")
        self.assertEqual(attempts["count"], 2)

        status, payload = self.client.request("GET", f"/api/tasks/{task_id}")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        reports = (payload.get("task") or {}).get("reports") or {}
        autopilot_audit = reports.get("autopilot_audit") if isinstance(reports, dict) else None
        self.assertIsInstance(autopilot_audit, dict)
        self.assertEqual(str(autopilot_audit.get("status") or ""), "completed")
        self.assertFalse(bool(autopilot_audit.get("heal_executed")))

        status, payload = self.client.request("GET", "/api/runtime-telemetry")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        telemetry = payload.get("telemetry") or {}
        self.assertGreaterEqual(int(telemetry.get("autopilot_retries", 0)), 1)

    def test_autopilot_low_confidence_routes_task_to_review_required_and_status_filter_works(self):
        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request("POST", "/api/auth/google-login", {"id_token": "test:amit@conwiz.in"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        status, payload = admin_client.request(
            "POST",
            "/api/admin/global-settings",
            {
                "settings": {
                    "editing": {
                        "autopilot_auto_heal_bibliography": True,
                        "autopilot_heal_when_reference_issues_at_least": 0,
                        "autopilot_min_overall_confidence_for_autocomplete": 1.0,
                        "autopilot_min_reference_confidence_for_autoheal": 0.0,
                    },
                    "ai": {"enabled": False},
                }
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        self._login("writer@conwiz.in")
        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {
                "file_name": "review-gate.txt",
                "content": (
                    "Introduction cites [1].\n"
                    "References\n"
                    "[1] Unknown Author. Missing metadata reference.\n"
                ),
            },
        )
        self.assertEqual(status, 200)
        task_id = str(payload.get("task_id") or "")
        self.assertTrue(task_id)

        confidence_patcher = patch(
            "webapp._compute_autopilot_confidence",
            return_value={
                "language_confidence": 0.82,
                "reference_confidence": 0.83,
                "citation_integrity_confidence": 0.81,
                "overall_autopilot_confidence": 0.82,
                "reference_issue_count": 2,
                "citation_issue_count": 1,
            },
        )
        confidence_patcher.start()
        try:
            status, payload = self.client.request(
                "POST",
                f"/api/tasks/{task_id}/autopilot",
                {
                    "options": {
                        "ai": {"enabled": False},
                        "automation": {
                            "min_overall_confidence_for_autocomplete": 0.95,
                            "min_reference_confidence_for_autoheal": 0.0,
                            "auto_heal_bibliography": True,
                            "heal_when_reference_issues_at_least": 0,
                        },
                    }
                },
            )
            self.assertEqual(status, 202)
            self.assertTrue(payload.get("success"))

            final_status = ""
            for _ in range(120):
                status, status_payload = self.client.request("GET", f"/api/tasks/{task_id}/process-status")
                self.assertEqual(status, 200)
                final_status = str(status_payload.get("status") or "")
                if final_status in {"REVIEW_REQUIRED", "FAILED"}:
                    break
                time.sleep(0.05)
        finally:
            confidence_patcher.stop()

        self.assertEqual(final_status, "REVIEW_REQUIRED")

        status, payload = self.client.request("GET", f"/api/tasks/{task_id}")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        reports = (payload.get("task") or {}).get("reports") or {}
        autopilot_audit = reports.get("autopilot_audit") if isinstance(reports, dict) else {}
        self.assertTrue(bool(autopilot_audit.get("review_required")))
        self.assertIsInstance(autopilot_audit.get("decision_reasons"), list)
        self.assertTrue(len(autopilot_audit.get("decision_reasons") or []) > 0)

        status, payload = self.client.request("GET", "/api/tasks", query={"status": "REVIEW_REQUIRED"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        tasks = payload.get("tasks") or []
        self.assertTrue(any(str(task.get("id") or "") == task_id for task in tasks))

    def test_runtime_telemetry_captures_processing_mode_and_editing_controls(self):
        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request("POST", "/api/auth/google-login", {"id_token": "test:amit@conwiz.in"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        status, payload = admin_client.request(
            "POST",
            "/api/admin/global-settings",
            {
                "settings": {
                    "editing": {
                        "editing_mode": "clarity",
                        "tone": "business",
                        "rewrite_strength": "moderate",
                        "explain_edits": True,
                    },
                    "ai": {"enabled": False},
                }
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        self._login("writer@conwiz.in")

        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "telemetry.txt", "content": "This are sample text."},
        )
        self.assertEqual(status, 200)
        task_id = payload.get("task_id")
        self.assertTrue(task_id)

        status, payload = self.client.request(
            "POST",
            f"/api/tasks/{task_id}/process",
            {"options": self._offline_processing_options()},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        status, payload = self.client.request("GET", "/api/runtime-telemetry")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        telemetry = payload.get("telemetry") or {}
        self.assertGreaterEqual(int(telemetry.get("process_runs_started", 0)), 1)
        self.assertGreaterEqual(int(telemetry.get("process_runs_succeeded", 0)), 1)
        self.assertEqual(int(telemetry.get("process_runs_failed", 0)), 0)
        self.assertIn("editing_mode_counts", telemetry)
        self.assertIn("tone_counts", telemetry)
        self.assertIn("rewrite_strength_counts", telemetry)
        self.assertIn("explain_edits_counts", telemetry)
        self.assertGreaterEqual(int((telemetry.get("editing_mode_counts") or {}).get("clarity", 0)), 1)
        self.assertGreaterEqual(int((telemetry.get("tone_counts") or {}).get("business", 0)), 1)
        self.assertGreaterEqual(int((telemetry.get("rewrite_strength_counts") or {}).get("moderate", 0)), 1)
        self.assertGreaterEqual(int((telemetry.get("explain_edits_counts") or {}).get("enabled", 0)), 1)
        self.assertIn("mode_counts", telemetry)

    def test_binary_download_endpoint_returns_valid_docx(self):
        self._force_offline_runtime_settings()
        self._login("writer@conwiz.in")

        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "sample.txt", "content": "This are sample text."},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        task_id = payload.get("task_id")
        self.assertTrue(task_id)

        status, payload = self.client.request(
            "POST",
            f"/api/tasks/{task_id}/process",
            {"options": self._offline_processing_options()},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        for file_type in ["clean", "highlighted", "highlighted_comments", "track_changes"]:
            status, body, headers = self.client.request_bytes(
                "GET",
                f"/api/tasks/{task_id}/download-file",
                query={"type": file_type},
            )
            self.assertEqual(status, 200)
            self.assertIn(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers.get("content-type", ""),
            )
            self.assertIn("attachment;", headers.get("content-disposition", ""))

            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as output_handle:
                output_path = output_handle.name
            try:
                with open(output_path, "wb") as outfile:
                    outfile.write(body)
                self.assertTrue(zipfile.is_zipfile(output_path))
                with zipfile.ZipFile(output_path) as archive:
                    names = set(archive.namelist())
                    self.assertIn("[Content_Types].xml", names)
                    self.assertIn("word/document.xml", names)
                    self.assertIn("word/_rels/document.xml.rels", names)
            finally:
                os.unlink(output_path)

    def test_legacy_export_file_uses_docx_template_when_base64_source_is_supplied(self):
        self._login("writer@conwiz.in")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as source_handle:
            source_path = source_handle.name

        try:
            doc = Document()
            doc.add_paragraph("Intro paragraph")
            table = doc.add_table(rows=1, cols=2)
            table.cell(0, 0).text = "A1"
            table.cell(0, 1).text = "B1"
            doc.add_paragraph("Closing paragraph")
            doc.save(source_path)

            with open(source_path, "rb") as infile:
                source_docx_base64 = base64.b64encode(infile.read()).decode("ascii")

            status, payload = self.client.request(
                "POST",
                "/api/export-file",
                {
                    "task_id": "",
                    "source_type": "docx",
                    "source_docx_base64": source_docx_base64,
                    "file_type": "clean",
                    "original_text": "Intro paragraph\nA1\tB1\nClosing paragraph",
                    "corrected_text": "Updated intro\nR1C1\tR1C2\nUpdated closing",
                    "file_name": "sample.docx",
                },
            )
            self.assertEqual(status, 200)
            self.assertTrue(payload.get("success"))
            self.assertIn("base64_data", payload)

            exported_bytes = base64.b64decode(payload["base64_data"])
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as output_handle:
                output_path = output_handle.name

            try:
                with open(output_path, "wb") as outfile:
                    outfile.write(exported_bytes)
                out_doc = Document(output_path)
                self.assertEqual(out_doc.paragraphs[0].text, "Updated intro")
                self.assertEqual(len(out_doc.tables), 1)
                self.assertEqual(out_doc.tables[0].cell(0, 0).text, "R1C1")
                self.assertEqual(out_doc.tables[0].cell(0, 1).text, "R1C2")
                self.assertEqual(out_doc.paragraphs[-1].text, "Updated closing")
            finally:
                os.unlink(output_path)
        finally:
            os.unlink(source_path)

    def test_legacy_process_document_can_create_and_process_docx_task_without_task_id(self):
        self._login("writer@conwiz.in")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as source_handle:
            source_path = source_handle.name

        try:
            doc = Document()
            doc.add_paragraph("Intro paragraph")
            table = doc.add_table(rows=1, cols=2)
            table.cell(0, 0).text = "A1"
            table.cell(0, 1).text = "B1"
            doc.add_paragraph("Closing paragraph")
            doc.save(source_path)

            with open(source_path, "rb") as infile:
                source_docx_base64 = base64.b64encode(infile.read()).decode("ascii")

            status, payload = self.client.request(
                "POST",
                "/api/process-document",
                {
                    "task_id": "",
                    "source_type": "docx",
                    "source_docx_base64": source_docx_base64,
                    "source_text": "Intro paragraph\nA1\tB1\nClosing paragraph",
                    "source_file_name": "sample.docx",
                    "options": {
                        "spelling": True,
                        "sentence_case": True,
                        "punctuation": True,
                        "chicago_style": True,
                        "ai": {"enabled": False},
                    },
                },
            )
            self.assertEqual(status, 200)
            self.assertTrue(payload.get("success"))
            task_id = payload.get("task_id")
            self.assertTrue(task_id)

            status, task_payload = self.client.request("GET", f"/api/tasks/{task_id}")
            self.assertEqual(status, 200)
            self.assertTrue(task_payload.get("success"))
            task = task_payload.get("task") or {}
            self.assertEqual(task.get("status"), "PROCESSED")
            self.assertTrue(str(task.get("corrected_text") or "").strip())
            self.assertTrue(task.get("downloads", {}).get("clean"))
            self.assertTrue(task.get("downloads", {}).get("highlighted"))
        finally:
            os.unlink(source_path)

    def test_upload_succeeds_when_bridge_header_is_present(self):
        self._login("bridge@conwiz.in")
        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "sample.txt", "content": "Bridge header upload should work."},
            headers={"X-Manuscript-Session": "browser-fallback-session-id"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertTrue(payload.get("task_id"))

    def test_task_access_isolated_between_users(self):
        owner = WsgiTestClient(webapp.app)
        other = WsgiTestClient(webapp.app)

        status, _ = owner.request("POST", "/api/auth/google-login", {"id_token": "test:owner@conwiz.in"})
        self.assertEqual(status, 200)

        status, payload = owner.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "alpha.txt", "content": "Alpha manuscript."},
        )
        self.assertEqual(status, 200)
        task_id = payload.get("task_id")

        status, _ = other.request("POST", "/api/auth/google-login", {"id_token": "test:other@conwiz.in"})
        self.assertEqual(status, 200)

        status, payload = other.request("GET", f"/api/tasks/{task_id}")
        self.assertEqual(status, 404)
        self.assertFalse(payload.get("success"))
        self.assertEqual(payload.get("error_code"), "TASK_NOT_FOUND")

    def test_assistant_requires_auth(self):
        status, payload = self.client.request(
            "POST",
            "/api/assistant",
            {"mode": "qna", "message": "help"},
        )
        self.assertEqual(status, 401)
        self.assertFalse(payload.get("success"))
        self.assertEqual(payload.get("error_code"), "AUTH_REQUIRED")

    def test_assistant_qna_returns_read_only_diagnostics(self):
        self._login("writer@conwiz.in")
        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "sample.txt", "content": "This are sample text."},
        )
        self.assertEqual(status, 200)
        task_id = str(payload.get("task_id") or "")
        self.assertTrue(task_id)

        status, payload = self.client.request(
            "POST",
            "/api/assistant",
            {"mode": "qna", "task_id": task_id, "message": "show spelling and citation diagnostics"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("mode"), "qna")
        assistant = payload.get("assistant") or {}
        self.assertIsInstance(assistant.get("message"), str)
        self.assertTrue(assistant.get("message"))
        self.assertIsInstance(assistant.get("suggestions"), list)
        diagnostics = assistant.get("task_diagnostics") or {}
        self.assertEqual((diagnostics.get("task") or {}).get("id"), task_id)

    def test_assistant_qna_admin_activity_summary_requires_admin_role(self):
        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request(
            "POST",
            "/api/auth/google-login",
            {"id_token": "test:amit@conwiz.in"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        status, payload = admin_client.request(
            "POST",
            "/api/assistant",
            {
                "mode": "qna",
                "message": "show all activity",
                "include_admin_activity": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        assistant = payload.get("assistant") or {}
        admin_activity = assistant.get("admin_activity") or {}
        self.assertIsInstance(admin_activity.get("user_counts"), dict)
        self.assertIn("top_event_types", admin_activity)

        member_client = WsgiTestClient(webapp.app)
        status, payload = member_client.request(
            "POST",
            "/api/auth/google-login",
            {"id_token": "test:member@conwiz.in"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        status, payload = member_client.request(
            "POST",
            "/api/assistant",
            {
                "mode": "qna",
                "message": "show all activity",
                "include_admin_activity": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        assistant = payload.get("assistant") or {}
        self.assertNotIn("admin_activity", assistant)

    def test_assistant_action_reprocess_task(self):
        self._login("writer@conwiz.in")
        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "sample.txt", "content": "This are sample text."},
        )
        self.assertEqual(status, 200)
        task_id = str(payload.get("task_id") or "")
        self.assertTrue(task_id)

        status, payload = self.client.request(
            "POST",
            "/api/assistant",
            {
                "mode": "action",
                "action": "reprocess_task",
                "task_id": task_id,
                "options": {"ai": {"enabled": False}},
                "confirm": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("mode"), "action")
        self.assertEqual(payload.get("action"), "reprocess_task")
        result = payload.get("result") or {}
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("task_id"), task_id)
        self.assertTrue(str(result.get("text") or "").strip())

    def test_assistant_action_reprocess_respects_task_ownership(self):
        owner = WsgiTestClient(webapp.app)
        other = WsgiTestClient(webapp.app)
        status, _ = owner.request("POST", "/api/auth/google-login", {"id_token": "test:owner@conwiz.in"})
        self.assertEqual(status, 200)
        status, payload = owner.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "alpha.txt", "content": "Alpha manuscript."},
        )
        self.assertEqual(status, 200)
        task_id = str(payload.get("task_id") or "")
        self.assertTrue(task_id)

        status, _ = other.request("POST", "/api/auth/google-login", {"id_token": "test:other@conwiz.in"})
        self.assertEqual(status, 200)
        status, payload = other.request(
            "POST",
            "/api/assistant",
            {
                "mode": "action",
                "action": "reprocess_task",
                "task_id": task_id,
                "options": {"ai": {"enabled": False}},
                "confirm": True,
            },
        )
        self.assertEqual(status, 404)
        self.assertFalse(payload.get("success"))
        self.assertEqual(payload.get("error_code"), "TASK_NOT_FOUND")

    def test_assistant_action_requires_explicit_confirmation(self):
        self._login("writer@conwiz.in")
        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "sample.txt", "content": "This are sample text."},
        )
        self.assertEqual(status, 200)
        task_id = str(payload.get("task_id") or "")
        self.assertTrue(task_id)

        status, payload = self.client.request(
            "POST",
            "/api/assistant",
            {
                "mode": "action",
                "action": "reprocess_task",
                "task_id": task_id,
                "options": {"ai": {"enabled": False}},
            },
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload.get("success"))
        self.assertEqual(payload.get("error_code"), "ASSISTANT_CONFIRMATION_REQUIRED")

    def test_assistant_action_apply_group_decisions(self):
        self._login("writer@conwiz.in")
        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {"file_name": "sample.txt", "content": "This are sample text."},
        )
        self.assertEqual(status, 200)
        task_id = str(payload.get("task_id") or "")
        self.assertTrue(task_id)

        status, payload = self.client.request(
            "POST",
            f"/api/tasks/{task_id}/process",
            {"options": {"ai": {"enabled": False}}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        status, payload = self.client.request(
            "POST",
            "/api/assistant",
            {
                "mode": "action",
                "action": "apply_correction_group_decisions",
                "task_id": task_id,
                "group_decisions": {
                    "spelling": True,
                    "capitalization": True,
                    "punctuation": True,
                    "citation": True,
                    "reference": True,
                    "style": True,
                },
                "confirm": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("action"), "apply_correction_group_decisions")
        result = payload.get("result") or {}
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("task_id"), task_id)

    def test_admin_can_view_users_and_non_admin_cannot(self):
        # Non-admin user should be blocked from admin endpoints.
        self._login("member@conwiz.in")
        status, payload = self.client.request("GET", "/api/admin/users")
        self.assertEqual(status, 403)
        self.assertFalse(payload.get("success"))
        self.assertEqual(payload.get("error_code"), "FORBIDDEN")

        # Admin login should allow access.
        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request(
            "POST",
            "/api/auth/google-login",
            {"id_token": "test:amit@conwiz.in"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        status, payload = admin_client.request("GET", "/api/admin/users")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertGreaterEqual(len(payload.get("users", [])), 1)

    def test_admin_can_validate_ai_provider(self):
        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request(
            "POST",
            "/api/auth/google-login",
            {"id_token": "test:amit@conwiz.in"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        status, payload = admin_client.request(
            "POST",
            "/api/admin/validate-ai-provider",
            {"provider": "unsupported-provider"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertFalse(payload.get("valid"))
        self.assertIn("Unsupported provider", str(payload.get("message", "")))

    def test_admin_global_settings_round_trip(self):
        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request("POST", "/api/auth/google-login", {"id_token": "test:amit@conwiz.in"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        status, payload = admin_client.request("GET", "/api/admin/global-settings")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertIn("settings", payload)

        updated = {
            "editing": {
                "spelling": True,
                "sentence_case": True,
                "punctuation": True,
                "chicago_style": True,
                "cmos_strict_mode": True,
                "online_reference_validation_admin_cap": 220,
                "auto_resolve_unresolved_references": False,
                "autopilot_auto_heal_bibliography": False,
                "autopilot_heal_when_reference_issues_at_least": 7,
                "autopilot_min_overall_confidence_for_autocomplete": 0.78,
                "autopilot_min_reference_confidence_for_autoheal": 0.55,
                "domain_profile": "medical",
                "editing_mode": "tone_adjust",
                "tone": "formal",
                "rewrite_strength": "moderate",
                "explain_edits": True,
                "cmos_profile": "strict",
                "custom_terms": ["myocardial infarction", "HbA1c"],
            },
            "ai": {
                "enabled": True,
                "provider": "agent_router",
                "model": "gpt-5",
                "ollama_host": "http://localhost:11434",
                "gemini_api_key": "gem-key",
                "openrouter_api_key": "or-key",
                "agent_router_api_key": "ar-key",
                "section_wise": True,
                "section_threshold_chars": 14000,
                "section_threshold_paragraphs": 100,
                "section_chunk_chars": 6000,
                "section_chunk_lines": 32,
                "global_consistency_max_chars": 19000,
                "ollama_generate_timeout_seconds": 35,
                "ollama_health_timeout_seconds": 4,
                "ollama_retry_count": 2,
                "ollama_retry_backoff_seconds": 0.25,
                "ollama_fallback_model_retry": False,
            },
        }
        status, payload = admin_client.request("POST", "/api/admin/global-settings", {"settings": updated})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("settings", {}).get("editing", {}).get("domain_profile"), "medical")
        self.assertEqual(payload.get("settings", {}).get("editing", {}).get("cmos_profile"), "strict")
        self.assertEqual(payload.get("settings", {}).get("editing", {}).get("editing_mode"), "tone_adjust")
        self.assertEqual(payload.get("settings", {}).get("editing", {}).get("tone"), "formal")
        self.assertEqual(payload.get("settings", {}).get("editing", {}).get("rewrite_strength"), "moderate")
        self.assertTrue(payload.get("settings", {}).get("editing", {}).get("explain_edits"))
        self.assertEqual(int(payload.get("settings", {}).get("editing", {}).get("online_reference_validation_admin_cap", 0)), 220)
        self.assertFalse(payload.get("settings", {}).get("editing", {}).get("auto_resolve_unresolved_references"))
        self.assertFalse(payload.get("settings", {}).get("editing", {}).get("autopilot_auto_heal_bibliography"))
        self.assertEqual(int(payload.get("settings", {}).get("editing", {}).get("autopilot_heal_when_reference_issues_at_least", 0)), 7)
        self.assertAlmostEqual(float(payload.get("settings", {}).get("editing", {}).get("autopilot_min_overall_confidence_for_autocomplete", 0)), 0.78, places=2)
        self.assertAlmostEqual(float(payload.get("settings", {}).get("editing", {}).get("autopilot_min_reference_confidence_for_autoheal", 0)), 0.55, places=2)
        admin_ai = payload.get("settings", {}).get("ai", {})
        self.assertEqual(float(admin_ai.get("ollama_generate_timeout_seconds", 0)), 35)
        self.assertEqual(float(admin_ai.get("ollama_health_timeout_seconds", 0)), 4)
        self.assertEqual(int(admin_ai.get("ollama_retry_count", 0)), 2)
        self.assertEqual(float(admin_ai.get("ollama_retry_backoff_seconds", 0)), 0.25)
        self.assertFalse(admin_ai.get("ollama_fallback_model_retry"))

        user_client = WsgiTestClient(webapp.app)
        status, payload = user_client.request("POST", "/api/auth/google-login", {"id_token": "test:user@conwiz.in"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        status, payload = user_client.request("GET", "/api/settings/runtime")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        user_settings = payload.get("settings", {})
        self.assertEqual(user_settings.get("editing", {}).get("domain_profile"), "medical")
        self.assertEqual(user_settings.get("editing", {}).get("cmos_profile"), "strict")
        self.assertEqual(user_settings.get("editing", {}).get("editing_mode"), "tone_adjust")
        self.assertEqual(user_settings.get("editing", {}).get("tone"), "formal")
        self.assertEqual(user_settings.get("editing", {}).get("rewrite_strength"), "moderate")
        self.assertTrue(user_settings.get("editing", {}).get("explain_edits"))
        self.assertEqual(int(user_settings.get("editing", {}).get("online_reference_validation_admin_cap", 0)), 220)
        self.assertFalse(user_settings.get("editing", {}).get("auto_resolve_unresolved_references"))
        self.assertFalse(user_settings.get("editing", {}).get("autopilot_auto_heal_bibliography"))
        self.assertEqual(int(user_settings.get("editing", {}).get("autopilot_heal_when_reference_issues_at_least", 0)), 7)
        self.assertAlmostEqual(float(user_settings.get("editing", {}).get("autopilot_min_overall_confidence_for_autocomplete", 0)), 0.78, places=2)
        self.assertAlmostEqual(float(user_settings.get("editing", {}).get("autopilot_min_reference_confidence_for_autoheal", 0)), 0.55, places=2)
        user_ai = user_settings.get("ai", {})
        self.assertEqual(float(user_ai.get("ollama_generate_timeout_seconds", 0)), 35)
        self.assertEqual(float(user_ai.get("ollama_health_timeout_seconds", 0)), 4)
        self.assertEqual(int(user_ai.get("ollama_retry_count", 0)), 2)
        self.assertEqual(float(user_ai.get("ollama_retry_backoff_seconds", 0)), 0.25)
        self.assertFalse(user_ai.get("ollama_fallback_model_retry"))
        self.assertEqual(user_settings.get("ai", {}).get("openrouter_api_key", ""), "")

    def test_phase3_settings_ux_wiring_is_present(self):
        status, html = self.client.request_text("GET", "/tasks/example-task-id")
        self.assertEqual(status, 200)
        self.assertIn('id="editing-mode-help"', html)
        self.assertIn('id="target-tone-help"', html)
        self.assertIn('id="rewrite-strength-help"', html)
        self.assertIn('id="explain-edits-help"', html)
        self.assertIn('id="managed-settings-runtime-status"', html)
        self.assertIn('id="admin-editing-mode-help"', html)
        self.assertIn('id="admin-tone-help"', html)
        self.assertIn('id="admin-rewrite-strength-help"', html)
        self.assertIn('id="admin-ai-provider-label"', html)
        self.assertIn('role="group" aria-labelledby="admin-ai-provider-label"', html)

        index_path = os.path.join(os.path.dirname(__file__), "..", "web", "index.html")
        with open(index_path, "r", encoding="utf-8") as handle:
            index_source = handle.read()
        self.assertIn('id="admin-editing-group-label"', index_source)
        self.assertIn('role="group" aria-labelledby="admin-editing-group-label"', index_source)
        self.assertIn('id="admin-ollama-transport-label"', index_source)
        self.assertIn('role="group" aria-labelledby="admin-ollama-transport-label"', index_source)
        self.assertIn('id="admin-advanced-ai-label"', index_source)
        self.assertIn('role="group" aria-labelledby="admin-advanced-ai-label"', index_source)

        task_detail_path = os.path.join(os.path.dirname(__file__), "..", "web", "task_detail.html")
        with open(task_detail_path, "r", encoding="utf-8") as handle:
            task_detail_source = handle.read()
        self.assertIn('id="admin-advanced-ai-label"', task_detail_source)
        self.assertIn('role="group" aria-labelledby="admin-advanced-ai-label"', task_detail_source)

        runtime_path = os.path.join(os.path.dirname(__file__), "..", "web", "admin", "runtime.js")
        with open(runtime_path, "r", encoding="utf-8") as handle:
            runtime_source = handle.read()
        self.assertIn("function setManagedRuntimeStatus", runtime_source)
        self.assertIn("Loading managed runtime settings", runtime_source)
        self.assertIn("Managed settings loaded", runtime_source)
        self.assertIn("safe local fallback", runtime_source)

        settings_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-settings.js")
        with open(settings_path, "r", encoding="utf-8") as handle:
            settings_source = handle.read()
        self.assertIn("function updateEditingExperienceHints", settings_source)
        self.assertIn("editingModeHelp", settings_source)
        self.assertIn("targetToneHelp", settings_source)
        self.assertIn("rewriteStrengthHelp", settings_source)
        self.assertIn("explainEditsHelp", settings_source)

        panel_path = os.path.join(os.path.dirname(__file__), "..", "web", "app-settings-panel.js")
        with open(panel_path, "r", encoding="utf-8") as handle:
            panel_source = handle.read()
        self.assertIn("updateEditingExperienceHints", panel_source)
        self.assertIn("updateAdminEditingControlsHint", panel_source)

        admin_global_path = os.path.join(os.path.dirname(__file__), "..", "web", "admin", "global-settings.js")
        with open(admin_global_path, "r", encoding="utf-8") as handle:
            admin_global_source = handle.read()
        self.assertIn("function updateAdminEditingControlsHint", admin_global_source)
        self.assertIn("Saving global settings...", admin_global_source)
        self.assertIn("Global settings loaded.", admin_global_source)
        self.assertIn("closest('.password-field')", admin_global_source)

    def test_admin_reference_validation_diagnostics_requires_admin(self):
        self._login("member@conwiz.in")
        status, payload = self.client.request("GET", "/api/admin/reference-validation-diagnostics")
        self.assertEqual(status, 403)
        self.assertFalse(payload.get("success"))
        self.assertEqual(payload.get("error_code"), "FORBIDDEN")

    def test_admin_reference_validation_diagnostics_reset_requires_admin(self):
        self._login("member@conwiz.in")
        status, payload = self.client.request("POST", "/api/admin/reference-validation-diagnostics/reset")
        self.assertEqual(status, 403)
        self.assertFalse(payload.get("success"))
        self.assertEqual(payload.get("error_code"), "FORBIDDEN")

    def test_admin_reference_validation_diagnostics_is_safe_and_structured(self):
        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request("POST", "/api/auth/google-login", {"id_token": "test:amit@conwiz.in"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        with patch.dict("os.environ", {"SERPER_API_KEY": "serper-secret-test-key"}, clear=False):
            status, payload = admin_client.request("GET", "/api/admin/reference-validation-diagnostics")

        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        diagnostics = payload.get("diagnostics", {})
        self.assertIsInstance(diagnostics, dict)
        self.assertIn("generated_at", diagnostics)
        self.assertIn("global_runtime", diagnostics)
        self.assertIn("serper", diagnostics)
        self.assertIn("cache", diagnostics)
        self.assertIn("lookup_metrics_last_run", diagnostics)
        self.assertTrue(bool(diagnostics.get("serper", {}).get("configured")))
        self.assertIn("autopilot_auto_heal_bibliography", diagnostics.get("global_runtime", {}))
        self.assertIn("autopilot_heal_when_reference_issues_at_least", diagnostics.get("global_runtime", {}))
        self.assertIn("autopilot_min_overall_confidence_for_autocomplete", diagnostics.get("global_runtime", {}))
        self.assertIn("autopilot_min_reference_confidence_for_autoheal", diagnostics.get("global_runtime", {}))
        serialized = json.dumps(payload)
        self.assertNotIn("serper-secret-test-key", serialized)

    def test_admin_reference_validation_diagnostics_reset_clears_cache(self):
        with ChicagoEditor._SHARED_ONLINE_VALIDATION_CACHE_LOCK:
            ChicagoEditor._SHARED_ONLINE_VALIDATION_CACHE["serper_search:{\"q\":\"test\"}"] = {
                "expires_at": 9999999999,
                "value": [{"title": "cached"}],
            }

        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request("POST", "/api/auth/google-login", {"id_token": "test:amit@conwiz.in"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        status, payload = admin_client.request("POST", "/api/admin/reference-validation-diagnostics/reset")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertGreaterEqual(int(payload.get("removed_cache_entries", 0)), 1)
        diagnostics = payload.get("diagnostics", {})
        self.assertEqual(int((diagnostics.get("cache", {}) or {}).get("entries_total", -1)), 0)

    @patch("chicago_editor.requests.get")
    def test_admin_reference_validation_diagnostics_include_last_run_lookup_metrics(self, mock_get):
        crossref_empty = Mock()
        crossref_empty.status_code = 200
        crossref_empty.raise_for_status.return_value = None
        crossref_empty.json.return_value = {"message": {"items": []}}
        openalex_empty = Mock()
        openalex_empty.status_code = 200
        openalex_empty.raise_for_status.return_value = None
        openalex_empty.json.return_value = {"results": []}
        mock_get.side_effect = [crossref_empty, openalex_empty]

        self._login("writer@conwiz.in")
        status, payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {
                "file_name": "refs.txt",
                "content": (
                    "Introduction cites [1].\n"
                    "References\n"
                    "[1] Kaplan S. The restorative benefits of nature toward an integrative framework. "
                    "J Environ Psychol. 1995 ;15(3):169-182.\n"
                ),
            },
        )
        self.assertEqual(status, 200)
        task_id = payload.get("task_id")
        self.assertTrue(task_id)

        status, payload = self.client.request(
            "POST",
            f"/api/tasks/{task_id}/process",
            {"options": {"ai": {"enabled": False}}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request("POST", "/api/auth/google-login", {"id_token": "test:amit@conwiz.in"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        status, payload = admin_client.request("GET", "/api/admin/reference-validation-diagnostics")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        diagnostics = payload.get("diagnostics", {})
        self.assertGreater(int((diagnostics.get("lookup_metrics_last_run", {}) or {}).get("crossref_requests", 0)), 0)
        self.assertGreater(int(diagnostics.get("lookup_metrics_last_run_at", 0) or 0), 0)

    def test_deactivated_user_cannot_access_api(self):
        admin_client = WsgiTestClient(webapp.app)
        user_client = WsgiTestClient(webapp.app)

        status, payload = admin_client.request("POST", "/api/auth/google-login", {"id_token": "test:amit@conwiz.in"})
        self.assertEqual(status, 200)

        status, payload = user_client.request("POST", "/api/auth/google-login", {"id_token": "test:reviewer@conwiz.in"})
        self.assertEqual(status, 200)
        user_id = payload["user"]["id"]

        status, payload = admin_client.request(
            "POST",
            f"/api/admin/users/{user_id}/status",
            {"status": "INACTIVE"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        status, payload = user_client.request("GET", "/api/tasks")
        self.assertIn(status, (401, 403))
        self.assertFalse(payload.get("success"))
        self.assertIn(payload.get("error_code"), {"AUTH_USER_INACTIVE", "AUTH_SESSION_INVALID"})

    @patch("webapp.requests.post")
    def test_admin_validate_ai_provider_uses_saved_global_key_when_input_blank(self, mock_post):
        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request("POST", "/api/auth/google-login", {"id_token": "test:amit@conwiz.in"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        status, payload = admin_client.request(
            "POST",
            "/api/admin/global-settings",
            {
                "settings": {
                    "editing": {},
                    "ai": {
                        "provider": "agent_router",
                        "model": "gpt-5",
                        "agent_router_api_key": "saved-agent-token",
                    },
                }
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        mock_post.return_value = mock_response

        status, payload = admin_client.request(
            "POST",
            "/api/admin/validate-ai-provider",
            {"provider": "agent_router", "model": "", "api_key": "", "ollama_host": ""},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertTrue(payload.get("valid"))

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer saved-agent-token")
        self.assertEqual(kwargs["json"]["model"], "gpt-5")

    @patch("webapp.requests.get")
    def test_validate_ai_provider_runtime_checks_ollama_model_presence(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'{"models":[{"name":"llama3.1:latest"}]}'
        mock_response.json.return_value = {"models": [{"name": "llama3.1:latest"}]}
        mock_get.return_value = mock_response

        ok, message = webapp._validate_ai_provider_runtime("ollama", "missing-model", "", "http://localhost:11434")
        self.assertFalse(ok)
        self.assertIn("not installed", message)

        ok, message = webapp._validate_ai_provider_runtime("ollama", "llama3.1:latest", "", "http://localhost:11434")
        self.assertTrue(ok)
        self.assertIn("with model llama3.1:latest", message)

    def test_admin_journal_profiles_requires_admin(self):
        self._login("member@conwiz.in")
        status, payload = self.client.request("GET", "/api/admin/journal-profiles")
        self.assertEqual(status, 403)
        self.assertFalse(payload.get("success"))
        self.assertEqual(payload.get("error_code"), "FORBIDDEN")

    def test_admin_journal_profiles_returns_all_profiles_and_computes_scores(self):
        admin_client = WsgiTestClient(webapp.app)
        status, payload = admin_client.request("POST", "/api/auth/google-login", {"id_token": "test:amit@conwiz.in"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))

        # Fetch without a task_id
        status, payload = admin_client.request("GET", "/api/admin/journal-profiles")
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        profiles = payload.get("profiles", [])
        self.assertGreaterEqual(len(profiles), 1)
        
        # Verify first item schema
        first = profiles[0]
        self.assertIn("id", first)
        self.assertIn("label", first)
        self.assertIn("initials_with_periods", first)
        self.assertIn("title_case", first)
        self.assertIn("journal_abbrev", first)
        self.assertEqual(first["match_score"], 100)
        self.assertEqual(first["issue_total"], 0)

        # Upload a task and fetch with task_id to check score computation
        self._login("writer@conwiz.in")
        status, upload_payload = self.client.request(
            "POST",
            "/api/tasks/upload-text",
            {
                "file_name": "refs.txt",
                "content": (
                    "Introduction cites [1].\n"
                    "References\n"
                    "[1] Kaplan S. The restorative benefits of nature toward an integrative framework. "
                    "J Environ Psychol. 1995 ;15(3):169-182.\n"
                ),
            },
        )
        self.assertEqual(status, 200)
        task_id = upload_payload.get("task_id")
        self.assertTrue(task_id)

        status, payload = admin_client.request("GET", "/api/admin/journal-profiles", query={"task_id": task_id})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        profiles = payload.get("profiles", [])
        self.assertGreaterEqual(len(profiles), 1)
        
        for p in profiles:
            self.assertIn("match_score", p)
            self.assertIn("issue_total", p)
            self.assertIn("reference_count", p)
            self.assertIn("validation_messages", p)


if __name__ == "__main__":
    unittest.main()
