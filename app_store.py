#!/usr/bin/env python3
"""Persistence layer for authenticated web mode.

This module intentionally keeps SQL simple and backend-agnostic so we can run on
PostgreSQL in production and SQLite during local development/tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - optional in local/dev fallback
    psycopg = None
    dict_row = None


SQLITE_BUSY_TIMEOUT_MS = int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "5000") or 5000)

ROLE_ADMIN = "ADMIN"
ROLE_USER = "USER"
STATUS_ACTIVE = "ACTIVE"
STATUS_INACTIVE = "INACTIVE"


@dataclass
class SessionContext:
    session_id: str
    user_id: str
    email: str
    display_name: str
    role: str
    status: str


class AppStore:
    """Database-backed persistence for users, sessions, tasks and audit logs."""

    def __init__(self, database_url: str, data_dir: str):
        self.database_url = (database_url or "").strip()
        self.data_dir = os.path.abspath(data_dir)
        self._lock = threading.Lock()

        if self.database_url.startswith("postgres://"):
            # psycopg requires postgresql:// style URL.
            self.database_url = "postgresql://" + self.database_url[len("postgres://") :]

        if self.database_url.startswith("postgresql://"):
            if psycopg is None:
                raise RuntimeError("psycopg is required for PostgreSQL DATABASE_URL")
            self.backend = "postgres"
            self.sqlite_path = ""
        else:
            self.backend = "sqlite"
            default_sqlite_path = os.path.join(self.data_dir, "manuscript_editor.sqlite3")
            self.sqlite_path = self._resolve_sqlite_path(self.database_url, default_sqlite_path)
            os.makedirs(os.path.dirname(self.sqlite_path), exist_ok=True)

        self._conn = None
        self._connect()
        self._init_schema()

    @staticmethod
    def _resolve_sqlite_path(database_url: str, fallback_path: str) -> str:
        value = (database_url or "").strip()
        if not value:
            return fallback_path
        if value.startswith("sqlite:///"):
            path = value[len("sqlite:///") :]
            if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
                path = path[1:]
            return os.path.abspath(path)
        if value.startswith("sqlite://"):
            path = value[len("sqlite://") :]
            return os.path.abspath(path)
        return fallback_path

    def _connect(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

        if self.backend == "sqlite":
            conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            # Multiple gunicorn workers share one WAL file; without a busy timeout
            # a concurrent writer raises "database is locked" immediately.
            conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._conn = conn
            return

        try:
            self._conn = psycopg.connect(self.database_url, autocommit=True, row_factory=dict_row)
        except Exception as exc:
            raise RuntimeError(self._build_db_connect_error(exc)) from exc

    def _build_db_connect_error(self, exc: Exception) -> str:
        parsed = urlparse(self.database_url or "")
        host = (parsed.hostname or "").strip() or "<unknown-host>"
        port = parsed.port or 5432
        db_name = (parsed.path or "").lstrip("/") or "<unknown-db>"
        base = (
            f"Database connection failed during startup (host={host}, port={port}, database={db_name}). "
            "Verify DATABASE_URL is reachable from this container."
        )
        if host in ("127.0.0.1", "localhost"):
            base += (
                " Detected loopback host in DATABASE_URL. Inside Docker, loopback points to the app container "
                "itself, not your Postgres service. Use your DB service/container hostname instead."
            )
        if str(exc):
            base += f" Original error: {exc}"
        return base

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        if isinstance(row, sqlite3.Row):
            return {k: row[k] for k in row.keys()}
        return dict(row)

    def _execute(self, sql: str, params: Sequence[Any] = ()):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(sql, params)
            if self.backend == "sqlite":
                self._conn.commit()
            return cursor

    def _query_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
        # The fetch happens inside the lock: the process shares one connection,
        # so stepping a cursor while another thread executes is not safe.
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def _query_all(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall() or []
        return [self._row_to_dict(row) for row in rows]

    def _init_schema(self):
        # When multiple Gunicorn workers boot at once, schema creation can race on PostgreSQL
        # even with IF NOT EXISTS. Serialize bootstrap with an advisory lock.
        if self.backend == "postgres":
            lock_key_major = 428_317
            lock_key_minor = 91_223
            self._execute(
                "SELECT pg_advisory_lock(%s, %s)",
                (lock_key_major, lock_key_minor),
            )
            try:
                self._init_schema_unlocked()
            finally:
                self._execute(
                    "SELECT pg_advisory_unlock(%s, %s)",
                    (lock_key_major, lock_key_minor),
                )
            return

        self._init_schema_unlocked()

    def _init_schema_unlocked(self):
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                google_sub TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                domain TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                last_login_at INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                revoked_at INTEGER,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_path TEXT,
                original_text TEXT NOT NULL,
                corrected_text TEXT,
                full_corrected_text TEXT,
                word_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                options_json TEXT,
                reports_json TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                processed_at INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS task_files (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                download_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                deleted_at INTEGER,
                created_at INTEGER NOT NULL,
                UNIQUE(task_id, file_type),
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                actor_user_id TEXT,
                target_user_id TEXT,
                event_type TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                metadata_json TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at INTEGER NOT NULL
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_by_user_id TEXT,
                updated_at INTEGER NOT NULL
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS task_runs (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL,
                job_id TEXT,
                options_json TEXT,
                result_json TEXT,
                error TEXT,
                progress_percent REAL DEFAULT 0,
                stage TEXT DEFAULT '',
                tokens_consumed INTEGER DEFAULT 0,
                estimated_seconds_remaining INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL,
                started_at INTEGER,
                finished_at INTEGER,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS error_events (
                id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                code TEXT NOT NULL,
                message TEXT NOT NULL,
                exception_type TEXT,
                traceback TEXT,
                request_method TEXT,
                request_path TEXT,
                status_code INTEGER,
                actor_user_id TEXT,
                task_id TEXT,
                context_json TEXT,
                occurrence_count INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS journals (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                scope TEXT,
                keywords_json TEXT NOT NULL,
                subject_areas_json TEXT NOT NULL,
                article_types_json TEXT NOT NULL,
                issn_print TEXT,
                issn_online TEXT,
                publisher TEXT,
                quartile TEXT,
                open_access INTEGER NOT NULL DEFAULT 0,
                apc_usd REAL NOT NULL DEFAULT 0,
                submission_url TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )

        self._execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id, created_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_task_files_task ON task_files(task_id, file_type)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_task_runs_task_created ON task_runs(task_id, created_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_task_runs_user_created ON task_runs(user_id, created_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_audit_events_actor ON audit_events(actor_user_id, created_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_audit_events_target ON audit_events(target_user_id, created_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_audit_events_type ON audit_events(event_type, created_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_app_settings_updated_at ON app_settings(updated_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_journals_active_updated ON journals(is_active, updated_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_task_runs_task_status ON task_runs(task_id, status)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_error_events_seen ON error_events(last_seen_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_error_events_fingerprint ON error_events(fingerprint, last_seen_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_error_events_code ON error_events(code, last_seen_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_error_events_task ON error_events(task_id, last_seen_at)")

        # Progress columns were added after the first release; bring older
        # databases forward without a migration framework.
        self._ensure_columns(
            "task_runs",
            (
                ("progress_percent", "REAL DEFAULT 0"),
                ("stage", "TEXT DEFAULT ''"),
                ("tokens_consumed", "INTEGER DEFAULT 0"),
                ("estimated_seconds_remaining", "INTEGER DEFAULT 0"),
            ),
        )

    def _existing_columns(self, table: str) -> set:
        try:
            if self.backend == "sqlite":
                rows = self._query_all(f"PRAGMA table_info({table})")
                return {str(row.get("name") or "") for row in rows}
            rows = self._query_all(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                (table,),
            )
            return {str(row.get("column_name") or "") for row in rows}
        except Exception:
            return set()

    def _ensure_columns(self, table: str, columns: Sequence[Tuple[str, str]]):
        existing = self._existing_columns(table)
        if not existing:
            return
        for column_name, column_type in columns:
            if column_name in existing:
                continue
            try:
                self._execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")
            except Exception:
                # Another worker won the race, or the column already exists.
                pass

    @staticmethod
    def _now_ts() -> int:
        return int(time.time())

    @staticmethod
    def _safe_json_dump(value: Any) -> str:
        try:
            return json.dumps(value or {}, ensure_ascii=False)
        except Exception:
            return "{}"

    @staticmethod
    def _safe_json_load(value: Any) -> Dict[str, Any]:
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(str(value))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}

    def _normalize_user_row(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["email"] = str(data.get("email", "")).lower().strip()
        return data

    def bootstrap_admin_roles(self, admin_emails: Sequence[str]):
        now = self._now_ts()
        normalized = sorted({str(value or "").strip().lower() for value in admin_emails if str(value or "").strip()})
        for email in normalized:
            self._execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE lower(email) = ?" if self.backend == "sqlite" else "UPDATE users SET role = %s, updated_at = %s WHERE lower(email) = %s",
                (ROLE_ADMIN, now, email),
            )

    def upsert_google_user(
        self,
        *,
        email: str,
        google_sub: str,
        display_name: str,
        domain: str,
        admin_emails: Sequence[str],
    ) -> Dict[str, Any]:
        now = self._now_ts()
        normalized_email = str(email or "").strip().lower()
        admin_set = {str(value or "").strip().lower() for value in admin_emails if str(value or "").strip()}

        existing = self._query_one(
            "SELECT * FROM users WHERE lower(email) = ?" if self.backend == "sqlite" else "SELECT * FROM users WHERE lower(email) = %s",
            (normalized_email,),
        )

        if existing:
            role = ROLE_ADMIN if normalized_email in admin_set else str(existing.get("role") or ROLE_USER)
            if role not in (ROLE_ADMIN, ROLE_USER):
                role = ROLE_USER

            self._execute(
                """
                UPDATE users
                SET google_sub = ?, display_name = ?, domain = ?, role = ?, updated_at = ?, last_login_at = ?
                WHERE id = ?
                """
                if self.backend == "sqlite"
                else
                """
                UPDATE users
                SET google_sub = %s, display_name = %s, domain = %s, role = %s, updated_at = %s, last_login_at = %s
                WHERE id = %s
                """,
                (google_sub, display_name, domain, role, now, now, existing["id"]),
            )
            refreshed = self._query_one(
                "SELECT * FROM users WHERE id = ?" if self.backend == "sqlite" else "SELECT * FROM users WHERE id = %s",
                (existing["id"],),
            )
            return self._normalize_user_row(refreshed) or {}

        user_id = uuid.uuid4().hex
        role = ROLE_ADMIN if normalized_email in admin_set else ROLE_USER
        self._execute(
            """
            INSERT INTO users (id, email, google_sub, display_name, domain, role, status, last_login_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            if self.backend == "sqlite"
            else
            """
            INSERT INTO users (id, email, google_sub, display_name, domain, role, status, last_login_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, normalized_email, google_sub, display_name, domain, role, STATUS_ACTIVE, now, now, now),
        )
        created = self._query_one(
            "SELECT * FROM users WHERE id = ?" if self.backend == "sqlite" else "SELECT * FROM users WHERE id = %s",
            (user_id,),
        )
        return self._normalize_user_row(created) or {}

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        row = self._query_one(
            "SELECT * FROM users WHERE id = ?" if self.backend == "sqlite" else "SELECT * FROM users WHERE id = %s",
            (user_id,),
        )
        return self._normalize_user_row(row)

    def create_session(self, user_id: str, ttl_hours: int, ip_address: str = "", user_agent: str = "") -> str:
        now = self._now_ts()
        ttl_seconds = max(1, int(ttl_hours)) * 3600
        expires_at = now + ttl_seconds
        session_id = uuid.uuid4().hex
        self._execute(
            """
            INSERT INTO user_sessions (id, user_id, expires_at, last_seen_at, ip_address, user_agent, revoked_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
            """
            if self.backend == "sqlite"
            else
            """
            INSERT INTO user_sessions (id, user_id, expires_at, last_seen_at, ip_address, user_agent, revoked_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NULL, %s)
            """,
            (session_id, user_id, expires_at, now, ip_address[:128], user_agent[:512], now),
        )
        return session_id

    def get_session_context(self, session_id: str) -> Optional[SessionContext]:
        now = self._now_ts()
        row = self._query_one(
            """
            SELECT
                s.id AS session_id,
                u.id AS user_id,
                u.email,
                u.display_name,
                u.role,
                u.status
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = ? AND s.revoked_at IS NULL AND s.expires_at > ?
            """
            if self.backend == "sqlite"
            else
            """
            SELECT
                s.id AS session_id,
                u.id AS user_id,
                u.email,
                u.display_name,
                u.role,
                u.status
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = %s AND s.revoked_at IS NULL AND s.expires_at > %s
            """,
            (session_id, now),
        )
        if row is None:
            return None

        self._execute(
            "UPDATE user_sessions SET last_seen_at = ? WHERE id = ?" if self.backend == "sqlite" else "UPDATE user_sessions SET last_seen_at = %s WHERE id = %s",
            (now, session_id),
        )

        return SessionContext(
            session_id=str(row.get("session_id") or ""),
            user_id=str(row.get("user_id") or ""),
            email=str(row.get("email") or "").lower().strip(),
            display_name=str(row.get("display_name") or ""),
            role=str(row.get("role") or ROLE_USER),
            status=str(row.get("status") or STATUS_ACTIVE),
        )

    def revoke_session(self, session_id: str):
        now = self._now_ts()
        self._execute(
            "UPDATE user_sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL"
            if self.backend == "sqlite"
            else
            "UPDATE user_sessions SET revoked_at = %s WHERE id = %s AND revoked_at IS NULL",
            (now, session_id),
        )

    def revoke_sessions_for_user(self, user_id: str):
        now = self._now_ts()
        self._execute(
            "UPDATE user_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL"
            if self.backend == "sqlite"
            else
            "UPDATE user_sessions SET revoked_at = %s WHERE user_id = %s AND revoked_at IS NULL",
            (now, user_id),
        )

    def create_task(
        self,
        *,
        task_id: str = "",
        user_id: str,
        file_name: str,
        source_type: str,
        source_path: str,
        original_text: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = self._now_ts()
        task_id = str(task_id or "").strip() or uuid.uuid4().hex
        word_count = len(str(original_text or "").split())
        options_json = self._safe_json_dump(options or {})
        self._execute(
            """
            INSERT INTO tasks (
                id, user_id, file_name, source_type, source_path, original_text,
                corrected_text, full_corrected_text, word_count, status,
                options_json, reports_json, created_at, updated_at, processed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, ?, ?, ?, NULL)
            """
            if self.backend == "sqlite"
            else
            """
            INSERT INTO tasks (
                id, user_id, file_name, source_type, source_path, original_text,
                corrected_text, full_corrected_text, word_count, status,
                options_json, reports_json, created_at, updated_at, processed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, '', '', %s, %s, %s, %s, %s, %s, NULL)
            """,
            (
                task_id,
                user_id,
                str(file_name or "manuscript.txt"),
                str(source_type or "text"),
                str(source_path or ""),
                str(original_text or ""),
                word_count,
                "UPLOADED",
                options_json,
                "{}",
                now,
                now,
            ),
        )
        return self.get_task_for_user(task_id=task_id, user_id=user_id, is_admin=True) or {}

    def get_task_for_user(self, *, task_id: str, user_id: str, is_admin: bool) -> Optional[Dict[str, Any]]:
        if is_admin:
            row = self._query_one(
                "SELECT * FROM tasks WHERE id = ?" if self.backend == "sqlite" else "SELECT * FROM tasks WHERE id = %s",
                (task_id,),
            )
        else:
            row = self._query_one(
                "SELECT * FROM tasks WHERE id = ? AND user_id = ?"
                if self.backend == "sqlite"
                else
                "SELECT * FROM tasks WHERE id = %s AND user_id = %s",
                (task_id, user_id),
            )
        return self._normalize_task_row(row)

    def list_tasks_for_user(self, *, user_id: str, limit: int = 100, status: str = "") -> List[Dict[str, Any]]:
        safe_limit = max(1, min(250, int(limit or 100)))
        normalized_status = str(status or "").strip().upper()
        if normalized_status:
            rows = self._query_all(
                "SELECT * FROM tasks WHERE user_id = ? AND status = ? ORDER BY created_at DESC LIMIT ?"
                if self.backend == "sqlite"
                else
                "SELECT * FROM tasks WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT %s",
                (user_id, normalized_status, safe_limit),
            )
        else:
            rows = self._query_all(
                "SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC LIMIT ?"
                if self.backend == "sqlite"
                else
                "SELECT * FROM tasks WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                (user_id, safe_limit),
            )
        return [self._normalize_task_row(row) for row in rows if row]

    def update_task_status(self, *, task_id: str, status: str, user_id: str, is_admin: bool = False):
        now = self._now_ts()
        if is_admin:
            self._execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?"
                if self.backend == "sqlite"
                else
                "UPDATE tasks SET status = %s, updated_at = %s WHERE id = %s",
                (status, now, task_id),
            )
            return

        self._execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?"
            if self.backend == "sqlite"
            else
            "UPDATE tasks SET status = %s, updated_at = %s WHERE id = %s AND user_id = %s",
            (status, now, task_id, user_id),
        )

    def update_task_processing_result(
        self,
        *,
        task_id: str,
        user_id: str,
        corrected_text: str,
        full_corrected_text: str,
        word_count: int,
        options: Dict[str, Any],
        reports: Dict[str, Any],
        is_admin: bool = False,
    ) -> Optional[Dict[str, Any]]:
        now = self._now_ts()
        params: List[Any] = [
            corrected_text,
            full_corrected_text,
            int(word_count),
            "PROCESSED",
            self._safe_json_dump(options),
            self._safe_json_dump(reports),
            now,
            now,
            task_id,
        ]
        owner_clause = "" if is_admin else " AND user_id = ?"
        if not is_admin:
            params.append(user_id)

        sql = f"""
            UPDATE tasks
            SET corrected_text = ?,
                full_corrected_text = ?,
                word_count = ?,
                status = ?,
                options_json = ?,
                reports_json = ?,
                processed_at = ?,
                updated_at = ?
            WHERE id = ?{owner_clause}
            """
        if self.backend != "sqlite":
            sql = sql.replace("?", "%s")
        self._execute(sql, tuple(params))
        return self.get_task_for_user(task_id=task_id, user_id=user_id, is_admin=is_admin)

    def update_task_corrected_text(
        self,
        *,
        task_id: str,
        user_id: str,
        corrected_text: str,
        reports: Dict[str, Any],
        is_admin: bool = False,
    ) -> Optional[Dict[str, Any]]:
        now = self._now_ts()
        params: List[Any] = [
            corrected_text,
            self._safe_json_dump(reports),
            now,
            task_id,
        ]
        owner_clause = "" if is_admin else " AND user_id = ?"
        if not is_admin:
            params.append(user_id)

        sql = f"""
            UPDATE tasks
            SET corrected_text = ?,
                reports_json = ?,
                updated_at = ?
            WHERE id = ?{owner_clause}
            """
        if self.backend != "sqlite":
            sql = sql.replace("?", "%s")
        self._execute(sql, tuple(params))
        return self.get_task_for_user(task_id=task_id, user_id=user_id, is_admin=is_admin)

    def upsert_task_file(
        self,
        *,
        task_id: str,
        file_type: str,
        storage_path: str,
        download_name: str,
        mime_type: str,
        size_bytes: int,
        expires_at: int,
    ):
        now = self._now_ts()
        row = self._query_one(
            "SELECT id FROM task_files WHERE task_id = ? AND file_type = ?"
            if self.backend == "sqlite"
            else
            "SELECT id FROM task_files WHERE task_id = %s AND file_type = %s",
            (task_id, file_type),
        )
        if row:
            self._execute(
                """
                UPDATE task_files
                SET storage_path = ?, download_name = ?, mime_type = ?, size_bytes = ?, expires_at = ?, deleted_at = NULL
                WHERE task_id = ? AND file_type = ?
                """
                if self.backend == "sqlite"
                else
                """
                UPDATE task_files
                SET storage_path = %s, download_name = %s, mime_type = %s, size_bytes = %s, expires_at = %s, deleted_at = NULL
                WHERE task_id = %s AND file_type = %s
                """,
                (storage_path, download_name, mime_type, int(size_bytes), int(expires_at), task_id, file_type),
            )
            return

        self._execute(
            """
            INSERT INTO task_files (
                id, task_id, file_type, storage_path, download_name, mime_type,
                size_bytes, expires_at, deleted_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """
            if self.backend == "sqlite"
            else
            """
            INSERT INTO task_files (
                id, task_id, file_type, storage_path, download_name, mime_type,
                size_bytes, expires_at, deleted_at, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
            """,
            (
                uuid.uuid4().hex,
                task_id,
                file_type,
                storage_path,
                download_name,
                mime_type,
                int(size_bytes),
                int(expires_at),
                now,
            ),
        )

    def create_task_run(
        self,
        *,
        task_id: str,
        user_id: str,
        status: str = "PENDING",
        options: Optional[Dict[str, Any]] = None,
        job_id: str = "",
    ) -> Dict[str, Any]:
        now = self._now_ts()
        run_id = uuid.uuid4().hex
        self._execute(
            """
            INSERT INTO task_runs (
                id, task_id, user_id, status, job_id, options_json, result_json, error,
                created_at, started_at, finished_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)
            """
            if self.backend == "sqlite"
            else
            """
            INSERT INTO task_runs (
                id, task_id, user_id, status, job_id, options_json, result_json, error,
                created_at, started_at, finished_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s)
            """,
            (
                run_id,
                str(task_id or ""),
                str(user_id or ""),
                str(status or "PENDING"),
                str(job_id or ""),
                self._safe_json_dump(options or {}),
                "{}",
                "",
                now,
                now,
            ),
        )
        return self.get_task_run_for_user(run_id=run_id, user_id=user_id, is_admin=True) or {}

    def update_task_run(
        self,
        *,
        run_id: str,
        user_id: str,
        is_admin: bool = False,
        status: str = "",
        job_id: str = "",
        error: str = "",
        result: Optional[Dict[str, Any]] = None,
        progress_percent: Optional[float] = None,
        stage: Optional[str] = None,
        tokens_consumed: Optional[int] = None,
        estimated_seconds_remaining: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Apply a targeted column update.

        Only the fields explicitly supplied are written, so concurrent writers
        (the request thread setting job_id, the worker thread setting status)
        cannot clobber each other's columns.
        """
        now = self._now_ts()
        sets: List[str] = []
        params: List[Any] = []

        next_status = str(status or "").strip()
        if next_status:
            sets.append("status = ?")
            params.append(next_status)
        if job_id:
            sets.append("job_id = ?")
            params.append(str(job_id))
        if error:
            sets.append("error = ?")
            params.append(str(error))
        if result is not None:
            sets.append("result_json = ?")
            params.append(self._safe_json_dump(result if isinstance(result, dict) else {}))
        if progress_percent is not None:
            sets.append("progress_percent = ?")
            params.append(max(0.0, min(100.0, float(progress_percent))))
        if stage is not None:
            sets.append("stage = ?")
            params.append(str(stage)[:400])
        if tokens_consumed is not None:
            sets.append("tokens_consumed = ?")
            params.append(max(0, int(tokens_consumed)))
        if estimated_seconds_remaining is not None:
            sets.append("estimated_seconds_remaining = ?")
            params.append(max(0, int(estimated_seconds_remaining)))

        # Timestamp transitions are applied in SQL so they never depend on a
        # previously-read snapshot.
        if next_status == "RUNNING":
            sets.append("started_at = COALESCE(started_at, ?)")
            params.append(now)
        elif next_status in ("SUCCEEDED", "FAILED"):
            sets.append("started_at = COALESCE(started_at, ?)")
            params.append(now)
            sets.append("finished_at = COALESCE(finished_at, ?)")
            params.append(now)

        if not sets:
            return self.get_task_run_for_user(run_id=run_id, user_id=user_id, is_admin=is_admin)

        sets.append("updated_at = ?")
        params.append(now)

        where = "id = ?" if is_admin else "id = ? AND user_id = ?"
        params.append(run_id)
        if not is_admin:
            params.append(user_id)

        sql = f"UPDATE task_runs SET {', '.join(sets)} WHERE {where}"
        if self.backend != "sqlite":
            sql = sql.replace("?", "%s")
        self._execute(sql, tuple(params))
        return self.get_task_run_for_user(run_id=run_id, user_id=user_id, is_admin=is_admin)

    def reap_orphaned_task_runs(self, *, error: str = "Server restarted while this run was in progress") -> int:
        """Fail runs left PENDING/RUNNING by a previous process and unstick their tasks.

        The in-process job queue does not survive a restart, so any run still
        marked active at boot has no worker behind it.
        """
        now = self._now_ts()
        rows = self._query_all(
            "SELECT id, task_id FROM task_runs WHERE status IN ('PENDING', 'RUNNING')"
        )
        if not rows:
            return 0
        self._execute(
            """
            UPDATE task_runs
            SET status = 'FAILED', error = ?, finished_at = COALESCE(finished_at, ?), updated_at = ?
            WHERE status IN ('PENDING', 'RUNNING')
            """
            if self.backend == "sqlite"
            else
            """
            UPDATE task_runs
            SET status = 'FAILED', error = %s, finished_at = COALESCE(finished_at, %s), updated_at = %s
            WHERE status IN ('PENDING', 'RUNNING')
            """,
            (str(error), now, now),
        )
        for row in rows:
            task_id = str(row.get("task_id") or "")
            if not task_id:
                continue
            self._execute(
                "UPDATE tasks SET status = 'FAILED', updated_at = ? WHERE id = ? AND status = 'PROCESSING'"
                if self.backend == "sqlite"
                else
                "UPDATE tasks SET status = 'FAILED', updated_at = %s WHERE id = %s AND status = 'PROCESSING'",
                (now, task_id),
            )
        return len(rows)

    def has_active_task_run(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Return the active (PENDING/RUNNING) run for a task, if any."""
        row = self._query_one(
            "SELECT * FROM task_runs WHERE task_id = ? AND status IN ('PENDING', 'RUNNING') "
            "ORDER BY created_at DESC LIMIT 1"
            if self.backend == "sqlite"
            else
            "SELECT * FROM task_runs WHERE task_id = %s AND status IN ('PENDING', 'RUNNING') "
            "ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        return self._normalize_task_run_row(row)

    def get_task_run_for_user(self, *, run_id: str, user_id: str, is_admin: bool) -> Optional[Dict[str, Any]]:
        if is_admin:
            row = self._query_one(
                "SELECT * FROM task_runs WHERE id = ?" if self.backend == "sqlite" else "SELECT * FROM task_runs WHERE id = %s",
                (run_id,),
            )
        else:
            row = self._query_one(
                "SELECT * FROM task_runs WHERE id = ? AND user_id = ?"
                if self.backend == "sqlite"
                else
                "SELECT * FROM task_runs WHERE id = %s AND user_id = %s",
                (run_id, user_id),
            )
        return self._normalize_task_run_row(row)

    def get_latest_task_run_for_task(self, *, task_id: str, user_id: str, is_admin: bool) -> Optional[Dict[str, Any]]:
        if is_admin:
            row = self._query_one(
                "SELECT * FROM task_runs WHERE task_id = ? ORDER BY created_at DESC LIMIT 1"
                if self.backend == "sqlite"
                else
                "SELECT * FROM task_runs WHERE task_id = %s ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            )
        else:
            row = self._query_one(
                "SELECT * FROM task_runs WHERE task_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 1"
                if self.backend == "sqlite"
                else
                "SELECT * FROM task_runs WHERE task_id = %s AND user_id = %s ORDER BY created_at DESC LIMIT 1",
                (task_id, user_id),
            )
        return self._normalize_task_run_row(row)

    def get_task_file_for_user(
        self,
        *,
        task_id: str,
        file_type: str,
        user_id: str,
        is_admin: bool,
    ) -> Optional[Dict[str, Any]]:
        if is_admin:
            sql = (
                """
                SELECT tf.*, t.user_id
                FROM task_files tf
                JOIN tasks t ON t.id = tf.task_id
                WHERE tf.task_id = ? AND tf.file_type = ? AND tf.deleted_at IS NULL
                """
                if self.backend == "sqlite"
                else
                """
                SELECT tf.*, t.user_id
                FROM task_files tf
                JOIN tasks t ON t.id = tf.task_id
                WHERE tf.task_id = %s AND tf.file_type = %s AND tf.deleted_at IS NULL
                """
            )
            params: Sequence[Any] = (task_id, file_type)
        else:
            sql = (
                """
                SELECT tf.*, t.user_id
                FROM task_files tf
                JOIN tasks t ON t.id = tf.task_id
                WHERE tf.task_id = ? AND tf.file_type = ? AND t.user_id = ? AND tf.deleted_at IS NULL
                """
                if self.backend == "sqlite"
                else
                """
                SELECT tf.*, t.user_id
                FROM task_files tf
                JOIN tasks t ON t.id = tf.task_id
                WHERE tf.task_id = %s AND tf.file_type = %s AND t.user_id = %s AND tf.deleted_at IS NULL
                """
            )
            params = (task_id, file_type, user_id)

        row = self._query_one(sql, params)
        if row is None:
            return None
        return dict(row)

    def record_audit_event(
        self,
        *,
        event_type: str,
        actor_user_id: str = "",
        target_user_id: str = "",
        entity_type: str = "",
        entity_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: str = "",
        user_agent: str = "",
    ):
        now = self._now_ts()
        self._execute(
            """
            INSERT INTO audit_events (
                id, actor_user_id, target_user_id, event_type,
                entity_type, entity_id, metadata_json, ip_address, user_agent, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            if self.backend == "sqlite"
            else
            """
            INSERT INTO audit_events (
                id, actor_user_id, target_user_id, event_type,
                entity_type, entity_id, metadata_json, ip_address, user_agent, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4().hex,
                actor_user_id or None,
                target_user_id or None,
                str(event_type or "unknown"),
                entity_type or None,
                entity_id or None,
                self._safe_json_dump(metadata or {}),
                (ip_address or "")[:128],
                (user_agent or "")[:512],
                now,
            ),
        )

    def list_users(self, limit: int = 200) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(500, int(limit or 200)))
        rows = self._query_all(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?"
            if self.backend == "sqlite"
            else
            "SELECT * FROM users ORDER BY created_at DESC LIMIT %s",
            (safe_limit,),
        )
        return [self._normalize_user_row(row) for row in rows if row]

    def set_user_status(self, *, user_id: str, status: str) -> Optional[Dict[str, Any]]:
        safe_status = STATUS_ACTIVE if str(status or "").upper() == STATUS_ACTIVE else STATUS_INACTIVE
        now = self._now_ts()
        self._execute(
            "UPDATE users SET status = ?, updated_at = ? WHERE id = ?"
            if self.backend == "sqlite"
            else
            "UPDATE users SET status = %s, updated_at = %s WHERE id = %s",
            (safe_status, now, user_id),
        )
        if safe_status == STATUS_INACTIVE:
            self.revoke_sessions_for_user(user_id)
        return self.get_user_by_id(user_id)

    def list_audit_events(
        self,
        *,
        limit: int = 200,
        actor_user_id: str = "",
        event_type: str = "",
        date_from: int = 0,
        date_to: int = 0,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(1000, int(limit or 200)))
        clauses = ["1=1"]
        params: List[Any] = []

        def push(clause_sql: str, value: Any):
            clauses.append(clause_sql)
            params.append(value)

        placeholder = "?" if self.backend == "sqlite" else "%s"

        if actor_user_id:
            push(f"ae.actor_user_id = {placeholder}", actor_user_id)
        if event_type:
            push(f"ae.event_type = {placeholder}", event_type)
        if date_from:
            push(f"ae.created_at >= {placeholder}", int(date_from))
        if date_to:
            push(f"ae.created_at <= {placeholder}", int(date_to))

        params.append(safe_limit)

        sql = (
            """
            SELECT
                ae.*,
                actor.email AS actor_email,
                target.email AS target_email
            FROM audit_events ae
            LEFT JOIN users actor ON actor.id = ae.actor_user_id
            LEFT JOIN users target ON target.id = ae.target_user_id
            WHERE {where_clause}
            ORDER BY ae.created_at DESC
            LIMIT ?
            """
            if self.backend == "sqlite"
            else
            """
            SELECT
                ae.*,
                actor.email AS actor_email,
                target.email AS target_email
            FROM audit_events ae
            LEFT JOIN users actor ON actor.id = ae.actor_user_id
            LEFT JOIN users target ON target.id = ae.target_user_id
            WHERE {where_clause}
            ORDER BY ae.created_at DESC
            LIMIT %s
            """
        ).format(where_clause=" AND ".join(clauses))

        rows = self._query_all(sql, params)
        out = []
        for row in rows:
            event = dict(row)
            event["metadata"] = self._safe_json_load(event.get("metadata_json"))
            out.append(event)
        return out

    def get_expired_task_files(self, now_ts: int) -> List[Dict[str, Any]]:
        rows = self._query_all(
            "SELECT * FROM task_files WHERE deleted_at IS NULL AND expires_at <= ?"
            if self.backend == "sqlite"
            else
            "SELECT * FROM task_files WHERE deleted_at IS NULL AND expires_at <= %s",
            (int(now_ts),),
        )
        return [dict(row) for row in rows]

    def mark_task_file_deleted(self, task_file_id: str, deleted_at: int):
        self._execute(
            "UPDATE task_files SET deleted_at = ? WHERE id = ?" if self.backend == "sqlite" else "UPDATE task_files SET deleted_at = %s WHERE id = %s",
            (int(deleted_at), task_file_id),
        )

    def purge_expired_sessions(self):
        now = self._now_ts()
        self._execute(
            "DELETE FROM user_sessions WHERE expires_at <= ? OR revoked_at IS NOT NULL"
            if self.backend == "sqlite"
            else
            "DELETE FROM user_sessions WHERE expires_at <= %s OR revoked_at IS NOT NULL",
            (now,),
        )

    def get_app_setting(self, key: str) -> Optional[Dict[str, Any]]:
        row = self._query_one(
            "SELECT * FROM app_settings WHERE key = ?" if self.backend == "sqlite" else "SELECT * FROM app_settings WHERE key = %s",
            (str(key or "").strip(),),
        )
        if row is None:
            return None
        item = dict(row)
        item["value"] = self._safe_json_load(item.get("value_json"))
        return item

    def upsert_app_setting(self, *, key: str, value: Dict[str, Any], updated_by_user_id: str = ""):
        safe_key = str(key or "").strip()
        if not safe_key:
            return
        now = self._now_ts()
        exists = self._query_one(
            "SELECT key FROM app_settings WHERE key = ?" if self.backend == "sqlite" else "SELECT key FROM app_settings WHERE key = %s",
            (safe_key,),
        )
        payload_json = self._safe_json_dump(value or {})
        if exists:
            self._execute(
                "UPDATE app_settings SET value_json = ?, updated_by_user_id = ?, updated_at = ? WHERE key = ?"
                if self.backend == "sqlite"
                else
                "UPDATE app_settings SET value_json = %s, updated_by_user_id = %s, updated_at = %s WHERE key = %s",
                (payload_json, updated_by_user_id or None, now, safe_key),
            )
            return
        self._execute(
            "INSERT INTO app_settings (key, value_json, updated_by_user_id, updated_at) VALUES (?, ?, ?, ?)"
            if self.backend == "sqlite"
            else
            "INSERT INTO app_settings (key, value_json, updated_by_user_id, updated_at) VALUES (%s, %s, %s, %s)",
            (safe_key, payload_json, updated_by_user_id or None, now),
        )

    # ------------------------------------------------------------------
    # Error events
    # ------------------------------------------------------------------

    ERROR_DEDUPE_WINDOW_SECONDS = 300
    MAX_TRACEBACK_CHARS = 8000
    MAX_MESSAGE_CHARS = 2000

    @staticmethod
    def _error_fingerprint(*, source: str, code: str, exception_type: str, message: str) -> str:
        """Group repeats of the same failure.

        The message is normalised first so ids, paths and numbers inside it do
        not split one recurring fault into thousands of distinct rows.
        """
        normalized = str(message or "")
        normalized = re.sub(r"\b[0-9a-f]{8,}\b", "<id>", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\d+", "<n>", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()[:400]
        raw = "|".join([str(source or ""), str(code or ""), str(exception_type or ""), normalized])
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]

    def record_error_event(
        self,
        *,
        code: str,
        message: str,
        source: str = "app",
        level: str = "ERROR",
        exception_type: str = "",
        traceback_text: str = "",
        request_method: str = "",
        request_path: str = "",
        status_code: int = 0,
        actor_user_id: str = "",
        task_id: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record one error occurrence, collapsing repeats within a short window."""
        now = self._now_ts()
        safe_message = str(message or "")[: self.MAX_MESSAGE_CHARS]
        safe_traceback = str(traceback_text or "")[: self.MAX_TRACEBACK_CHARS]
        fingerprint = self._error_fingerprint(
            source=source, code=code, exception_type=exception_type, message=safe_message
        )
        placeholder = "?" if self.backend == "sqlite" else "%s"

        existing = self._query_one(
            f"SELECT id, occurrence_count FROM error_events "
            f"WHERE fingerprint = {placeholder} AND last_seen_at >= {placeholder} "
            f"ORDER BY last_seen_at DESC LIMIT 1",
            (fingerprint, now - self.ERROR_DEDUPE_WINDOW_SECONDS),
        )
        if existing:
            self._execute(
                f"UPDATE error_events SET occurrence_count = occurrence_count + 1, last_seen_at = {placeholder} "
                f"WHERE id = {placeholder}",
                (now, existing["id"]),
            )
            return {
                "id": str(existing["id"]),
                "fingerprint": fingerprint,
                "deduplicated": True,
                "occurrence_count": int(existing.get("occurrence_count") or 0) + 1,
            }

        event_id = uuid.uuid4().hex
        columns = (
            "id, fingerprint, level, source, code, message, exception_type, traceback, "
            "request_method, request_path, status_code, actor_user_id, task_id, context_json, "
            "occurrence_count, created_at, last_seen_at"
        )
        marks = ", ".join([placeholder] * 17)
        self._execute(
            f"INSERT INTO error_events ({columns}) VALUES ({marks})",
            (
                event_id,
                fingerprint,
                str(level or "ERROR").upper()[:16],
                str(source or "app")[:120],
                str(code or "UNKNOWN")[:120],
                safe_message,
                str(exception_type or "")[:120],
                safe_traceback,
                str(request_method or "")[:12],
                str(request_path or "")[:512],
                int(status_code or 0),
                str(actor_user_id or "") or None,
                str(task_id or "") or None,
                self._safe_json_dump(context or {}),
                1,
                now,
                now,
            ),
        )
        return {"id": event_id, "fingerprint": fingerprint, "deduplicated": False, "occurrence_count": 1}

    def _normalize_error_row(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        item = dict(row)
        item["context"] = self._safe_json_load(item.pop("context_json", None))
        item["occurrence_count"] = int(item.get("occurrence_count") or 1)
        item["status_code"] = int(item.get("status_code") or 0)
        for key in ("actor_user_id", "task_id", "exception_type", "request_method", "request_path", "traceback"):
            item[key] = str(item.get(key) or "")
        return item

    def list_error_events(
        self,
        *,
        limit: int = 100,
        level: str = "",
        code: str = "",
        source: str = "",
        task_id: str = "",
        actor_user_id: str = "",
        since_ts: int = 0,
        include_traceback: bool = False,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(500, int(limit or 100)))
        placeholder = "?" if self.backend == "sqlite" else "%s"
        clauses = ["1=1"]
        params: List[Any] = []

        def push(clause_sql: str, value: Any):
            clauses.append(clause_sql)
            params.append(value)

        if level:
            push(f"ee.level = {placeholder}", str(level).upper())
        if code:
            push(f"ee.code = {placeholder}", str(code))
        if source:
            push(f"ee.source = {placeholder}", str(source))
        if task_id:
            push(f"ee.task_id = {placeholder}", str(task_id))
        if actor_user_id:
            push(f"ee.actor_user_id = {placeholder}", str(actor_user_id))
        if since_ts:
            push(f"ee.last_seen_at >= {placeholder}", int(since_ts))

        params.append(safe_limit)
        sql = (
            "SELECT ee.*, actor.email AS actor_email FROM error_events ee "
            "LEFT JOIN users actor ON actor.id = ee.actor_user_id "
            f"WHERE {' AND '.join(clauses)} "
            f"ORDER BY ee.last_seen_at DESC LIMIT {placeholder}"
        )
        rows = [self._normalize_error_row(row) for row in self._query_all(sql, tuple(params))]
        if not include_traceback:
            for row in rows:
                row.pop("traceback", None)
        return [row for row in rows if row]

    def get_error_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        placeholder = "?" if self.backend == "sqlite" else "%s"
        row = self._query_one(
            "SELECT ee.*, actor.email AS actor_email FROM error_events ee "
            "LEFT JOIN users actor ON actor.id = ee.actor_user_id "
            f"WHERE ee.id = {placeholder}",
            (str(event_id or ""),),
        )
        return self._normalize_error_row(row)

    def summarize_error_events(self, *, since_ts: int = 0, limit: int = 10) -> Dict[str, Any]:
        """Aggregate counts for the admin health view."""
        placeholder = "?" if self.backend == "sqlite" else "%s"
        where = f"WHERE last_seen_at >= {placeholder}" if since_ts else ""
        params: Tuple[Any, ...] = (int(since_ts),) if since_ts else ()

        totals = self._query_one(
            "SELECT COALESCE(SUM(occurrence_count), 0) AS total_occurrences, "
            "COUNT(*) AS distinct_faults, "
            "COALESCE(MAX(last_seen_at), 0) AS latest_at "
            f"FROM error_events {where}",
            params,
        ) or {}

        by_level = self._query_all(
            f"SELECT level, COALESCE(SUM(occurrence_count), 0) AS occurrences FROM error_events {where} GROUP BY level",
            params,
        )
        safe_limit = max(1, min(50, int(limit or 10)))
        top_params = params + (safe_limit,)
        top_codes = self._query_all(
            "SELECT code, source, COALESCE(SUM(occurrence_count), 0) AS occurrences, MAX(last_seen_at) AS last_seen_at "
            f"FROM error_events {where} GROUP BY code, source ORDER BY occurrences DESC LIMIT {placeholder}",
            top_params,
        )
        return {
            "total_occurrences": int(totals.get("total_occurrences") or 0),
            "distinct_faults": int(totals.get("distinct_faults") or 0),
            "latest_at": int(totals.get("latest_at") or 0),
            "by_level": {str(row.get("level") or "ERROR"): int(row.get("occurrences") or 0) for row in by_level},
            "top_codes": [
                {
                    "code": str(row.get("code") or ""),
                    "source": str(row.get("source") or ""),
                    "occurrences": int(row.get("occurrences") or 0),
                    "last_seen_at": int(row.get("last_seen_at") or 0),
                }
                for row in top_codes
            ],
        }

    def purge_error_events(self, *, before_ts: int = 0) -> int:
        """Delete error rows older than a cutoff, or all rows when none is given."""
        placeholder = "?" if self.backend == "sqlite" else "%s"
        if before_ts:
            row = self._query_one(
                f"SELECT COUNT(*) AS n FROM error_events WHERE last_seen_at < {placeholder}", (int(before_ts),)
            )
            removed = int((row or {}).get("n") or 0)
            self._execute(f"DELETE FROM error_events WHERE last_seen_at < {placeholder}", (int(before_ts),))
            return removed
        row = self._query_one("SELECT COUNT(*) AS n FROM error_events")
        removed = int((row or {}).get("n") or 0)
        self._execute("DELETE FROM error_events")
        return removed

    def _normalize_journal_row(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        item = dict(row)
        item["keywords"] = self._safe_json_load(item.get("keywords_json")).get("items", [])
        item["subject_areas"] = self._safe_json_load(item.get("subject_areas_json")).get("items", [])
        item["article_types"] = self._safe_json_load(item.get("article_types_json")).get("items", [])
        item["open_access"] = bool(item.get("open_access"))
        item["is_active"] = bool(item.get("is_active"))
        item["apc_usd"] = float(item.get("apc_usd") or 0.0)
        return item

    def list_journals(self, *, include_inactive: bool = True, limit: int = 500) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(2000, int(limit or 500)))
        if include_inactive:
            rows = self._query_all(
                "SELECT * FROM journals ORDER BY updated_at DESC LIMIT ?"
                if self.backend == "sqlite"
                else
                "SELECT * FROM journals ORDER BY updated_at DESC LIMIT %s",
                (safe_limit,),
            )
        else:
            rows = self._query_all(
                "SELECT * FROM journals WHERE is_active = 1 ORDER BY updated_at DESC LIMIT ?"
                if self.backend == "sqlite"
                else
                "SELECT * FROM journals WHERE is_active = 1 ORDER BY updated_at DESC LIMIT %s",
                (safe_limit,),
            )
        return [self._normalize_journal_row(row) for row in rows if row]

    def get_journal(self, journal_id: str) -> Optional[Dict[str, Any]]:
        row = self._query_one(
            "SELECT * FROM journals WHERE id = ?" if self.backend == "sqlite" else "SELECT * FROM journals WHERE id = %s",
            (str(journal_id or "").strip(),),
        )
        return self._normalize_journal_row(row)

    def create_journal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = self._now_ts()
        journal_id = uuid.uuid4().hex
        keywords = payload.get("keywords") if isinstance(payload.get("keywords"), list) else []
        subject_areas = payload.get("subject_areas") if isinstance(payload.get("subject_areas"), list) else []
        article_types = payload.get("article_types") if isinstance(payload.get("article_types"), list) else []
        self._execute(
            """
            INSERT INTO journals (
                id, name, scope, keywords_json, subject_areas_json, article_types_json,
                issn_print, issn_online, publisher, quartile, open_access, apc_usd,
                submission_url, is_active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            if self.backend == "sqlite"
            else
            """
            INSERT INTO journals (
                id, name, scope, keywords_json, subject_areas_json, article_types_json,
                issn_print, issn_online, publisher, quartile, open_access, apc_usd,
                submission_url, is_active, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                journal_id,
                str(payload.get("name") or "").strip(),
                str(payload.get("scope") or "").strip(),
                self._safe_json_dump({"items": keywords}),
                self._safe_json_dump({"items": subject_areas}),
                self._safe_json_dump({"items": article_types}),
                str(payload.get("issn_print") or "").strip(),
                str(payload.get("issn_online") or "").strip(),
                str(payload.get("publisher") or "").strip(),
                str(payload.get("quartile") or "").strip().upper(),
                1 if bool(payload.get("open_access", False)) else 0,
                float(payload.get("apc_usd") or 0.0),
                str(payload.get("submission_url") or "").strip(),
                1 if bool(payload.get("is_active", True)) else 0,
                now,
                now,
            ),
        )
        return self.get_journal(journal_id) or {}

    def update_journal(self, journal_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = self.get_journal(journal_id)
        if current is None:
            return None
        now = self._now_ts()
        keywords = payload.get("keywords") if isinstance(payload.get("keywords"), list) else current.get("keywords", [])
        subject_areas = payload.get("subject_areas") if isinstance(payload.get("subject_areas"), list) else current.get("subject_areas", [])
        article_types = payload.get("article_types") if isinstance(payload.get("article_types"), list) else current.get("article_types", [])
        self._execute(
            """
            UPDATE journals
            SET name = ?, scope = ?, keywords_json = ?, subject_areas_json = ?, article_types_json = ?,
                issn_print = ?, issn_online = ?, publisher = ?, quartile = ?, open_access = ?, apc_usd = ?,
                submission_url = ?, is_active = ?, updated_at = ?
            WHERE id = ?
            """
            if self.backend == "sqlite"
            else
            """
            UPDATE journals
            SET name = %s, scope = %s, keywords_json = %s, subject_areas_json = %s, article_types_json = %s,
                issn_print = %s, issn_online = %s, publisher = %s, quartile = %s, open_access = %s, apc_usd = %s,
                submission_url = %s, is_active = %s, updated_at = %s
            WHERE id = %s
            """,
            (
                str((payload.get("name") if ("name" in payload and payload.get("name") is not None) else current.get("name")) or "").strip(),
                str((payload.get("scope") if ("scope" in payload and payload.get("scope") is not None) else current.get("scope")) or "").strip(),
                self._safe_json_dump({"items": keywords}),
                self._safe_json_dump({"items": subject_areas}),
                self._safe_json_dump({"items": article_types}),
                str((payload.get("issn_print") if ("issn_print" in payload and payload.get("issn_print") is not None) else current.get("issn_print")) or "").strip(),
                str((payload.get("issn_online") if ("issn_online" in payload and payload.get("issn_online") is not None) else current.get("issn_online")) or "").strip(),
                str((payload.get("publisher") if ("publisher" in payload and payload.get("publisher") is not None) else current.get("publisher")) or "").strip(),
                str((payload.get("quartile") if ("quartile" in payload and payload.get("quartile") is not None) else current.get("quartile")) or "").strip().upper(),
                1 if bool(payload.get("open_access", current.get("open_access", False))) else 0,
                float(payload.get("apc_usd", current.get("apc_usd", 0.0)) or 0.0),
                str((payload.get("submission_url") if ("submission_url" in payload and payload.get("submission_url") is not None) else current.get("submission_url")) or "").strip(),
                1 if bool(payload.get("is_active", current.get("is_active", True))) else 0,
                now,
                str(journal_id),
            ),
        )
        return self.get_journal(journal_id)

    def deactivate_journal(self, journal_id: str) -> Optional[Dict[str, Any]]:
        now = self._now_ts()
        self._execute(
            "UPDATE journals SET is_active = 0, updated_at = ? WHERE id = ?"
            if self.backend == "sqlite"
            else
            "UPDATE journals SET is_active = 0, updated_at = %s WHERE id = %s",
            (now, str(journal_id)),
        )
        return self.get_journal(journal_id)

    def seed_default_journals(self, journals: Sequence[Dict[str, Any]]) -> int:
        existing = self.list_journals(include_inactive=True, limit=1)
        if existing:
            return 0
        inserted = 0
        for item in journals or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            self.create_journal(item)
            inserted += 1
        return inserted

    def _normalize_task_row(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        item = dict(row)
        item["options"] = self._safe_json_load(item.get("options_json"))
        item["reports"] = self._safe_json_load(item.get("reports_json"))
        return item

    def _normalize_task_run_row(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        item = dict(row)
        item["options"] = self._safe_json_load(item.get("options_json"))
        item["result"] = self._safe_json_load(item.get("result_json"))
        try:
            item["progress_percent"] = float(item.get("progress_percent") or 0.0)
        except Exception:
            item["progress_percent"] = 0.0
        item["stage"] = str(item.get("stage") or "")
        try:
            item["tokens_consumed"] = int(item.get("tokens_consumed") or 0)
        except Exception:
            item["tokens_consumed"] = 0
        try:
            item["estimated_seconds_remaining"] = int(item.get("estimated_seconds_remaining") or 0)
        except Exception:
            item["estimated_seconds_remaining"] = 0
        return item

    def clear_all_for_tests(self):
        """Utility for tests to reset database content."""
        self._execute("DELETE FROM error_events")
        self._execute("DELETE FROM task_runs")
        self._execute("DELETE FROM journals")
        self._execute("DELETE FROM task_files")
        self._execute("DELETE FROM tasks")
        self._execute("DELETE FROM user_sessions")
        self._execute("DELETE FROM audit_events")
        self._execute("DELETE FROM app_settings")
        self._execute("DELETE FROM users")
