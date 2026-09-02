#!/usr/bin/env python3
"""Small in-process background job queue for web task processing.

The queue is a per-process fast path only. Authoritative run state lives in the
``task_runs`` table so status polling works across gunicorn workers and survives
a restart.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional


JOB_PENDING = "PENDING"
JOB_RUNNING = "RUNNING"
JOB_SUCCEEDED = "SUCCEEDED"
JOB_FAILED = "FAILED"

_TERMINAL_STATUSES = (JOB_SUCCEEDED, JOB_FAILED)


def _env_int(key: str, default_value: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(os.getenv(key, "") or default_value)
    except Exception:
        parsed = default_value
    return max(min_value, min(max_value, parsed))


# Finished jobs are kept only long enough for an in-flight poll to read them.
JOB_RETENTION_SECONDS = _env_int("PROCESSING_JOB_RETENTION_SECONDS", 900, 60, 86_400)
JOB_MAX_TRACKED = _env_int("PROCESSING_JOB_MAX_TRACKED", 200, 10, 10_000)


@dataclass
class BackgroundJob:
    id: str
    task_id: str
    owner_user_id: str
    status: str = JOB_PENDING
    created_at: int = field(default_factory=lambda: int(time.time()))
    started_at: int = 0
    finished_at: int = 0
    error: str = ""
    result: Optional[Dict] = None
    progress_percent: float = 0.0
    stage: str = "Initializing"
    tokens_consumed: int = 0
    estimated_seconds_remaining: int = 0

    def snapshot(self) -> Dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "result": self.result if self.status == JOB_SUCCEEDED else None,
            "progress_percent": self.progress_percent,
            "stage": self.stage,
            "tokens_consumed": self.tokens_consumed,
            "estimated_seconds_remaining": self.estimated_seconds_remaining,
        }


class BackgroundJobQueue:
    """Thread-pool backed queue scoped to a single web process."""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max(1, int(max_workers or 1)), thread_name_prefix="task-job")
        self._lock = threading.Lock()
        self._jobs: Dict[str, BackgroundJob] = {}
        self._latest_by_task: Dict[str, str] = {}

    @staticmethod
    def new_job_id() -> str:
        """Allocate a job id ahead of submission.

        Callers persist the id before the worker thread starts so the request
        thread never has to write back to the run row afterwards.
        """
        return uuid.uuid4().hex

    def submit(
        self,
        *,
        task_id: str,
        owner_user_id: str,
        callback: Callable[[], Dict],
        job_id: str = "",
    ) -> Dict:
        job = BackgroundJob(
            id=str(job_id or "").strip() or self.new_job_id(),
            task_id=str(task_id or ""),
            owner_user_id=str(owner_user_id or ""),
        )
        with self._lock:
            self._evict_locked()
            self._jobs[job.id] = job
            self._latest_by_task[job.task_id] = job.id
        self._executor.submit(self._run_job, job.id, callback)
        return job.snapshot()

    def get(self, job_id: str, *, owner_user_id: str = "", is_admin: bool = False) -> Optional[Dict]:
        with self._lock:
            job = self._jobs.get(str(job_id or ""))
            if job is None:
                return None
            if not is_admin and owner_user_id and job.owner_user_id != owner_user_id:
                return None
            return job.snapshot()

    def latest_for_task(self, task_id: str, *, owner_user_id: str = "", is_admin: bool = False) -> Optional[Dict]:
        with self._lock:
            job_id = self._latest_by_task.get(str(task_id or ""))
        if not job_id:
            return None
        return self.get(job_id, owner_user_id=owner_user_id, is_admin=is_admin)

    def _run_job(self, job_id: str, callback: Callable[[], Dict]) -> None:
        self._mark_running(job_id)
        try:
            result = callback()
        except Exception as exc:  # pragma: no cover - exercised through web route integration
            self._mark_failed(job_id, str(exc))
            return
        self._mark_succeeded(job_id, result)

    def _mark_running(self, job_id: str) -> None:
        now = int(time.time())
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = JOB_RUNNING
            job.started_at = now

    def _mark_succeeded(self, job_id: str, result: Dict) -> None:
        now = int(time.time())
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = JOB_SUCCEEDED
            job.finished_at = now
            job.result = result if isinstance(result, dict) else {}
            job.progress_percent = 100.0
            job.estimated_seconds_remaining = 0

    def _mark_failed(self, job_id: str, error: str) -> None:
        now = int(time.time())
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = JOB_FAILED
            job.finished_at = now
            job.error = str(error or "Job failed")

    def update_progress(
        self,
        task_id: str,
        progress_percent: float,
        stage: str,
        tokens_consumed: int = 0,
        estimated_seconds_remaining: int = 0,
        job_id: str = "",
    ):
        with self._lock:
            resolved_id = str(job_id or "").strip() or self._latest_by_task.get(str(task_id or ""), "")
            if not resolved_id:
                return
            job = self._jobs.get(resolved_id)
            if job is None or job.status in _TERMINAL_STATUSES:
                return
            job.progress_percent = float(progress_percent)
            job.stage = str(stage or "")
            job.tokens_consumed = int(tokens_consumed)
            job.estimated_seconds_remaining = int(estimated_seconds_remaining)

    def _evict_locked(self) -> None:
        """Drop finished jobs. Called with the lock held."""
        cutoff = int(time.time()) - JOB_RETENTION_SECONDS
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in _TERMINAL_STATUSES and job.finished_at and job.finished_at <= cutoff
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)

        overflow = len(self._jobs) - JOB_MAX_TRACKED
        if overflow > 0:
            finished = sorted(
                (job for job in self._jobs.values() if job.status in _TERMINAL_STATUSES),
                key=lambda job: job.finished_at or job.created_at,
            )
            for job in finished[:overflow]:
                self._jobs.pop(job.id, None)

        live_ids = set(self._jobs)
        stale_tasks = [task_id for task_id, job_id in self._latest_by_task.items() if job_id not in live_ids]
        for task_id in stale_tasks:
            self._latest_by_task.pop(task_id, None)

    def tracked_job_count(self) -> int:
        with self._lock:
            return len(self._jobs)
