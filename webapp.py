#!/usr/bin/env python3
"""Deployable WSGI web application for Manuscript Editor."""

from __future__ import annotations

import base64
import hashlib
import math
import json
import os
import re
import copy
import tempfile
import threading
import time
import traceback
import uuid
import zipfile
import xml.etree.ElementTree as ET
import requests
from functools import wraps
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

from bottle import Bottle, HTTPResponse, request, response, run, static_file

from app_store import AppStore, ROLE_ADMIN, STATUS_ACTIVE, STATUS_INACTIVE, SessionContext
from document_processor import DocumentProcessor
from job_queue import BackgroundJobQueue
from version_info import APP_VERSION, WEB_ASSET_VERSION
import manuscript_service


try:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token
except Exception:  # pragma: no cover - optional import if auth deps missing
    google_requests = None
    google_id_token = None


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT_DIR, "web")
REQUIRED_WEB_ASSETS = (
    "index.html",
    "tasks.html",
    "task_detail.html",
    "style.css",
    "app.js",
    "app-assistant.js",
    "app-settings-panel.js",
    "app-heal-bibliography.js",
    "admin/runtime.js",
    "admin/audit.js",
    "admin/users.js",
    "admin/global-settings.js",
    "admin/reference-diagnostics.js",
    "admin/panel.js",
    "eel_web_bridge.js",
    "fragments/login.html",
    "fragments/app_header.html",
    "fragments/assistant_panel.html",
    "fragments/app_footer.html",
    "fragments/script_bundle.html",
)

SESSION_COOKIE_NAME = "manuscript_editor_sid"
SESSION_COOKIE_ALT_NAME = "manuscript_editor_sid_v2"
SESSION_COOKIE_ENV_KEY = "manuscript_editor.session_id"
SESSION_HEADER_NAME = "HTTP_X_MANUSCRIPT_SESSION"

DEFAULT_ALLOWED_DOMAINS = [
    "celnet.in",
    "conwiz.in",
    "stmjournals.in",
    "stmjournals.com",
    "nanoschool.in",
    "nstc.in",
]
DEFAULT_ADMIN_EMAILS = [
    "amit@conwiz.in",
    "puneet.mehrotra@celnet.in",
]

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
APP_SETTING_KEY_GLOBAL_RUNTIME = "global_runtime_settings"
APP_SETTING_KEY_REFERENCE_UNRESOLVED_TRENDS = "reference_unresolved_trends"


def _boot_env_int(key: str, default_value: int, min_value: int, max_value: int) -> int:
    raw = str(os.getenv(key, "") or "").strip()
    if not raw:
        return default_value
    try:
        parsed = int(raw)
    except Exception:
        return default_value
    return max(min_value, min(max_value, parsed))


PROCESSING_JOB_WORKERS = _boot_env_int("PROCESSING_JOB_WORKERS", 2, 1, 32)
MAX_UPLOAD_BYTES = _boot_env_int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024, 1024 * 100, 1024 * 1024 * 100)
MAX_TEXT_CHARS = _boot_env_int("MAX_TEXT_CHARS", 500000, 1000, 5_000_000)
TASK_LIST_LIMIT_MAX = _boot_env_int("TASK_LIST_LIMIT_MAX", 200, 10, 1000)
AUTH_RATE_LIMIT_COUNT = _boot_env_int("AUTH_RATE_LIMIT_COUNT", 20, 1, 1000)
AUTH_RATE_LIMIT_WINDOW_SECONDS = _boot_env_int("AUTH_RATE_LIMIT_WINDOW_SECONDS", 300, 1, 3600)
WRITE_RATE_LIMIT_COUNT = _boot_env_int("WRITE_RATE_LIMIT_COUNT", 120, 1, 5000)
WRITE_RATE_LIMIT_WINDOW_SECONDS = _boot_env_int("WRITE_RATE_LIMIT_WINDOW_SECONDS", 300, 1, 3600)
ALLOWED_ORIGINS = [value.strip().lower() for value in str(os.getenv("ALLOWED_ORIGINS", "") or "").split(",") if value.strip()]


def _parse_csv_env(key: str, default_values):
    raw = str(os.getenv(key, "") or "").strip()
    if not raw:
        return [str(value).strip().lower() for value in default_values if str(value).strip()]
    values = []
    for piece in raw.split(","):
        candidate = str(piece or "").strip().lower()
        if candidate:
            values.append(candidate)
    return values


def _env_int(key: str, default_value: int, min_value: int, max_value: int) -> int:
    raw = str(os.getenv(key, "") or "").strip()
    if not raw:
        return default_value
    try:
        parsed = int(raw)
    except Exception:
        return default_value
    return max(min_value, min(max_value, parsed))


GOOGLE_CLIENT_ID = str(os.getenv("GOOGLE_CLIENT_ID", "") or "").strip()
ALLOWED_EMAIL_DOMAINS = sorted(set(_parse_csv_env("ALLOWED_EMAIL_DOMAINS", DEFAULT_ALLOWED_DOMAINS)))
ADMIN_EMAILS = sorted(set(_parse_csv_env("ADMIN_EMAILS", DEFAULT_ADMIN_EMAILS)))
SESSION_TTL_HOURS = _env_int("SESSION_TTL_HOURS", 12, 1, 168)
FILE_RETENTION_DAYS = _env_int("FILE_RETENTION_DAYS", 30, 1, 3650)
DATA_DIR = os.path.abspath(str(os.getenv("DATA_DIR", os.path.join(ROOT_DIR, "data")) or os.path.join(ROOT_DIR, "data")))
DATABASE_URL = str(os.getenv("DATABASE_URL", "") or "").strip()
ENABLE_DEV_TEST_TOKENS = str(os.getenv("MANUSCRIPT_EDITOR_DEV_TEST_TOKENS", "0") or "0").strip() in (
    "1",
    "true",
    "yes",
)
ENABLE_LOCAL_MANUAL_LOGIN = str(os.getenv("MANUSCRIPT_EDITOR_LOCAL_LOGIN", "0") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
LOCAL_MANUAL_LOGIN_USERNAME = str(os.getenv("MANUSCRIPT_EDITOR_LOCAL_LOGIN_USERNAME", "admin") or "admin").strip()
LOCAL_MANUAL_LOGIN_PASSWORD = str(os.getenv("MANUSCRIPT_EDITOR_LOCAL_LOGIN_PASSWORD", "password") or "password")


os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "tasks"), exist_ok=True)

_STORE = AppStore(database_url=DATABASE_URL, data_dir=DATA_DIR)
_STORE.bootstrap_admin_roles(ADMIN_EMAILS)
_PROCESSING_JOB_QUEUE = BackgroundJobQueue(max_workers=PROCESSING_JOB_WORKERS)

_CLEANUP_LOCK = threading.Lock()
_LAST_CLEANUP_AT = 0.0

_RUNTIME_TELEMETRY_LOCK = threading.Lock()
_RUNTIME_TELEMETRY: Dict[str, Dict] = {}
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_BUCKETS: Dict[str, Dict[str, Tuple[int, float]]] = {}


app = Bottle()


def _default_runtime_telemetry() -> Dict:
    return manuscript_service.get_default_runtime_telemetry()


def _ensure_web_assets():
    missing = [name for name in REQUIRED_WEB_ASSETS if not os.path.isfile(os.path.join(WEB_DIR, name))]
    if missing:
        raise FileNotFoundError(f"Missing web assets in {WEB_DIR}: {', '.join(missing)}")


def _read_web_asset(relative_path: str) -> str:
    with open(os.path.join(WEB_DIR, relative_path), "r", encoding="utf-8") as handle:
        return handle.read()


def _render_web_template(source: str, replacements: Dict[str, str]) -> str:
    rendered = source
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _normalize_session_id(raw_value: str) -> str:
    candidate = str(raw_value or "").strip()
    if not candidate:
        return ""
    safe = []
    for char in candidate:
        if char.isalnum() or char in ("-", "_"):
            safe.append(char)
    return "".join(safe)[:128]


def _is_https_request() -> bool:
    forwarded = str(request.get_header("X-Forwarded-Proto", "") or "").strip().lower()
    if forwarded in ("https", "wss"):
        return True
    try:
        if request.urlparts and str(request.urlparts.scheme).lower() == "https":
            return True
    except Exception:
        return False
    return False


def _json_response(payload: Dict, status: int = 200, session_id: str = "", clear_session: bool = False) -> HTTPResponse:
    safe_payload = _json_safe(payload)
    http_response = HTTPResponse(
        status=status,
        body=json.dumps(safe_payload, ensure_ascii=False, allow_nan=False),
        headers={"Content-Type": "application/json"},
    )

    if session_id:
        http_response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            path="/",
            httponly=True,
            samesite="Lax",
            secure=_is_https_request(),
            max_age=SESSION_TTL_HOURS * 3600,
        )

    if clear_session:
        http_response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        http_response.delete_cookie(SESSION_COOKIE_ALT_NAME, path="/")

    return http_response


def _json_safe(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return str(value)
    return str(value)


def _read_json_payload() -> Dict:
    raw_body = request.body.read()
    if not raw_body:
        return {}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _get_client_ip() -> str:
    forwarded = str(request.get_header("X-Forwarded-For", "") or "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:128]
    return str(request.environ.get("REMOTE_ADDR", "") or "").strip()[:128]


def _is_production_env() -> bool:
    env = str(os.getenv("MANUSCRIPT_EDITOR_ENV", "") or "").strip().lower()
    return env in ("prod", "production")


def _validate_startup_config():
    if not _is_production_env():
        return
    errors = []
    if not GOOGLE_CLIENT_ID:
        errors.append("GOOGLE_CLIENT_ID is required in production.")
    if ENABLE_LOCAL_MANUAL_LOGIN:
        errors.append("MANUSCRIPT_EDITOR_LOCAL_LOGIN must be disabled in production.")
    if LOCAL_MANUAL_LOGIN_PASSWORD.strip().lower() in ("password", "admin", "changeme", ""):
        errors.append("MANUSCRIPT_EDITOR_LOCAL_LOGIN_PASSWORD must not use weak/default values.")
    if not DATABASE_URL:
        errors.append("DATABASE_URL should be configured explicitly in production.")
    if errors:
        raise RuntimeError("Startup configuration validation failed: " + " ".join(errors))


def _prune_rate_bucket(bucket: Dict[str, Tuple[int, float]], now_ts: float):
    stale_keys = [key for key, value in bucket.items() if float(value[1]) <= now_ts]
    for key in stale_keys:
        bucket.pop(key, None)


def _check_rate_limit(bucket_name: str, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
    now_ts = time.time()
    expires_at = now_ts + max(1, int(window_seconds))
    token = str(key or "").strip()[:256]
    if not token:
        token = "unknown"
    with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_BUCKETS.get(bucket_name)
        if bucket is None:
            bucket = {}
            _RATE_LIMIT_BUCKETS[bucket_name] = bucket
        _prune_rate_bucket(bucket, now_ts)
        current_count, current_expiry = bucket.get(token, (0, 0.0))
        if float(current_expiry) <= now_ts:
            current_count = 0
            current_expiry = expires_at
        if int(current_count) >= int(limit):
            retry_after = max(1, int(round(float(current_expiry) - now_ts)))
            return False, retry_after
        bucket[token] = (int(current_count) + 1, float(current_expiry or expires_at))
    return True, 0


def _is_allowed_origin() -> bool:
    origin = str(request.get_header("Origin", "") or "").strip().lower()
    referer = str(request.get_header("Referer", "") or "").strip().lower()
    if not origin and not referer:
        return (not _is_production_env()) or _is_local_request()
    allowed = set(ALLOWED_ORIGINS)
    host = str(request.get_header("Host", "") or "").strip().lower()
    if host:
        scheme = "https" if _is_https_request() else "http"
        allowed.add(f"{scheme}://{host}")
    if origin and origin in allowed:
        return True
    if referer:
        for allowed_origin in allowed:
            if referer.startswith(allowed_origin + "/") or referer == allowed_origin:
                return True
    return False


def _get_user_agent() -> str:
    return str(request.get_header("User-Agent", "") or "").strip()[:512]


def _is_local_request() -> bool:
    ip = _get_client_ip().strip().lower()
    if not ip:
        return False
    if ip in ("127.0.0.1", "::1", "localhost"):
        return True
    if ip.startswith("127."):
        return True
    if ip.startswith("::ffff:127."):
        return True
    return False


def _is_local_manual_login_allowed() -> bool:
    return ENABLE_LOCAL_MANUAL_LOGIN and _is_local_request()


def _read_cookie_value_from_header(cookie_name: str) -> str:
    raw_cookie = str(request.environ.get("HTTP_COOKIE", "") or "")
    if not raw_cookie:
        return ""
    target = str(cookie_name or "").strip()
    if not target:
        return ""
    last_value = ""
    for piece in raw_cookie.split(";"):
        token = piece.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key.strip() == target:
            last_value = value.strip()
    return _normalize_session_id(last_value)


def _get_session_id_from_request() -> str:
    header_sid = _normalize_session_id(request.environ.get(SESSION_HEADER_NAME, ""))
    # Prefer raw Cookie header parsing so duplicate-cookie edge cases pick the most recent value.
    cookie_sid = _read_cookie_value_from_header(SESSION_COOKIE_NAME) or _normalize_session_id(
        request.get_cookie(SESSION_COOKIE_NAME) or ""
    )
    alt_cookie_sid = _read_cookie_value_from_header(SESSION_COOKIE_ALT_NAME) or _normalize_session_id(
        request.get_cookie(SESSION_COOKIE_ALT_NAME) or ""
    )
    # Prefer canonical cookie, then alternate cookie, then header fallback.
    return cookie_sid or alt_cookie_sid or header_sid


def _auth_context_from_request() -> Optional[SessionContext]:
    return request.environ.get("manuscript_editor.auth")


def _public_user_payload(context: SessionContext) -> Dict:
    return {
        "id": context.user_id,
        "email": context.email,
        "display_name": context.display_name,
        "role": context.role,
        "status": context.status,
    }


def _record_audit(
    *,
    event_type: str,
    actor_user_id: str = "",
    target_user_id: str = "",
    entity_type: str = "",
    entity_id: str = "",
    metadata: Optional[Dict] = None,
):
    try:
        _STORE.record_audit_event(
            event_type=event_type,
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata or {},
            ip_address=_get_client_ip(),
            user_agent=_get_user_agent(),
        )
    except Exception:
        # Audit failures should not block user flow.
        pass


def _error_payload(code: str, message: str, **extra) -> Dict:
    payload = {"success": False, "error": message, "error_code": code}
    payload.update(extra)
    return payload


def _default_global_runtime_settings() -> Dict:
    return {
        "editing": {
            "spelling": True,
            "sentence_case": True,
            "punctuation": True,
            "chicago_style": True,
            "cmos_strict_mode": True,
            "online_reference_validation": True,
            "online_reference_serper_fallback": True,
            "online_reference_validation_admin_cap": 150,
            "auto_resolve_unresolved_references": True,
            "autopilot_auto_heal_bibliography": True,
            "autopilot_heal_when_reference_issues_at_least": 1,
            "autopilot_min_overall_confidence_for_autocomplete": 0.72,
            "autopilot_min_reference_confidence_for_autoheal": 0.62,
            "doi_insertion_mode": "balanced",
            "domain_profile": "auto",
            "cmos_profile": "strict",
            "editing_mode": "copyedit",
            "tone": "neutral",
            "rewrite_strength": "minimal",
            "explain_edits": False,
            "custom_terms": [],
        },
        "ai": {
            "enabled": True,
            "provider": "ollama",
            "model": "llama3.1",
            "ollama_host": "http://localhost:11434",
            "gemini_api_key": "",
            "openrouter_api_key": "",
            "agent_router_api_key": "",
            "ai_first_cmos": False,
            "section_wise": True,
            "section_threshold_chars": 12000,
            "section_threshold_paragraphs": 90,
            "section_chunk_chars": 5500,
            "section_chunk_lines": 28,
            "global_consistency_max_chars": 18000,
            "ollama_generate_timeout_seconds": 60,
            "ollama_health_timeout_seconds": 5,
            "ollama_retry_count": 0,
            "ollama_retry_backoff_seconds": 0,
            "ollama_fallback_model_retry": True,
        },
    }


def _normalize_custom_terms(raw_value) -> list:
    if isinstance(raw_value, str):
        pieces = re.split(r"[\n,;]+", raw_value)
    elif isinstance(raw_value, (list, tuple)):
        pieces = list(raw_value)
    else:
        pieces = []
    seen = set()
    out = []
    for piece in pieces:
        token = str(piece or "").strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(token[:120])
        if len(out) >= 500:
            break
    return out


def _normalize_global_runtime_settings(raw_value) -> Dict:
    defaults = _default_global_runtime_settings()
    raw = raw_value if isinstance(raw_value, dict) else {}
    editing_in = raw.get("editing", {}) if isinstance(raw.get("editing"), dict) else {}
    ai_in = raw.get("ai", {}) if isinstance(raw.get("ai"), dict) else {}

    def _bool(src: Dict, key: str, fallback: bool) -> bool:
        return bool(src.get(key, fallback))

    def _int(src: Dict, key: str, fallback: int, min_value: int, max_value: int) -> int:
        try:
            parsed = int(src.get(key, fallback))
        except Exception:
            parsed = int(fallback)
        return max(min_value, min(max_value, parsed))

    def _float(src: Dict, key: str, fallback: float, min_value: float, max_value: float) -> float:
        try:
            parsed = float(src.get(key, fallback))
        except Exception:
            parsed = float(fallback)
        return max(min_value, min(max_value, parsed))

    domain = str(editing_in.get("domain_profile", defaults["editing"]["domain_profile"]) or "auto").strip().lower()
    if domain not in ("auto", "general", "medical", "engineering", "law"):
        domain = "auto"
    cmos_profile = str(editing_in.get("cmos_profile", defaults["editing"]["cmos_profile"]) or "strict").strip().lower()
    if cmos_profile not in ("core", "strict", "journal_custom"):
        cmos_profile = "strict"
    doi_mode = str(editing_in.get("doi_insertion_mode", defaults["editing"]["doi_insertion_mode"]) or "balanced").strip().lower()
    if doi_mode not in ("strict", "balanced"):
        doi_mode = "balanced"
    editing_mode = str(editing_in.get("editing_mode", defaults["editing"]["editing_mode"]) or "copyedit").strip().lower()
    if editing_mode not in ("proofread", "copyedit", "clarity", "tone_adjust", "concise"):
        editing_mode = "copyedit"
    tone = str(editing_in.get("tone", defaults["editing"]["tone"]) or "neutral").strip().lower()
    if tone not in ("neutral", "formal", "informal", "academic", "business", "technical", "marketing", "legal", "casual"):
        tone = "neutral"
    rewrite_strength = str(editing_in.get("rewrite_strength", defaults["editing"]["rewrite_strength"]) or "minimal").strip().lower()
    if rewrite_strength not in ("minimal", "moderate"):
        rewrite_strength = "minimal"

    provider = str(ai_in.get("provider", defaults["ai"]["provider"]) or "ollama").strip().lower()
    if provider not in ("ollama", "gemini", "openrouter", "agent_router"):
        provider = "ollama"

    return {
        "editing": {
            "spelling": _bool(editing_in, "spelling", defaults["editing"]["spelling"]),
            "sentence_case": _bool(editing_in, "sentence_case", defaults["editing"]["sentence_case"]),
            "punctuation": _bool(editing_in, "punctuation", defaults["editing"]["punctuation"]),
            "chicago_style": _bool(editing_in, "chicago_style", defaults["editing"]["chicago_style"]),
            "cmos_strict_mode": _bool(editing_in, "cmos_strict_mode", defaults["editing"]["cmos_strict_mode"]),
            "online_reference_validation": _bool(
                editing_in,
                "online_reference_validation",
                defaults["editing"]["online_reference_validation"],
            ),
            "online_reference_serper_fallback": _bool(
                editing_in,
                "online_reference_serper_fallback",
                defaults["editing"]["online_reference_serper_fallback"],
            ),
            "online_reference_validation_admin_cap": _int(
                editing_in,
                "online_reference_validation_admin_cap",
                defaults["editing"]["online_reference_validation_admin_cap"],
                1,
                500,
            ),
            "auto_resolve_unresolved_references": _bool(
                editing_in,
                "auto_resolve_unresolved_references",
                defaults["editing"]["auto_resolve_unresolved_references"],
            ),
            "autopilot_auto_heal_bibliography": _bool(
                editing_in,
                "autopilot_auto_heal_bibliography",
                defaults["editing"]["autopilot_auto_heal_bibliography"],
            ),
            "autopilot_heal_when_reference_issues_at_least": _int(
                editing_in,
                "autopilot_heal_when_reference_issues_at_least",
                defaults["editing"]["autopilot_heal_when_reference_issues_at_least"],
                0,
                200,
            ),
            "autopilot_min_overall_confidence_for_autocomplete": _float(
                editing_in,
                "autopilot_min_overall_confidence_for_autocomplete",
                defaults["editing"]["autopilot_min_overall_confidence_for_autocomplete"],
                0.0,
                1.0,
            ),
            "autopilot_min_reference_confidence_for_autoheal": _float(
                editing_in,
                "autopilot_min_reference_confidence_for_autoheal",
                defaults["editing"]["autopilot_min_reference_confidence_for_autoheal"],
                0.0,
                1.0,
            ),
            "doi_insertion_mode": doi_mode,
            "domain_profile": domain,
            "cmos_profile": cmos_profile,
            "editing_mode": editing_mode,
            "tone": tone,
            "rewrite_strength": rewrite_strength,
            "explain_edits": _bool(editing_in, "explain_edits", defaults["editing"]["explain_edits"]),
            "custom_terms": _normalize_custom_terms(editing_in.get("custom_terms", defaults["editing"]["custom_terms"])),
        },
        "ai": {
            "enabled": _bool(ai_in, "enabled", defaults["ai"]["enabled"]),
            "provider": provider,
            "model": str(ai_in.get("model", defaults["ai"]["model"]) or defaults["ai"]["model"]).strip()[:120],
            "ollama_host": str(ai_in.get("ollama_host", defaults["ai"]["ollama_host"]) or defaults["ai"]["ollama_host"]).strip()[:300],
            "gemini_api_key": str(ai_in.get("gemini_api_key", defaults["ai"]["gemini_api_key"]) or "").strip(),
            "openrouter_api_key": str(ai_in.get("openrouter_api_key", defaults["ai"]["openrouter_api_key"]) or "").strip(),
            "agent_router_api_key": str(ai_in.get("agent_router_api_key", defaults["ai"]["agent_router_api_key"]) or "").strip(),
            "ai_first_cmos": _bool(ai_in, "ai_first_cmos", defaults["ai"]["ai_first_cmos"]),
            "section_wise": _bool(ai_in, "section_wise", defaults["ai"]["section_wise"]),
            "section_threshold_chars": _int(ai_in, "section_threshold_chars", defaults["ai"]["section_threshold_chars"], 4000, 120000),
            "section_threshold_paragraphs": _int(ai_in, "section_threshold_paragraphs", defaults["ai"]["section_threshold_paragraphs"], 20, 1000),
            "section_chunk_chars": _int(ai_in, "section_chunk_chars", defaults["ai"]["section_chunk_chars"], 1800, 30000),
            "section_chunk_lines": _int(ai_in, "section_chunk_lines", defaults["ai"]["section_chunk_lines"], 8, 200),
            "global_consistency_max_chars": _int(
                ai_in,
                "global_consistency_max_chars",
                defaults["ai"]["global_consistency_max_chars"],
                6000,
                120000,
            ),
            "ollama_generate_timeout_seconds": _float(
                ai_in,
                "ollama_generate_timeout_seconds",
                defaults["ai"]["ollama_generate_timeout_seconds"],
                1,
                600,
            ),
            "ollama_health_timeout_seconds": _float(
                ai_in,
                "ollama_health_timeout_seconds",
                defaults["ai"]["ollama_health_timeout_seconds"],
                1,
                60,
            ),
            "ollama_retry_count": _int(ai_in, "ollama_retry_count", defaults["ai"]["ollama_retry_count"], 0, 3),
            "ollama_retry_backoff_seconds": _float(
                ai_in,
                "ollama_retry_backoff_seconds",
                defaults["ai"]["ollama_retry_backoff_seconds"],
                0,
                30,
            ),
            "ollama_fallback_model_retry": _bool(
                ai_in,
                "ollama_fallback_model_retry",
                defaults["ai"]["ollama_fallback_model_retry"],
            ),
        },
    }


def _read_global_runtime_settings() -> Dict:
    row = _STORE.get_app_setting(APP_SETTING_KEY_GLOBAL_RUNTIME)
    if row and isinstance(row.get("value"), dict):
        return _normalize_global_runtime_settings(row.get("value"))
    return _default_global_runtime_settings()


def _global_runtime_settings_for_user_payload(settings: Dict) -> Dict:
    safe = _normalize_global_runtime_settings(settings)
    # Do not expose server API keys to non-admin users.
    safe["ai"]["gemini_api_key"] = ""
    safe["ai"]["openrouter_api_key"] = ""
    safe["ai"]["agent_router_api_key"] = ""
    return safe


def _apply_global_runtime_settings(request_options: Dict, runtime_settings: Dict) -> Dict:
    opts = dict(request_options or {})
    settings = _normalize_global_runtime_settings(runtime_settings or {})
    editing = settings.get("editing", {})
    ai = settings.get("ai", {})
    opts["spelling"] = bool(editing.get("spelling", True))
    opts["sentence_case"] = bool(editing.get("sentence_case", True))
    opts["punctuation"] = bool(editing.get("punctuation", True))
    opts["chicago_style"] = bool(editing.get("chicago_style", True))
    opts["cmos_strict_mode"] = bool(editing.get("cmos_strict_mode", True))
    opts["online_reference_validation"] = bool(editing.get("online_reference_validation", True))
    opts["online_reference_serper_fallback"] = bool(editing.get("online_reference_serper_fallback", True))
    opts["online_reference_validation_admin_cap"] = int(editing.get("online_reference_validation_admin_cap", 150))
    opts["auto_resolve_unresolved_references"] = bool(editing.get("auto_resolve_unresolved_references", True))
    opts["automation"] = {
        "auto_heal_bibliography": bool(editing.get("autopilot_auto_heal_bibliography", True)),
        "heal_when_reference_issues_at_least": int(editing.get("autopilot_heal_when_reference_issues_at_least", 1)),
        "min_overall_confidence_for_autocomplete": float(editing.get("autopilot_min_overall_confidence_for_autocomplete", 0.72)),
        "min_reference_confidence_for_autoheal": float(editing.get("autopilot_min_reference_confidence_for_autoheal", 0.62)),
    }
    opts["doi_insertion_mode"] = str(editing.get("doi_insertion_mode", "balanced"))
    opts["domain_profile"] = str(editing.get("domain_profile", "auto"))
    opts["editing_mode"] = str(editing.get("editing_mode", "copyedit"))
    opts["tone"] = str(editing.get("tone", "neutral"))
    opts["rewrite_strength"] = str(editing.get("rewrite_strength", "minimal"))
    opts["explain_edits"] = bool(editing.get("explain_edits", False))
    resolved_cmos_profile = str(editing.get("cmos_profile", "strict"))
    if bool(editing.get("cmos_strict_mode", True)) and resolved_cmos_profile == "core":
        resolved_cmos_profile = "strict"
    opts["cmos_profile"] = resolved_cmos_profile
    opts["custom_terms"] = list(editing.get("custom_terms", []))
    opts["journal_profile"] = "vancouver_nlm"
    opts["reference_profile"] = "vancouver_nlm"
    opts["ai"] = {
        "enabled": bool(ai.get("enabled", True)),
        "provider": str(ai.get("provider", "ollama")),
        "model": str(ai.get("model", "")),
        "ollama_host": str(ai.get("ollama_host", "")),
        "api_key": str(ai.get("gemini_api_key", "")),
        "gemini_api_key": str(ai.get("gemini_api_key", "")),
        "openrouter_api_key": str(ai.get("openrouter_api_key", "")),
        "agent_router_api_key": str(ai.get("agent_router_api_key", "")),
        "ai_first_cmos": bool(ai.get("ai_first_cmos", False)),
        "section_wise": bool(ai.get("section_wise", True)),
        "section_threshold_chars": int(ai.get("section_threshold_chars", 12000)),
        "section_threshold_paragraphs": int(ai.get("section_threshold_paragraphs", 90)),
        "section_chunk_chars": int(ai.get("section_chunk_chars", 5500)),
        "section_chunk_lines": int(ai.get("section_chunk_lines", 28)),
        "global_consistency_max_chars": int(ai.get("global_consistency_max_chars", 18000)),
        "ollama_generate_timeout_seconds": float(ai.get("ollama_generate_timeout_seconds", 60)),
        "ollama_health_timeout_seconds": float(ai.get("ollama_health_timeout_seconds", 5)),
        "ollama_retry_count": int(ai.get("ollama_retry_count", 0)),
        "ollama_retry_backoff_seconds": float(ai.get("ollama_retry_backoff_seconds", 0)),
        "ollama_fallback_model_retry": bool(ai.get("ollama_fallback_model_retry", True)),
    }
    return opts


def _increment_runtime_counter(session_id: str, key: str, code: str = ""):
    sid = _normalize_session_id(session_id)
    if not sid:
        return
    with _RUNTIME_TELEMETRY_LOCK:
        telemetry = _RUNTIME_TELEMETRY.get(sid)
        if telemetry is None:
            telemetry = _default_runtime_telemetry()
            _RUNTIME_TELEMETRY[sid] = telemetry
        telemetry[key] = int(telemetry.get(key, 0)) + 1
        if code:
            bucket = telemetry.setdefault("errors_by_code", {})
            bucket[code] = int(bucket.get(code, 0)) + 1


def _increment_runtime_bucket(session_id: str, bucket_key: str, item_key: str):
    sid = _normalize_session_id(session_id)
    if not sid:
        return
    token = str(item_key or "unknown").strip().lower() or "unknown"
    with _RUNTIME_TELEMETRY_LOCK:
        telemetry = _RUNTIME_TELEMETRY.get(sid)
        if telemetry is None:
            telemetry = _default_runtime_telemetry()
            _RUNTIME_TELEMETRY[sid] = telemetry
        bucket = telemetry.setdefault(bucket_key, {})
        if not isinstance(bucket, dict):
            bucket = {}
            telemetry[bucket_key] = bucket
        bucket[token] = int(bucket.get(token, 0)) + 1


def _add_runtime_duration_sample(session_id: str, duration_seconds: float):
    sid = _normalize_session_id(session_id)
    if not sid:
        return
    try:
        seconds = max(0.0, float(duration_seconds))
    except Exception:
        return
    with _RUNTIME_TELEMETRY_LOCK:
        telemetry = _RUNTIME_TELEMETRY.get(sid)
        if telemetry is None:
            telemetry = _default_runtime_telemetry()
            _RUNTIME_TELEMETRY[sid] = telemetry
        stats = telemetry.setdefault("async_run_duration_samples", {"count": 0, "total_seconds": 0.0, "max_seconds": 0.0})
        if not isinstance(stats, dict):
            stats = {"count": 0, "total_seconds": 0.0, "max_seconds": 0.0}
            telemetry["async_run_duration_samples"] = stats
        stats["count"] = int(stats.get("count", 0)) + 1
        stats["total_seconds"] = float(stats.get("total_seconds", 0.0)) + seconds
        stats["max_seconds"] = max(float(stats.get("max_seconds", 0.0)), seconds)


def _read_runtime_telemetry(session_id: str) -> Dict:
    sid = _normalize_session_id(session_id)
    if not sid:
        return _default_runtime_telemetry()
    with _RUNTIME_TELEMETRY_LOCK:
        telemetry = _RUNTIME_TELEMETRY.get(sid)
        if telemetry is None:
            telemetry = _default_runtime_telemetry()
            _RUNTIME_TELEMETRY[sid] = telemetry
        return dict(telemetry)


def _reset_runtime_telemetry(session_id: str):
    sid = _normalize_session_id(session_id)
    if not sid:
        return
    with _RUNTIME_TELEMETRY_LOCK:
        _RUNTIME_TELEMETRY[sid] = _default_runtime_telemetry()


def _verify_google_token(raw_id_token: str) -> Dict:
    token = str(raw_id_token or "").strip()
    if not token:
        raise ValueError("Missing Google ID token")

    if ENABLE_DEV_TEST_TOKENS and token.startswith("test:"):
        email = str(token.split(":", 1)[1] or "").strip().lower()
        if "@" not in email:
            raise ValueError("Invalid test token email")
        domain = email.rsplit("@", 1)[-1]
        return {
            "sub": "test_" + hashlib.sha256(email.encode("utf-8")).hexdigest()[:24],
            "email": email,
            "email_verified": True,
            "name": email.split("@", 1)[0],
            "hd": domain,
        }

    if not GOOGLE_CLIENT_ID:
        raise RuntimeError("GOOGLE_CLIENT_ID is not configured")

    if google_id_token is None or google_requests is None:
        raise RuntimeError("google-auth package is required for Google login")

    verifier_request = google_requests.Request()
    token_info = google_id_token.verify_oauth2_token(token, verifier_request, GOOGLE_CLIENT_ID)
    if not isinstance(token_info, dict):
        raise RuntimeError("Invalid token verification response")
    return token_info


def _require_auth_context() -> Tuple[Optional[SessionContext], Optional[HTTPResponse]]:
    session_id = _get_session_id_from_request()
    if not session_id:
        return None, _json_response(_error_payload("AUTH_REQUIRED", "Authentication required"), status=401)

    context = _STORE.get_session_context(session_id)
    if context is None:
        return None, _json_response(
            _error_payload("AUTH_SESSION_INVALID", "Session expired or invalid"),
            status=401,
            clear_session=True,
        )

    if context.status != STATUS_ACTIVE:
        _STORE.revoke_session(session_id)
        return None, _json_response(
            _error_payload("AUTH_USER_INACTIVE", "User access is inactive"),
            status=403,
            clear_session=True,
        )

    request.environ["manuscript_editor.auth"] = context
    request.environ[SESSION_COOKIE_ENV_KEY] = context.session_id
    return context, None


def require_auth(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not _is_allowed_origin():
            return _json_response(_error_payload("CSRF_ORIGIN_DENIED", "Request origin is not allowed"), status=403)
        context, response = _require_auth_context()
        if response is not None:
            return response
        rate_key = f"{_get_client_ip()}:{context.user_id}:{request.path}"
        allowed, retry_after = _check_rate_limit(
            "write_authenticated",
            rate_key,
            WRITE_RATE_LIMIT_COUNT,
            WRITE_RATE_LIMIT_WINDOW_SECONDS,
        )
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not allowed:
            return _json_response(
                _error_payload(
                    "RATE_LIMITED",
                    f"Too many write requests. Retry after {retry_after} seconds.",
                    retry_after=retry_after,
                ),
                status=429,
            )
        _maybe_run_cleanup()
        return handler(*args, **kwargs)

    return wrapped


def require_admin(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not _is_allowed_origin():
            return _json_response(_error_payload("CSRF_ORIGIN_DENIED", "Request origin is not allowed"), status=403)
        context, response = _require_auth_context()
        if response is not None:
            return response

        if context.role != ROLE_ADMIN:
            _record_audit(
                event_type="admin_access_denied",
                actor_user_id=context.user_id,
                entity_type="route",
                entity_id=str(request.path or ""),
            )
            return _json_response(_error_payload("FORBIDDEN", "Admin access required"), status=403)

        _maybe_run_cleanup()
        return handler(*args, **kwargs)

    return wrapped


def _safe_file_name(raw_name: str, fallback: str = "manuscript") -> str:
    name = str(raw_name or "").strip() or fallback
    name = os.path.basename(name)
    allowed = []
    for char in name:
        if char.isalnum() or char in (".", "-", "_", " "):
            allowed.append(char)
    cleaned = "".join(allowed).strip().strip(".")
    if not cleaned:
        cleaned = fallback
    if len(cleaned) > 180:
        root, ext = os.path.splitext(cleaned)
        cleaned = root[:150] + ext[:20]
    return cleaned


def _task_dir(task_id: str) -> str:
    safe_id = _normalize_session_id(task_id) or uuid.uuid4().hex
    path = os.path.join(DATA_DIR, "tasks", safe_id)
    os.makedirs(path, exist_ok=True)
    return path


def _to_storage_relative_path(abs_path: str) -> str:
    normalized = os.path.abspath(abs_path)
    if not normalized.startswith(DATA_DIR + os.sep) and normalized != DATA_DIR:
        raise ValueError("Invalid storage path")
    rel = os.path.relpath(normalized, DATA_DIR)
    return rel.replace("\\", "/")


def _resolve_storage_path(relative_path: str) -> str:
    rel = str(relative_path or "").strip().replace("\\", "/")
    target = os.path.abspath(os.path.join(DATA_DIR, rel))
    if not target.startswith(DATA_DIR + os.sep) and target != DATA_DIR:
        raise ValueError("Path escapes data dir")
    return target


def _build_download_filename(original_file_name: str, file_type: str) -> str:
    base_name = os.path.splitext(_safe_file_name(original_file_name or "manuscript"))[0] or "manuscript"
    ft = str(file_type or "").strip().lower()
    if ft in {"clean", "highlighted", "highlighted_comments", "track_changes"}:
        prefix = ft
    else:
        prefix = "highlighted"
    return f"{prefix}_{base_name}.docx"


def _extract_docx_preview_images(source_docx_path: str, max_images: int = 20, max_bytes: int = 6 * 1024 * 1024) -> List[Dict[str, Any]]:
    """Extract embedded DOCX media images in document order for browser preview."""
    return manuscript_service.extract_docx_preview_images(source_docx_path, max_images, max_bytes)


def _build_process_payload(
    processor: DocumentProcessor,
    task_row: Dict,
    corrected_text: str,
    full_corrected_text: str,
    options: Optional[Dict] = None,
) -> Dict:
    source_docx_path = ""
    if str(task_row.get("source_type") or "").lower() == "docx":
        try:
            source_docx_path = _resolve_storage_path(str(task_row.get("source_path") or ""))
        except Exception:
            source_docx_path = ""
    return manuscript_service.build_process_payload(
        processor=processor,
        task_id=str(task_row.get("id") or ""),
        original_text=str(task_row.get("original_text") or ""),
        corrected_text=corrected_text,
        full_corrected_text=full_corrected_text,
        source_type=str(task_row.get("source_type") or ""),
        source_docx_path=source_docx_path,
        options=options,
    )


def _extract_reports_from_process_payload(process_payload: Dict) -> Dict:
    return {
        "redline_html": process_payload.get("redline_html", ""),
        "prose_only_diff": process_payload.get("prose_only_diff", ""),
        "strict_cmos_issues": process_payload.get("strict_cmos_issues") or {},
        "corrected_annotated_html": process_payload.get("corrected_annotated_html", ""),
        "corrections_report": process_payload.get("corrections_report") or {},
        "noun_report": process_payload.get("noun_report") or {},
        "domain_report": process_payload.get("domain_report") or {},
        "journal_profile_report": process_payload.get("journal_profile_report") or {},
        "citation_reference_report": process_payload.get("citation_reference_report") or {},
        "processing_audit": process_payload.get("processing_audit") or {},
        "processing_note": process_payload.get("processing_note", ""),
        "edit_explanations": process_payload.get("edit_explanations") or {},
        "docx_preview_images": process_payload.get("docx_preview_images") or [],
    }


def _store_task_export_files(task_row: Dict, original_text: str, corrected_text: str):
    task_id = str(task_row.get("id") or "")
    file_name = str(task_row.get("file_name") or "manuscript.docx")
    task_dir = _task_dir(task_id)
    processor = DocumentProcessor()
    source_docx_path = ""
    if str(task_row.get("source_type") or "").lower() == "docx":
        try:
            source_docx_path = _resolve_storage_path(str(task_row.get("source_path") or ""))
        except Exception:
            source_docx_path = ""

    expires_at = int(time.time()) + FILE_RETENTION_DAYS * 24 * 3600
    modes = ["clean", "highlighted", "highlighted_comments", "track_changes"]
    print(f"[EXPORT] Generating {len(modes)} variants for task={task_id} source_docx={'yes' if source_docx_path else 'no'}")

    for mode in modes:
        mode_abs = os.path.join(task_dir, f"{mode}.docx")
        try:
            manuscript_service.generate_docx_file(
                processor=processor,
                original_text=original_text,
                corrected_text=corrected_text,
                file_type=mode,
                dest_path=mode_abs,
                source_docx_path=source_docx_path,
            )
            mode_rel = _to_storage_relative_path(mode_abs)
            _STORE.upsert_task_file(
                task_id=task_id,
                file_type=mode,
                storage_path=mode_rel,
                download_name=_build_download_filename(file_name, mode),
                mime_type=MIME_DOCX,
                size_bytes=os.path.getsize(mode_abs),
                expires_at=expires_at,
            )
            print(f"[EXPORT] OK  mode={mode} size={os.path.getsize(mode_abs)} bytes")
        except Exception as _mode_exc:  # noqa: BLE001
            import traceback as _tb
            print(f"[EXPORT] FAIL mode={mode} error={_mode_exc}")
            _tb.print_exc()


def _task_summary(task_row: Dict) -> Dict:
    status = str(task_row.get("status") or "")
    downloadable = status in {"PROCESSED", "REVIEW_REQUIRED"}
    return {
        "id": str(task_row.get("id") or ""),
        "file_name": str(task_row.get("file_name") or ""),
        "status": status,
        "word_count": int(task_row.get("word_count") or 0),
        "source_type": str(task_row.get("source_type") or "text"),
        "created_at": int(task_row.get("created_at") or 0),
        "updated_at": int(task_row.get("updated_at") or 0),
        "processed_at": int(task_row.get("processed_at") or 0),
        "can_download_clean": downloadable,
        "can_download_highlighted": downloadable,
        "can_download_highlighted_comments": downloadable,
        "can_download_track_changes": downloadable,
    }


def _get_owned_task_or_error(context: SessionContext, task_id: str) -> Tuple[Optional[Dict], Optional[HTTPResponse]]:
    task = _STORE.get_task_for_user(
        task_id=str(task_id or "").strip(),
        user_id=context.user_id,
        is_admin=context.role == ROLE_ADMIN,
    )
    if task is None:
        return None, _json_response(_error_payload("TASK_NOT_FOUND", "Task not found"), status=404)
    return task, None


def _upload_text_to_task(context: SessionContext, file_name: str, text: str, source_type: str, source_bytes: bytes = b"") -> Dict:
    safe_name = _safe_file_name(file_name, "manuscript.txt")
    task_id = uuid.uuid4().hex
    task_dir = _task_dir(task_id)
    ext = ".docx" if source_type == "docx" else ".txt"
    source_abs = os.path.join(task_dir, "source" + ext)

    if source_type == "docx":
        with open(source_abs, "wb") as outfile:
            outfile.write(source_bytes)
    else:
        with open(source_abs, "w", encoding="utf-8") as outfile:
            outfile.write(text)

    relative_source = _to_storage_relative_path(source_abs)

    task = _STORE.create_task(
        task_id=task_id,
        user_id=context.user_id,
        file_name=safe_name,
        source_type=source_type,
        source_path=relative_source,
        original_text=text,
        options={},
    )

    _record_audit(
        event_type="task_uploaded",
        actor_user_id=context.user_id,
        entity_type="task",
        entity_id=task_id,
        metadata={
            "file_name": safe_name,
            "source_type": source_type,
            "word_count": len(text.split()),
        },
    )

    return {
        "success": True,
        "task_id": task_id,
        "text": text,
        "word_count": len(text.split()),
        "file_name": safe_name,
        "task": _task_summary(task),
    }


def _upload_docx_to_task(context: SessionContext, file_name: str, byte_data: bytes) -> Dict:
    """Decode DOCX bytes, extract text, and persist as a DOCX-backed task."""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as handle:
            handle.write(byte_data)
            temp_path = handle.name

        processor = DocumentProcessor()
        text, _ = processor.load_document(temp_path)
        return _upload_text_to_task(
            context,
            file_name=file_name,
            text=text,
            source_type="docx",
            source_bytes=byte_data,
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def _process_task(context: SessionContext, task: Dict, options: Dict) -> Dict:
    _increment_runtime_counter(context.session_id, "process_runs_started")
    processor = DocumentProcessor()
    task_id = str(task.get("id") or "")
    def progress_callback(progress_percent: float, stage: str, tokens_consumed: int = 0, estimated_seconds_remaining: int = 0):
        if task_id:
            _PROCESSING_JOB_QUEUE.update_progress(
                task_id=task_id,
                progress_percent=progress_percent,
                stage=stage,
                tokens_consumed=tokens_consumed,
                estimated_seconds_remaining=estimated_seconds_remaining
            )
    processor.set_progress_callback(progress_callback)
    original_text = str(task.get("original_text") or "")
    processing_source_text = original_text
    safe_options = dict(options or {})
    if bool(safe_options.get("unresolved_reference_only", False)):
        processing_source_text = (
            str(task.get("full_corrected_text") or "")
            or str(task.get("corrected_text") or "")
            or original_text
        )
        # Focus this mode on reference cleanup speed/safety.
        safe_options["spelling"] = False
        safe_options["sentence_case"] = False
        safe_options["punctuation"] = False
        safe_options["chicago_style"] = True
        ai_opts = safe_options.get("ai", {}) if isinstance(safe_options.get("ai"), dict) else {}
        ai_opts["enabled"] = False
        safe_options["ai"] = ai_opts

    full_corrected_text = processor.process_text(processing_source_text, safe_options)
    corrected_text = full_corrected_text

    process_payload = _build_process_payload(
        processor=processor,
        task_row=task,
        corrected_text=corrected_text,
        full_corrected_text=full_corrected_text,
        options=safe_options,
    )

    try:
        _append_reference_unresolved_trend_sample(task=task, process_payload=process_payload)
    except Exception:
        pass

    reports = _extract_reports_from_process_payload(process_payload)
    updated = _STORE.update_task_processing_result(
        task_id=str(task.get("id") or ""),
        user_id=context.user_id,
        corrected_text=corrected_text,
        full_corrected_text=full_corrected_text,
        word_count=process_payload["word_count"],
        options=safe_options,
        reports=reports,
    )
    if updated is None:
        raise RuntimeError("Task update failed")

    _store_task_export_files(updated, original_text=original_text, corrected_text=corrected_text)

    _record_audit(
        event_type="task_processed",
        actor_user_id=context.user_id,
        entity_type="task",
        entity_id=str(task.get("id") or ""),
        metadata={
            "word_count": process_payload["word_count"],
            "unresolved_reference_only": bool(safe_options.get("unresolved_reference_only", False)),
            "editing_mode": str(safe_options.get("editing_mode") or "copyedit"),
            "tone": str(safe_options.get("tone") or "neutral"),
            "rewrite_strength": str(safe_options.get("rewrite_strength") or "minimal"),
            "explain_edits": bool(safe_options.get("explain_edits", False)),
            "processing_mode": str(((process_payload.get("processing_audit") or {}).get("mode") or "unknown")),
        },
    )

    _increment_runtime_counter(context.session_id, "process_runs_succeeded")
    _increment_runtime_bucket(context.session_id, "editing_mode_counts", str(safe_options.get("editing_mode") or "copyedit"))
    _increment_runtime_bucket(context.session_id, "tone_counts", str(safe_options.get("tone") or "neutral"))
    _increment_runtime_bucket(context.session_id, "rewrite_strength_counts", str(safe_options.get("rewrite_strength") or "minimal"))
    _increment_runtime_bucket(context.session_id, "explain_edits_counts", "enabled" if bool(safe_options.get("explain_edits", False)) else "disabled")
    processing_audit = process_payload.get("processing_audit", {}) if isinstance(process_payload, dict) else {}
    summary = processing_audit.get("summary", {}) if isinstance(processing_audit.get("summary"), dict) else {}
    _increment_runtime_bucket(context.session_id, "mode_counts", str(processing_audit.get("mode") or "unknown"))
    fallback_reason_counts = summary.get("fallback_reason_counts", {}) if isinstance(summary.get("fallback_reason_counts"), dict) else {}
    for reason_key, reason_count in fallback_reason_counts.items():
        try:
            count = max(0, int(reason_count))
        except Exception:
            count = 0
        for _ in range(count):
            _increment_runtime_bucket(context.session_id, "fallback_reason_counts", str(reason_key or "unknown"))

    return process_payload


def _heal_bibliography_task(context: SessionContext, task: Dict, options: Dict) -> Dict:
    _increment_runtime_counter(context.session_id, "heal_bibliography_started")
    processor = DocumentProcessor()
    task_id = str(task.get("id") or "")
    def progress_callback(progress_percent: float, stage: str, tokens_consumed: int = 0, estimated_seconds_remaining: int = 0):
        if task_id:
            _PROCESSING_JOB_QUEUE.update_progress(
                task_id=task_id,
                progress_percent=progress_percent,
                stage=stage,
                tokens_consumed=tokens_consumed,
                estimated_seconds_remaining=estimated_seconds_remaining
            )
    processor.set_progress_callback(progress_callback)

    source_text = (
        str(task.get("full_corrected_text") or "")
        or str(task.get("corrected_text") or "")
        or str(task.get("original_text") or "")
    )

    progress_callback(10.0, "Initializing Bibliography Healing Engine...")

    healed_text = processor.editor.heal_bibliography(source_text, options, progress_callback=progress_callback)

    progress_callback(90.0, "Updating document metadata & reports...")

    process_payload = _build_process_payload(
        processor=processor,
        task_row=task,
        corrected_text=healed_text,
        full_corrected_text=healed_text,
        options=options,
    )

    reports = _extract_reports_from_process_payload(process_payload)

    reports["healing_audit"] = {
        "status": "healed",
        "timestamp": int(time.time()),
        "original_length": len(source_text),
        "healed_length": len(healed_text)
    }

    updated = _STORE.update_task_processing_result(
        task_id=task_id,
        user_id=context.user_id,
        corrected_text=healed_text,
        full_corrected_text=healed_text,
        word_count=process_payload["word_count"],
        options=options,
        reports=reports,
    )
    if updated is None:
        raise RuntimeError("Task update failed during healing")

    _store_task_export_files(updated, original_text=str(task.get("original_text") or ""), corrected_text=healed_text)

    _record_audit(
        event_type="task_healed",
        actor_user_id=context.user_id,
        entity_type="task",
        entity_id=task_id,
        metadata={
            "word_count": process_payload["word_count"],
            "original_length": len(source_text),
            "healed_length": len(healed_text)
        },
    )

    _increment_runtime_counter(context.session_id, "heal_bibliography_succeeded")

    return process_payload


def _count_reference_issues_from_payload(process_payload: Dict) -> int:
    report = process_payload.get("citation_reference_report") if isinstance(process_payload, dict) else {}
    if not isinstance(report, dict):
        return 0

    for key in ("issue_count", "issues_count", "unresolved_count", "total_issues"):
        try:
            value = int(report.get(key, 0) or 0)
            if value > 0:
                return value
        except Exception:
            continue

    issues = report.get("issues")
    if isinstance(issues, list):
        return len(issues)
    return 0


def _count_citation_issues_from_payload(process_payload: Dict) -> int:
    report = process_payload.get("citation_reference_report") if isinstance(process_payload, dict) else {}
    if not isinstance(report, dict):
        return 0
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    for key in ("issue_total", "citation_issues", "total_issues"):
        try:
            value = int(summary.get(key, 0) or 0)
            if value > 0:
                return value
        except Exception:
            continue
    for key in ("issue_total", "issues_count"):
        try:
            value = int(report.get(key, 0) or 0)
            if value > 0:
                return value
        except Exception:
            continue
    return 0


def _compute_autopilot_confidence(process_payload: Dict) -> Dict:
    processing_audit = process_payload.get("processing_audit") if isinstance(process_payload, dict) else {}
    summary = processing_audit.get("summary") if isinstance(processing_audit, dict) and isinstance(processing_audit.get("summary"), dict) else {}
    note = str(process_payload.get("processing_note") or "").lower()

    total_sections = max(1, int(summary.get("total_sections", 1) or 1))
    fallback_sections = max(0, int(summary.get("fallback_sections", 0) or 0))
    fallback_ratio = min(1.0, float(fallback_sections) / float(total_sections))
    language_confidence = max(0.0, min(1.0, 1.0 - (fallback_ratio * 0.65)))
    if "fallback" in note:
        language_confidence = max(0.0, language_confidence - 0.08)

    reference_issues = max(0, _count_reference_issues_from_payload(process_payload))
    citation_issues = max(0, _count_citation_issues_from_payload(process_payload))

    reference_confidence = max(0.0, min(1.0, 1.0 - (min(reference_issues, 12) / 12.0)))
    citation_integrity_confidence = max(0.0, min(1.0, 1.0 - (min(citation_issues, 12) / 12.0)))

    overall = (
        (language_confidence * 0.45)
        + (reference_confidence * 0.30)
        + (citation_integrity_confidence * 0.25)
    )
    overall = max(0.0, min(1.0, overall))

    return {
        "language_confidence": round(language_confidence, 4),
        "reference_confidence": round(reference_confidence, 4),
        "citation_integrity_confidence": round(citation_integrity_confidence, 4),
        "overall_autopilot_confidence": round(overall, 4),
        "reference_issue_count": reference_issues,
        "citation_issue_count": citation_issues,
    }


def _persist_autopilot_audit(
    *,
    context: SessionContext,
    task_id: str,
    process_payload: Dict,
    autopilot_audit: Dict,
) -> None:
    if not task_id:
        return
    task_row = _STORE.get_task_for_user(
        task_id=task_id,
        user_id=context.user_id,
        is_admin=context.role == ROLE_ADMIN,
    )
    if not isinstance(task_row, dict):
        return

    reports = _extract_reports_from_process_payload(process_payload)
    reports["autopilot_audit"] = autopilot_audit

    corrected_text = str(task_row.get("corrected_text") or process_payload.get("text") or "")
    full_corrected_text = str(task_row.get("full_corrected_text") or process_payload.get("full_corrected_text") or corrected_text)
    options = task_row.get("options") if isinstance(task_row.get("options"), dict) else {}
    word_count = int(task_row.get("word_count") or process_payload.get("word_count") or len(corrected_text.split()))

    _STORE.update_task_processing_result(
        task_id=task_id,
        user_id=context.user_id,
        corrected_text=corrected_text,
        full_corrected_text=full_corrected_text,
        word_count=word_count,
        options=options,
        reports=reports,
    )


def _autopilot_task(context: SessionContext, task: Dict, options: Dict) -> Dict:
    """Run an autonomous processing pipeline with policy-based gates."""
    effective_options = copy.deepcopy(options) if isinstance(options, dict) else {}
    automation = effective_options.get("automation") if isinstance(effective_options.get("automation"), dict) else {}

    process_options = copy.deepcopy(effective_options)
    process_options.pop("automation", None)
    process_options.setdefault("spelling", True)
    process_options.setdefault("sentence_case", True)
    process_options.setdefault("punctuation", True)
    process_options.setdefault("chicago_style", True)
    process_options.setdefault("editing_mode", "copyedit")
    process_options.setdefault("rewrite_strength", "minimal")
    process_options.setdefault("tone", "neutral")
    process_options.setdefault("online_reference_validation", True)

    auto_heal_enabled = bool(automation.get("auto_heal_bibliography", True))
    try:
        heal_threshold = int(automation.get("heal_when_reference_issues_at_least", 1) or 1)
    except Exception:
        heal_threshold = 1
    heal_threshold = max(0, heal_threshold)
    try:
        min_overall_confidence = float(automation.get("min_overall_confidence_for_autocomplete", 0.72) or 0.72)
    except Exception:
        min_overall_confidence = 0.72
    try:
        min_reference_confidence_for_autoheal = float(automation.get("min_reference_confidence_for_autoheal", 0.62) or 0.62)
    except Exception:
        min_reference_confidence_for_autoheal = 0.62
    min_overall_confidence = max(0.0, min(1.0, min_overall_confidence))
    min_reference_confidence_for_autoheal = max(0.0, min(1.0, min_reference_confidence_for_autoheal))

    process_payload = _process_task(context, task, process_options)
    process_confidence = _compute_autopilot_confidence(process_payload)
    issue_count = _count_reference_issues_from_payload(process_payload)
    should_heal = bool(
        auto_heal_enabled
        and issue_count >= heal_threshold
        and float(process_confidence.get("reference_confidence", 0.0)) >= min_reference_confidence_for_autoheal
    )
    decision_reasons: List[str] = []
    if not auto_heal_enabled:
        decision_reasons.append("auto_heal_disabled_by_policy")
    elif issue_count < heal_threshold:
        decision_reasons.append("reference_issues_below_heal_threshold")
    elif float(process_confidence.get("reference_confidence", 0.0)) < min_reference_confidence_for_autoheal:
        decision_reasons.append("reference_confidence_below_autoheal_threshold")
    else:
        decision_reasons.append("healing_gate_passed")

    healed_payload = None
    if should_heal:
        latest_task = _STORE.get_task_for_user(
            task_id=str(task.get("id") or ""),
            user_id=context.user_id,
            is_admin=context.role == ROLE_ADMIN,
        ) or task
        heal_options = copy.deepcopy(process_options)
        heal_options["online_reference_validation"] = True
        healed_payload = _heal_bibliography_task(context, latest_task, heal_options)

    final_payload = healed_payload if isinstance(healed_payload, dict) else process_payload
    final_confidence = _compute_autopilot_confidence(final_payload)
    requires_review = float(final_confidence.get("overall_autopilot_confidence", 0.0)) < min_overall_confidence
    if requires_review:
        decision_reasons.append("overall_confidence_below_autocomplete_threshold")
    else:
        decision_reasons.append("overall_confidence_meets_autocomplete_threshold")

    autopilot_audit = {
        "status": "completed",
        "timestamp": int(time.time()),
        "process_executed": True,
        "auto_heal_bibliography": auto_heal_enabled,
        "heal_threshold_reference_issues": heal_threshold,
        "min_overall_confidence_for_autocomplete": round(min_overall_confidence, 4),
        "min_reference_confidence_for_autoheal": round(min_reference_confidence_for_autoheal, 4),
        "reference_issue_count": int(final_confidence.get("reference_issue_count", issue_count)),
        "citation_issue_count": int(final_confidence.get("citation_issue_count", 0)),
        "heal_executed": bool(healed_payload is not None),
        "review_required": requires_review,
        "decision_reasons": decision_reasons,
        "confidence": final_confidence,
        "effective_options": {
            "editing_mode": str(process_options.get("editing_mode") or "copyedit"),
            "rewrite_strength": str(process_options.get("rewrite_strength") or "minimal"),
            "tone": str(process_options.get("tone") or "neutral"),
            "chicago_style": bool(process_options.get("chicago_style", True)),
            "online_reference_validation": bool(process_options.get("online_reference_validation", True)),
        },
    }
    _persist_autopilot_audit(
        context=context,
        task_id=str(task.get("id") or ""),
        process_payload=final_payload,
        autopilot_audit=autopilot_audit,
    )
    if requires_review:
        _STORE.update_task_status(
            task_id=str(task.get("id") or ""),
            status="REVIEW_REQUIRED",
            user_id=context.user_id,
            is_admin=context.role == ROLE_ADMIN,
        )

    return {
        "success": True,
        "task_id": str(task.get("id") or ""),
        "status": "AUTOPILOT_REVIEW_REQUIRED" if requires_review else "AUTOPILOT_COMPLETED",
        "autopilot": autopilot_audit,
        "result": final_payload,
    }


def _append_reference_unresolved_trend_sample(task: Dict, process_payload: Dict) -> None:
    """Store lightweight unresolved-reference trend sample for admin diagnostics."""
    report = process_payload.get("citation_reference_report", {}) if isinstance(process_payload, dict) else {}
    if not isinstance(report, dict):
        return
    online = report.get("online_validation", {}) if isinstance(report.get("online_validation"), dict) else {}
    enrichment = online.get("enrichment", {}) if isinstance(online.get("enrichment"), dict) else {}
    trail = enrichment.get("trail", []) if isinstance(enrichment.get("trail"), list) else []
    entries = online.get("entries", []) if isinstance(online.get("entries"), list) else []

    unresolved_by_source: Dict[str, int] = {}
    unresolved_by_reason: Dict[str, int] = {}
    unresolved_total = 0

    for item in trail:
        if not isinstance(item, dict):
            continue
        autofill_status = str(item.get("autofill_status") or "none").strip().lower()
        doi_rejected = bool(item.get("doi_rejected"))
        doi_needs_review = bool(item.get("doi_needs_review"))
        unresolved = autofill_status != "full" or doi_rejected or doi_needs_review
        if not unresolved:
            continue
        unresolved_total += 1
        source_name = str(item.get("source") or "unknown").strip().lower() or "unknown"
        unresolved_by_source[source_name] = int(unresolved_by_source.get(source_name, 0)) + 1
        reason = str(item.get("why_manual_review") or "").strip().lower()
        if not reason:
            chips = item.get("autofill_chips", []) if isinstance(item.get("autofill_chips"), list) else []
            reason = str(chips[0] if chips else "autofill_not_full").strip().lower()
        unresolved_by_reason[reason] = int(unresolved_by_reason.get(reason, 0)) + 1

    for item in entries:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status not in {"not_found", "mismatch", "ambiguous", "error"}:
            continue
        unresolved_total += 1
        source_name = str(item.get("source") or "unknown").strip().lower() or "unknown"
        unresolved_by_source[source_name] = int(unresolved_by_source.get(source_name, 0)) + 1
        reason = str(item.get("reason") or status).strip().lower() or status
        unresolved_by_reason[reason] = int(unresolved_by_reason.get(reason, 0)) + 1

    sample = {
        "timestamp": int(time.time()),
        "task_id": str(task.get("id") or ""),
        "task_name": str(task.get("file_name") or ""),
        "unresolved_total": int(unresolved_total),
        "by_source": unresolved_by_source,
        "by_reason": unresolved_by_reason,
    }

    row = _STORE.get_app_setting(APP_SETTING_KEY_REFERENCE_UNRESOLVED_TRENDS)
    current = row.get("value") if isinstance(row, dict) else {}
    runs = current.get("runs") if isinstance(current, dict) else []
    if not isinstance(runs, list):
        runs = []
    runs.append(sample)
    runs = runs[-20:]
    _STORE.upsert_app_setting(
        key=APP_SETTING_KEY_REFERENCE_UNRESOLVED_TRENDS,
        value={"runs": runs},
        updated_by_user_id=None,
    )


def _apply_group_decisions(context: SessionContext, task: Dict, group_decisions: Dict, fallback_full_corrected: str = "") -> Dict:
    original_text = str(task.get("original_text") or "")
    full_corrected = str(task.get("full_corrected_text") or "") or str(fallback_full_corrected or "")
    if not original_text.strip():
        raise RuntimeError("No document loaded")
    if not full_corrected.strip():
        raise RuntimeError("No corrected document available")

    processor = DocumentProcessor()
    corrected_text = processor.apply_group_decisions(original_text, full_corrected, group_decisions)

    process_payload = _build_process_payload(
        processor=processor,
        task_row=task,
        corrected_text=corrected_text,
        full_corrected_text=full_corrected,
        options=task.get("options", {}),
    )
    reports = _extract_reports_from_process_payload(process_payload)

    updated = _STORE.update_task_corrected_text(
        task_id=str(task.get("id") or ""),
        user_id=context.user_id,
        corrected_text=corrected_text,
        reports=reports,
    )
    if updated is None:
        raise RuntimeError("Task update failed")

    _store_task_export_files(updated, original_text=original_text, corrected_text=corrected_text)

    _record_audit(
        event_type="task_group_decisions_applied",
        actor_user_id=context.user_id,
        entity_type="task",
        entity_id=str(task.get("id") or ""),
    )

    return process_payload


def _resolve_task_download_file(context: SessionContext, task_id: str, file_type: str) -> Tuple[Dict, str, str]:
    """Resolve generated DOCX metadata and absolute path for task downloads."""
    normalized_type = str(file_type or "").strip().lower()
    print(f"[DOWNLOAD] request  task={task_id!r}  raw_type={file_type!r}  normalized={normalized_type!r}")
    if normalized_type not in {"clean", "highlighted", "highlighted_comments", "track_changes"}:
        normalized_type = "highlighted"
        print(f"[DOWNLOAD] unknown type, defaulted to 'highlighted'")

    file_row = _STORE.get_task_file_for_user(
        task_id=task_id,
        file_type=normalized_type,
        user_id=context.user_id,
        is_admin=context.role == ROLE_ADMIN,
    )
    print(f"[DOWNLOAD] db_lookup  type={normalized_type!r}  found={'yes' if file_row else 'NO — will attempt regen'}")
    if file_row is None:
        # Try to regenerate from stored processed content if available.
        task = _STORE.get_task_for_user(task_id=task_id, user_id=context.user_id, is_admin=context.role == ROLE_ADMIN)
        if task and str(task.get("status") or "") in {"PROCESSED", "REVIEW_REQUIRED"}:
            corrected = str(task.get("corrected_text") or "")
            original = str(task.get("original_text") or "")
            if corrected.strip() and original.strip():
                print(f"[DOWNLOAD] regenerating all export variants for task={task_id!r}")
                _store_task_export_files(task, original_text=original, corrected_text=corrected)
                file_row = _STORE.get_task_file_for_user(
                    task_id=task_id,
                    file_type=normalized_type,
                    user_id=context.user_id,
                    is_admin=context.role == ROLE_ADMIN,
                )
                print(f"[DOWNLOAD] post-regen lookup  type={normalized_type!r}  found={'yes' if file_row else 'STILL MISSING'}")
            else:
                print(f"[DOWNLOAD] regen skipped — corrected/original text missing")
        else:
            status = str(task.get("status") or "<none>") if task else "<task not found>"
            print(f"[DOWNLOAD] regen skipped — task status={status!r}")

    if file_row is None:
        raise FileNotFoundError("No generated file is available for this task")

    file_abs = _resolve_storage_path(str(file_row.get("storage_path") or ""))
    on_disk = os.path.isfile(file_abs)
    print(f"[DOWNLOAD] resolved  path={file_abs!r}  on_disk={on_disk}")
    if not on_disk:
        raise FileNotFoundError("Stored file was not found on disk")

    return file_row, file_abs, normalized_type


def _read_task_download_payload(context: SessionContext, task_id: str, file_type: str) -> Dict:
    file_row, file_abs, normalized_type = _resolve_task_download_file(
        context=context,
        task_id=task_id,
        file_type=file_type,
    )

    with open(file_abs, "rb") as infile:
        encoded = base64.b64encode(infile.read()).decode("ascii")

    _record_audit(
        event_type="task_downloaded",
        actor_user_id=context.user_id,
        entity_type="task",
        entity_id=task_id,
        metadata={"file_type": normalized_type},
    )

    task = _STORE.get_task_for_user(
        task_id=task_id,
        user_id=context.user_id,
        is_admin=context.role == ROLE_ADMIN,
    ) or {}
    reports = task.get("reports") if isinstance(task.get("reports"), dict) else {}
    autopilot_audit = reports.get("autopilot_audit") if isinstance(reports.get("autopilot_audit"), dict) else {}

    return {
        "success": True,
        "task_id": task_id,
        "file_type": normalized_type,
        "file_name": str(file_row.get("download_name") or _build_download_filename("manuscript", normalized_type)),
        "mime_type": str(file_row.get("mime_type") or MIME_DOCX),
        "base64_data": encoded,
        "task_diagnostics": _task_diagnostics_snapshot(task) if isinstance(task, dict) and task else {},
        "autopilot_audit": autopilot_audit,
    }


def _task_diagnostics_snapshot(task: Dict) -> Dict:
    reports = task.get("reports") if isinstance(task.get("reports"), dict) else {}
    citation_report = reports.get("citation_reference_report") if isinstance(reports.get("citation_reference_report"), dict) else {}
    citation_summary = citation_report.get("summary") if isinstance(citation_report.get("summary"), dict) else {}
    issue_counts = citation_report.get("issue_counts") if isinstance(citation_report.get("issue_counts"), dict) else {}
    online = citation_report.get("online_validation") if isinstance(citation_report.get("online_validation"), dict) else {}
    online_entries = online.get("entries") if isinstance(online.get("entries"), list) else []
    enrichment = online.get("enrichment") if isinstance(online.get("enrichment"), dict) else {}
    enrichment_trail = enrichment.get("trail") if isinstance(enrichment.get("trail"), list) else []
    processing_note = str(reports.get("processing_note") or "")
    processing_audit = reports.get("processing_audit") if isinstance(reports.get("processing_audit"), dict) else {}
    autopilot_audit = reports.get("autopilot_audit") if isinstance(reports.get("autopilot_audit"), dict) else {}
    summary = processing_audit.get("summary") if isinstance(processing_audit.get("summary"), dict) else {}
    unresolved_numbers = set()
    for entry in online_entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status") or "") in {"mismatch", "not_found", "ambiguous", "error"}:
            try:
                unresolved_numbers.add(int(entry.get("number") or 0))
            except (TypeError, ValueError):
                continue
    for entry in enrichment_trail:
        if not isinstance(entry, dict):
            continue
        autofill_status = str(entry.get("autofill_status") or "none")
        if bool(entry.get("doi_rejected")) or bool(entry.get("doi_needs_review")) or autofill_status != "full":
            try:
                unresolved_numbers.add(int(entry.get("number") or 0))
            except (TypeError, ValueError):
                continue
    unresolved_numbers.discard(0)
    return {
        "task": _task_summary(task),
        "has_corrected_text": bool(str(task.get("corrected_text") or "").strip()),
        "processing_note": processing_note,
        "citation_issue_total": int(citation_summary.get("issue_total", 0) or 0),
        "citation_issue_counts": issue_counts,
        "processing_summary": summary,
        "autopilot_audit": autopilot_audit,
        "reference_issue_total": int(citation_summary.get("reference_issues", 0) or 0),
        "unresolved_reference_count": len(unresolved_numbers),
        "cmos_guardrails": summary.get("cmos_guardrails") if isinstance(summary.get("cmos_guardrails"), dict) else {},
    }


def _assistant_admin_activity_snapshot() -> Dict:
    users = _STORE.list_users(limit=500)
    events = _STORE.list_audit_events(limit=200)
    active_users = 0
    inactive_users = 0
    for user in users:
        if str(user.get("status") or STATUS_ACTIVE).upper() == STATUS_ACTIVE:
            active_users += 1
        else:
            inactive_users += 1

    event_counts: Dict[str, int] = {}
    for event in events:
        code = str(event.get("event_type") or "unknown").strip() or "unknown"
        event_counts[code] = int(event_counts.get(code, 0)) + 1

    top_events = sorted(event_counts.items(), key=lambda item: item[1], reverse=True)[:8]
    recent = []
    for event in events[:10]:
        recent.append(
            {
                "event_type": str(event.get("event_type") or ""),
                "actor_email": str(event.get("actor_email") or ""),
                "target_email": str(event.get("target_email") or ""),
                "entity_type": str(event.get("entity_type") or ""),
                "entity_id": str(event.get("entity_id") or ""),
                "created_at": int(event.get("created_at") or 0),
            }
        )

    return {
        "user_counts": {
            "total": len(users),
            "active": active_users,
            "inactive": inactive_users,
        },
        "recent_event_count": len(events),
        "top_event_types": [{"event_type": key, "count": value} for key, value in top_events],
        "recent_events": recent,
    }


def _assistant_qna_response(
    context: SessionContext,
    message: str,
    task: Optional[Dict],
    include_admin_activity: bool = False,
) -> Dict:
    runtime = _read_global_runtime_settings()
    editing = runtime.get("editing", {}) if isinstance(runtime.get("editing"), dict) else {}
    ai = runtime.get("ai", {}) if isinstance(runtime.get("ai"), dict) else {}
    lower = str(message or "").strip().lower()

    def _looks_like_tulsi_question(text: str) -> bool:
        return "tulsi" in text and ("word" in text or "capital" in text or "lower" in text or "upper" in text)

    def _plain_answer_for_message(text: str) -> str:
        if _looks_like_tulsi_question(text):
            return (
                "Use 'Tulsi' when it is a specific plant name or cultural/sacred name (as in your sentence). "
                "Use 'tulsi' only for generic mention."
            )
        if "next step" in text or "what should i do" in text or "safest action" in text:
            return "I will use the current task diagnostics to choose the safest next step."
        if "export" in text or "ready" in text:
            return "I will check whether the task looks ready for clean or redline export."
        if "fallback" in text or "retry" in text:
            return "Fallback usually means the AI output was incomplete, risky, or failed a guardrail; use the task diagnostics before retrying."
        if "reference" in text or "citation" in text:
            return "References are checked for author/title/year and source-type rules. If format still looks wrong, run Retry Recommended once."
        if "spell" in text or "grammar" in text:
            return "Spelling and grammar are enabled. If output still looks weak, use Retry Recommended to reduce fallback sections."
        return "I can help with one thing at a time: wording, spelling, references, citations, or retry settings."

    lines = [_plain_answer_for_message(lower)]

    suggestions: list[str] = []
    if "spell" in lower or "grammar" in lower:
        suggestions.append("If spelling/grammar corrections look weak, reprocess with AI enabled and keep spelling + sentence_case + punctuation enabled.")
    if "reference" in lower or "citation" in lower:
        suggestions.append("For references, keep chicago_style enabled and verify citation/reference issues after processing.")
    if "next step" in lower or "what should i do" in lower:
        suggestions.append("Use the quick prompts first, then run only the smallest safe action: unresolved retry, recommended retry, or export.")
    if "fallback" in lower or "retry" in lower:
        suggestions.append("Use Retry Recommended when fallback sections are present; use unresolved-reference retry only for reference cleanup.")
    if "export" in lower or "ready" in lower:
        suggestions.append("Before final export, review unresolved references, fallback sections, and the corrected preview.")
    if "reprocess" in lower or "process" in lower:
        suggestions.append("Use mode=action with action=reprocess_task and task_id to execute the safe processing action.")
    if "decision" in lower or "accept" in lower or "reject" in lower:
        suggestions.append("Use mode=action with action=apply_correction_group_decisions and pass group_decisions to apply accept/reject choices safely.")

    wants_diagnostics = (
        "diagnostic" in lower
        or "status" in lower
        or "why" in lower
        or "fallback" in lower
        or "score" in lower
        or "runtime" in lower
        or "next step" in lower
        or "what should i do" in lower
        or "ready" in lower
        or "export" in lower
    )

    task_snapshot = {}
    if task is not None:
        task_snapshot = _task_diagnostics_snapshot(task)
        if wants_diagnostics:
            lines.append(
                f"Task status: {task_snapshot.get('task', {}).get('status', '')}, words: {task_snapshot.get('task', {}).get('word_count', 0)}, "
                f"citation issues: {task_snapshot.get('citation_issue_total', 0)}."
            )
        guardrails = task_snapshot.get("cmos_guardrails", {})
        if wants_diagnostics and isinstance(guardrails, dict) and guardrails:
            lines.append(
                f"CMOS: {guardrails.get('status', 'unknown')} (score {guardrails.get('compliance_score', 0)})."
            )
        if wants_diagnostics and task_snapshot.get("processing_note"):
            lines.append(f"Last note: {task_snapshot.get('processing_note')}")
        if wants_diagnostics:
            processing_summary = task_snapshot.get("processing_summary", {})
            if not isinstance(processing_summary, dict):
                processing_summary = {}
            fallback_sections = int(processing_summary.get("fallback_sections", 0) or 0)
            total_sections = int(processing_summary.get("total_sections", 0) or 0)
            unresolved_count = int(task_snapshot.get("unresolved_reference_count", 0) or 0)
            reference_issues = int(task_snapshot.get("reference_issue_total", 0) or 0)
            has_corrected = bool(task_snapshot.get("has_corrected_text"))
            if total_sections > 0:
                lines.append(f"AI sections: fallback={fallback_sections}/{total_sections}.")
            if unresolved_count > 0:
                lines.append(f"Unresolved references needing review: {unresolved_count}.")
            if "next step" in lower or "what should i do" in lower or "safest action" in lower:
                if not has_corrected:
                    lines.append("Next step: process or reprocess the task before export.")
                elif unresolved_count > 0 or reference_issues > 0:
                    lines.append("Next step: review unresolved references, then use Retry Auto-Fixable Only or export the unresolved report.")
                elif fallback_sections > 0:
                    lines.append("Next step: use Retry Recommended to reduce fallback sections before final export.")
                else:
                    lines.append("Next step: the task looks ready for clean/redline export after your human review.")
            if "export" in lower or "ready" in lower:
                if not has_corrected:
                    lines.append("Export readiness: blocked until corrected text exists.")
                elif unresolved_count > 0 or fallback_sections > 0:
                    lines.append("Export readiness: usable for review, but resolve references/fallback before final delivery.")
                else:
                    lines.append("Export readiness: no assistant-level blocker found; export after reviewing the preview.")

    admin_activity = {}
    if include_admin_activity and context.role == ROLE_ADMIN:
        admin_activity = _assistant_admin_activity_snapshot()
        counts = admin_activity.get("user_counts", {}) if isinstance(admin_activity, dict) else {}
        if wants_diagnostics:
            lines.append(
                f"Admin snapshot: users total={int(counts.get('total', 0) or 0)}, "
                f"active={int(counts.get('active', 0) or 0)}, inactive={int(counts.get('inactive', 0) or 0)}."
            )
        suggestions.append("Review top event types and recent events to spot recurring operational issues.")

    if not suggestions:
        suggestions.append("Ask about spelling, references, citations, or request reprocess_task/apply_correction_group_decisions for a specific task.")

    payload = {
        "message": " ".join(lines),
        "suggestions": suggestions,
        "task_diagnostics": task_snapshot,
    }
    if admin_activity:
        payload["admin_activity"] = admin_activity
    return payload


def _run_retention_cleanup(force: bool = False):
    global _LAST_CLEANUP_AT
    now = time.time()
    with _CLEANUP_LOCK:
        if not force and now - _LAST_CLEANUP_AT < 300:
            return

        cutoff = int(now)
        for file_row in _STORE.get_expired_task_files(cutoff):
            try:
                abs_path = _resolve_storage_path(str(file_row.get("storage_path") or ""))
                if os.path.isfile(abs_path):
                    os.unlink(abs_path)
            except Exception:
                pass
            _STORE.mark_task_file_deleted(str(file_row.get("id") or ""), cutoff)

        _STORE.purge_expired_sessions()
        _LAST_CLEANUP_AT = now


def _maybe_run_cleanup():
    try:
        _run_retention_cleanup(force=False)
    except Exception:
        pass


def _validate_ai_provider_runtime(provider: str, model: str, api_key: str, ollama_host: str) -> Tuple[bool, str]:
    selected = str(provider or "").strip().lower()
    selected_model = str(model or "").strip()
    key = str(api_key or "").strip()
    host = str(ollama_host or "http://localhost:11434").strip() or "http://localhost:11434"

    if selected == "ollama":
        try:
            response = requests.get(f"{host}/api/tags", timeout=8)
            if response.status_code == 200:
                data = response.json() if response.content else {}
                raw_models = data.get("models", []) if isinstance(data, dict) else []
                available_models = []
                for item in raw_models if isinstance(raw_models, list) else []:
                    if isinstance(item, dict):
                        name = str(item.get("name", "") or "").strip()
                        if name:
                            available_models.append(name)
                if selected_model:
                    if selected_model in available_models:
                        return True, f"Ollama reachable at {host} with model {selected_model}"
                    if available_models:
                        return False, f"Ollama reachable, but model '{selected_model}' is not installed on {host}"
                    return False, f"Ollama reachable, but no models are installed on {host}"
                if available_models:
                    return True, f"Ollama reachable at {host} with {len(available_models)} installed model(s)"
                return False, f"Ollama reachable at {host}, but no models are installed"
            return False, f"Ollama check failed ({response.status_code}) at {host}"
        except Exception as exc:
            return False, f"Ollama check failed: {exc}"

    if selected == "gemini":
        if not key:
            key = str(os.getenv("GEMINI_API_KEY", "") or "").strip()
        if not key:
            return False, "Gemini API key missing"
        use_model = selected_model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": "Reply with OK only."}]}],
            "generationConfig": {"temperature": 0},
        }
        try:
            response = requests.post(url, json=payload, timeout=12)
            if response.status_code == 200:
                return True, f"Gemini reachable with model {use_model}"
            if response.status_code in (401, 403):
                return False, f"Gemini unauthorized/forbidden ({response.status_code})"
            return False, f"Gemini check failed ({response.status_code})"
        except Exception as exc:
            return False, f"Gemini check failed: {exc}"

    if selected == "openrouter":
        if not key:
            key = str(os.getenv("OPENROUTER_API_KEY", "") or "").strip()
        if not key:
            return False, "OpenRouter API key missing"
        use_model = selected_model or "openrouter/auto"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        referer = str(os.getenv("OPENROUTER_HTTP_REFERER", "") or "").strip()
        title = str(os.getenv("OPENROUTER_APP_TITLE", "Manuscript Editor") or "").strip()
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
        payload = {
            "model": use_model,
            "messages": [{"role": "user", "content": "Reply with OK only."}],
            "temperature": 0,
            "max_tokens": 8,
        }
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=15,
            )
            if response.status_code == 200:
                return True, f"OpenRouter reachable with model {use_model}"
            if response.status_code in (401, 403):
                return False, f"OpenRouter unauthorized/forbidden ({response.status_code})"
            if response.status_code == 429:
                return False, "OpenRouter rate-limited (429)"
            return False, f"OpenRouter check failed ({response.status_code})"
        except Exception as exc:
            return False, f"OpenRouter check failed: {exc}"

    if selected == "agent_router":
        if not key:
            key = str(os.getenv("AGENT_ROUTER_TOKEN", "") or "").strip()
        if not key:
            return False, "AgentRouter token missing"
        use_model = selected_model or "deepseek-v3.1"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": use_model,
            "messages": [{"role": "user", "content": "Reply with OK only."}],
            "temperature": 0,
            "max_tokens": 8,
        }
        try:
            response = requests.post(
                "https://agentrouter.org/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=15,
            )
            if response.status_code == 200:
                return True, f"AgentRouter reachable with model {use_model}"
            if response.status_code in (401, 403):
                return False, f"AgentRouter unauthorized/forbidden ({response.status_code})"
            if response.status_code == 429:
                return False, "AgentRouter rate-limited (429)"
            return False, f"AgentRouter check failed ({response.status_code})"
        except Exception as exc:
            return False, f"AgentRouter check failed: {exc}"

    return False, f"Unsupported provider: {selected or 'unknown'}"


def _build_reference_validation_diagnostics_payload() -> Dict:
    """Build safe admin diagnostics for online reference validation and Serper fallback."""
    settings = _read_global_runtime_settings()
    editing = settings.get("editing", {}) if isinstance(settings.get("editing"), dict) else {}
    online_validation_enabled = bool(editing.get("online_reference_validation", True))
    serper_requested = bool(editing.get("online_reference_serper_fallback", True))

    processor = DocumentProcessor()
    editor = getattr(processor, "editor", None)
    raw_diagnostics = {}
    if editor is not None and hasattr(editor, "get_online_validation_diagnostics"):
        try:
            raw_diagnostics = editor.get_online_validation_diagnostics()
        except Exception:
            raw_diagnostics = {}

    serper_configured = bool(raw_diagnostics.get("serper_configured"))
    trend_row = _STORE.get_app_setting(APP_SETTING_KEY_REFERENCE_UNRESOLVED_TRENDS)
    trend_value = trend_row.get("value") if isinstance(trend_row, dict) else {}
    trend_runs = trend_value.get("runs") if isinstance(trend_value, dict) else []
    if not isinstance(trend_runs, list):
        trend_runs = []
    trend_runs = trend_runs[-20:]
    trend_by_source: Dict[str, int] = {}
    trend_by_reason: Dict[str, int] = {}
    for run in trend_runs:
        if not isinstance(run, dict):
            continue
        by_source = run.get("by_source", {}) if isinstance(run.get("by_source"), dict) else {}
        by_reason = run.get("by_reason", {}) if isinstance(run.get("by_reason"), dict) else {}
        for key, value in by_source.items():
            trend_by_source[str(key)] = int(trend_by_source.get(str(key), 0)) + int(value or 0)
        for key, value in by_reason.items():
            trend_by_reason[str(key)] = int(trend_by_reason.get(str(key), 0)) + int(value or 0)

    return {
        "generated_at": int(time.time()),
        "global_runtime": {
            "online_reference_validation": online_validation_enabled,
            "online_reference_serper_fallback": serper_requested,
            "online_reference_validation_admin_cap": int(editing.get("online_reference_validation_admin_cap", 150) or 150),
            "auto_resolve_unresolved_references": bool(editing.get("auto_resolve_unresolved_references", True)),
            "autopilot_auto_heal_bibliography": bool(editing.get("autopilot_auto_heal_bibliography", True)),
            "autopilot_heal_when_reference_issues_at_least": int(editing.get("autopilot_heal_when_reference_issues_at_least", 1) or 1),
            "autopilot_min_overall_confidence_for_autocomplete": float(editing.get("autopilot_min_overall_confidence_for_autocomplete", 0.72) or 0.72),
            "autopilot_min_reference_confidence_for_autoheal": float(editing.get("autopilot_min_reference_confidence_for_autoheal", 0.62) or 0.62),
        },
        "serper": {
            "configured": serper_configured,
            "effective_enabled": bool(online_validation_enabled and serper_requested and serper_configured),
            "endpoint": str(raw_diagnostics.get("serper_endpoint") or ""),
        },
        "lookup_limits": raw_diagnostics.get("limits", {}),
        "cache": raw_diagnostics.get("cache", {}),
        "lookup_metrics_last_run": raw_diagnostics.get("lookup_metrics", {}),
        "lookup_metrics_last_run_at": int(raw_diagnostics.get("lookup_metrics_updated_at", 0) or 0),
        "unresolved_trends": {
            "window_runs": len(trend_runs),
            "runs": trend_runs,
            "totals_by_source": trend_by_source,
            "totals_by_reason": trend_by_reason,
        },
    }


def _reset_reference_validation_diagnostics_payload() -> Dict:
    """Reset shared online reference cache and return refreshed safe diagnostics."""
    processor = DocumentProcessor()
    editor = getattr(processor, "editor", None)
    removed_entries = 0
    if editor is not None and hasattr(editor, "reset_online_validation_cache"):
        try:
            removed_entries = int(editor.reset_online_validation_cache() or 0)
        except Exception:
            removed_entries = 0
    _STORE.upsert_app_setting(
        key=APP_SETTING_KEY_REFERENCE_UNRESOLVED_TRENDS,
        value={"runs": []},
        updated_by_user_id=None,
    )
    diagnostics = _build_reference_validation_diagnostics_payload()
    return {
        "removed_cache_entries": removed_entries,
        "diagnostics": diagnostics,
    }


def _render_html_shell(
    html_file: str,
    admin_dashboard: bool = False,
    route_classes: Optional[list[str]] = None,
    task_route_id: str = "",
) -> HTTPResponse:
    _ensure_web_assets()
    fragment_values = {
        "ASSET_VERSION": WEB_ASSET_VERSION,
        "APP_VERSION": APP_VERSION,
    }
    fragment_values["LOGIN_FRAGMENT"] = _render_web_template(_read_web_asset("fragments/login.html"), fragment_values)
    fragment_values["APP_HEADER_FRAGMENT"] = _render_web_template(_read_web_asset("fragments/app_header.html"), fragment_values)
    fragment_values["ASSISTANT_PANEL_FRAGMENT"] = _render_web_template(_read_web_asset("fragments/assistant_panel.html"), fragment_values)
    fragment_values["APP_FOOTER_FRAGMENT"] = _render_web_template(_read_web_asset("fragments/app_footer.html"), fragment_values)
    fragment_values["SCRIPT_BUNDLE_FRAGMENT"] = _render_web_template(_read_web_asset("fragments/script_bundle.html"), fragment_values)
    shell_values = {
        **fragment_values,
        "HEADER_SUBTITLE": "Professional Copy Editing",
    }
    if html_file == "tasks.html":
        shell_values["HEADER_SUBTITLE"] = "Task Dashboard"

    html = _render_web_template(_read_web_asset(html_file), shell_values)

    body_classes = list(route_classes or [])
    if admin_dashboard:
        body_classes.extend(["admin-dashboard-route", "admin-dashboard-active"])
        html = html.replace(
            'class="setup-wizard-backdrop hidden" id="admin-panel-backdrop"',
            'class="setup-wizard-backdrop" id="admin-panel-backdrop"',
            1,
        )
    class_attr = f' class="{" ".join(dict.fromkeys(body_classes))}"' if body_classes else ""
    task_attr = f' data-task-route-id="{task_route_id}"' if task_route_id else ""
    html = html.replace("<body>", f"<body{class_attr}{task_attr}>", 1)

    return HTTPResponse(
        body=html,
        status=200,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store, max-age=0, must-revalidate",
            "Pragma": "no-cache",
        },
    )



def _build_route_dependencies():
    return SimpleNamespace(
        admin_emails=ADMIN_EMAILS,
        allowed_email_domains=ALLOWED_EMAIL_DOMAINS,
        app_setting_key_global_runtime=APP_SETTING_KEY_GLOBAL_RUNTIME,
        app_version=APP_VERSION,
        apply_global_runtime_settings=_apply_global_runtime_settings,
        apply_group_decisions=_apply_group_decisions,
        assistant_qna_response=_assistant_qna_response,
        auth_context_from_request=_auth_context_from_request,
        build_download_filename=_build_download_filename,
        build_reference_validation_diagnostics_payload=_build_reference_validation_diagnostics_payload,
        document_processor=DocumentProcessor,
        ensure_web_assets=_ensure_web_assets,
        error_payload=_error_payload,
        get_client_ip=_get_client_ip,
        get_owned_task_or_error=_get_owned_task_or_error,
        get_session_id_from_request=_get_session_id_from_request,
        get_user_agent=_get_user_agent,
        global_runtime_settings_for_user_payload=_global_runtime_settings_for_user_payload,
        google_client_id=GOOGLE_CLIENT_ID,
        increment_runtime_counter=_increment_runtime_counter,
        add_runtime_duration_sample=_add_runtime_duration_sample,
        is_local_manual_login_allowed=_is_local_manual_login_allowed,
        is_local_request=_is_local_request,
        is_production_env=_is_production_env,
        json_response=_json_response,
        local_manual_login_password=LOCAL_MANUAL_LOGIN_PASSWORD,
        local_manual_login_username=LOCAL_MANUAL_LOGIN_USERNAME,
        mime_docx=MIME_DOCX,
        normalize_global_runtime_settings=_normalize_global_runtime_settings,
        processing_job_queue=_PROCESSING_JOB_QUEUE,
        process_task=_process_task,
        heal_bibliography_task=_heal_bibliography_task,
        autopilot_task=_autopilot_task,
        public_user_payload=_public_user_payload,
        read_global_runtime_settings=_read_global_runtime_settings,
        read_json_payload=_read_json_payload,
        read_runtime_telemetry=_read_runtime_telemetry,
        read_task_download_payload=_read_task_download_payload,
        check_rate_limit=_check_rate_limit,
        record_audit=_record_audit,
        render_html_shell=_render_html_shell,
        require_admin=require_admin,
        require_auth=require_auth,
        require_auth_context=_require_auth_context,
        reset_reference_validation_diagnostics_payload=_reset_reference_validation_diagnostics_payload,
        reset_runtime_telemetry=_reset_runtime_telemetry,
        resolve_task_download_file=_resolve_task_download_file,
        role_admin=ROLE_ADMIN,
        session_ttl_hours=SESSION_TTL_HOURS,
        status_active=STATUS_ACTIVE,
        status_inactive=STATUS_INACTIVE,
        auth_rate_limit_count=AUTH_RATE_LIMIT_COUNT,
        auth_rate_limit_window_seconds=AUTH_RATE_LIMIT_WINDOW_SECONDS,
        max_upload_bytes=MAX_UPLOAD_BYTES,
        max_text_chars=MAX_TEXT_CHARS,
        task_list_limit_max=TASK_LIST_LIMIT_MAX,
        store=_STORE,
        task_summary=_task_summary,
        upload_docx_to_task=_upload_docx_to_task,
        upload_text_to_task=_upload_text_to_task,
        validate_ai_provider_runtime=_validate_ai_provider_runtime,
        verify_google_token=_verify_google_token,
        web_asset_version=WEB_ASSET_VERSION,
        web_dir=WEB_DIR,
    )


def _register_routes():
    from routes import register_routes

    register_routes(app, _build_route_dependencies())


_register_routes()
_validate_startup_config()


def main():
    _ensure_web_assets()
    host = os.getenv("MANUSCRIPT_EDITOR_HOST", "127.0.0.1")
    try:
        port = int(os.getenv("MANUSCRIPT_EDITOR_PORT", os.getenv("PORT", "8000")))
    except Exception:
        port = 8000

    print(f"Manuscript Editor web app listening on http://{host}:{port}")
    print(f"Auth domains: {', '.join(ALLOWED_EMAIL_DOMAINS)}")
    print(f"DB backend: {_STORE.backend}")

    run(app=app, host=host, port=port, debug=False, reloader=False)


if __name__ == "__main__":
    main()
