#!/usr/bin/env python3
"""Small in-process background job queue for web task processing."""

from __future__ import annotations

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

    def submit(self, *, task_id: str, owner_user_id: str, callback: Callable[[], Dict]) -> Dict:
        job = BackgroundJob(id=uuid.uuid4().hex, task_id=str(task_id or ""), owner_user_id=str(owner_user_id or ""))
        with self._lock:
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

    def _mark_failed(self, job_id: str, error: str) -> None:
        now = int(time.time())
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = JOB_FAILED
            job.finished_at = now
            job.error = str(error or "Job failed")

    def update_progress(self, task_id: str, progress_percent: float, stage: str, tokens_consumed: int = 0, estimated_seconds_remaining: int = 0):
        with self._lock:
            job_id = self._latest_by_task.get(str(task_id or ""))
            if not job_id:
                return
            job = self._jobs.get(job_id)
            if job:
                job.progress_percent = float(progress_percent)
                job.stage = str(stage or "")
                job.tokens_consumed = int(tokens_consumed)
                job.estimated_seconds_remaining = int(estimated_seconds_remaining)
