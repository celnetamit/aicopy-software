"""Task ownership, run-row concurrency and restart-recovery guards.

Covers the correctness defects found at the module seams:

* an admin could read any task but never write one back (silent HTTP 500)
* two writers on the same run row raced through a read-modify-write
* a restart left runs PENDING/RUNNING forever with their tasks stuck PROCESSING
* nothing stopped a second run being queued for a task already processing
"""

import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_store import AppStore  # noqa: E402
from job_queue import BackgroundJobQueue  # noqa: E402


class StoreFixture(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp(prefix="task-run-tests-")
        self.store = AppStore(database_url="", data_dir=self.data_dir)
        self.owner = self.store.upsert_google_user(
            email="owner@example.com",
            display_name="Owner",
            google_sub="sub-owner",
            domain="example.com",
            admin_emails=[],
        )
        self.admin = self.store.upsert_google_user(
            email="admin@example.com",
            display_name="Admin",
            google_sub="sub-admin",
            domain="example.com",
            admin_emails=["admin@example.com"],
        )
        self.other = self.store.upsert_google_user(
            email="other@example.com",
            display_name="Other",
            google_sub="sub-other",
            domain="example.com",
            admin_emails=[],
        )
        self.store.create_task(
            task_id="task-1",
            user_id=self.owner["id"],
            file_name="m.txt",
            source_type="text",
            source_path="tasks/task-1/source.txt",
            original_text="The colour of the sample.",
            options={},
        )


class AdminTaskWriteTests(StoreFixture):
    def test_admin_can_write_a_task_it_does_not_own(self):
        self.assertIsNotNone(
            self.store.get_task_for_user(task_id="task-1", user_id=self.admin["id"], is_admin=True),
            "admin should be able to read any task",
        )
        updated = self.store.update_task_processing_result(
            task_id="task-1",
            user_id=self.owner["id"],
            corrected_text="The color of the sample.",
            full_corrected_text="The color of the sample.",
            word_count=5,
            options={},
            reports={},
            is_admin=True,
        )
        self.assertIsNotNone(updated, "admin write returned None — the route would raise 'Task update failed'")
        self.assertEqual(updated["corrected_text"], "The color of the sample.")
        self.assertEqual(updated["status"], "PROCESSED")
        self.assertEqual(updated["user_id"], self.owner["id"], "ownership must not transfer to the actor")

    def test_admin_can_write_corrected_text_it_does_not_own(self):
        updated = self.store.update_task_corrected_text(
            task_id="task-1",
            user_id=self.owner["id"],
            corrected_text="Decision applied.",
            reports={"redline_html": "<p>x</p>"},
            is_admin=True,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["corrected_text"], "Decision applied.")

    def test_non_admin_still_cannot_write_another_users_task(self):
        result = self.store.update_task_processing_result(
            task_id="task-1",
            user_id=self.other["id"],
            corrected_text="hijacked",
            full_corrected_text="hijacked",
            word_count=1,
            options={},
            reports={},
            is_admin=False,
        )
        self.assertIsNone(result, "a non-admin must not be able to write another user's task")
        task = self.store.get_task_for_user(task_id="task-1", user_id=self.owner["id"], is_admin=False)
        self.assertNotEqual(task["corrected_text"], "hijacked")

    def test_owner_write_is_unaffected(self):
        updated = self.store.update_task_processing_result(
            task_id="task-1",
            user_id=self.owner["id"],
            corrected_text="ok",
            full_corrected_text="ok",
            word_count=1,
            options={},
            reports={},
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["corrected_text"], "ok")


class TaskRunUpdateTests(StoreFixture):
    def create_run(self, job_id: str = "job-1"):
        return self.store.create_task_run(
            task_id="task-1",
            user_id=self.owner["id"],
            status="PENDING",
            options={"a": 1},
            job_id=job_id,
        )

    def test_job_id_is_durable_at_insert(self):
        run = self.create_run("job-abc")
        self.assertEqual(run["job_id"], "job-abc")

    def test_updates_touch_only_the_supplied_columns(self):
        run = self.create_run()
        run_id = run["id"]

        self.store.update_task_run(run_id=run_id, user_id=self.owner["id"], status="RUNNING")
        self.store.update_task_run(
            run_id=run_id, user_id=self.owner["id"], result={"summary": "partial"}
        )

        current = self.store.get_task_run_for_user(run_id=run_id, user_id=self.owner["id"], is_admin=False)
        self.assertEqual(current["status"], "RUNNING", "a result-only write reverted the status")
        self.assertEqual(current["result"], {"summary": "partial"})
        self.assertEqual(current["job_id"], "job-1", "job_id was clobbered by an unrelated write")
        self.assertGreater(int(current["started_at"] or 0), 0)

    def test_concurrent_status_and_progress_writes_do_not_clobber(self):
        run = self.create_run()
        run_id = run["id"]
        errors = []

        def set_status():
            try:
                self.store.update_task_run(run_id=run_id, user_id=self.owner["id"], status="RUNNING")
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        def set_progress():
            try:
                for percent in range(0, 100, 10):
                    self.store.update_task_run(
                        run_id=run_id,
                        user_id=self.owner["id"],
                        progress_percent=float(percent),
                        stage=f"stage {percent}",
                    )
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=set_status), threading.Thread(target=set_progress)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        current = self.store.get_task_run_for_user(run_id=run_id, user_id=self.owner["id"], is_admin=False)
        self.assertEqual(current["status"], "RUNNING", "progress writes reverted the status to PENDING")

    def test_progress_columns_round_trip(self):
        run = self.create_run()
        self.store.update_task_run(
            run_id=run["id"],
            user_id=self.owner["id"],
            status="RUNNING",
            progress_percent=42.5,
            stage="Analyzing references",
            tokens_consumed=1234,
            estimated_seconds_remaining=17,
        )
        current = self.store.get_latest_task_run_for_task(
            task_id="task-1", user_id=self.owner["id"], is_admin=False
        )
        self.assertAlmostEqual(current["progress_percent"], 42.5, places=3)
        self.assertEqual(current["stage"], "Analyzing references")
        self.assertEqual(current["tokens_consumed"], 1234)
        self.assertEqual(current["estimated_seconds_remaining"], 17)

    def test_terminal_status_sets_finished_at_once(self):
        run = self.create_run()
        self.store.update_task_run(run_id=run["id"], user_id=self.owner["id"], status="RUNNING")
        first = self.store.update_task_run(run_id=run["id"], user_id=self.owner["id"], status="SUCCEEDED")
        second = self.store.update_task_run(run_id=run["id"], user_id=self.owner["id"], status="SUCCEEDED")
        self.assertEqual(first["finished_at"], second["finished_at"])


class ActiveRunGuardTests(StoreFixture):
    def test_active_run_is_detected_and_cleared(self):
        self.assertIsNone(self.store.has_active_task_run("task-1"))

        run = self.store.create_task_run(task_id="task-1", user_id=self.owner["id"], status="PENDING")
        self.assertIsNotNone(self.store.has_active_task_run("task-1"))

        self.store.update_task_run(run_id=run["id"], user_id=self.owner["id"], status="RUNNING")
        self.assertIsNotNone(self.store.has_active_task_run("task-1"))

        self.store.update_task_run(run_id=run["id"], user_id=self.owner["id"], status="SUCCEEDED")
        self.assertIsNone(self.store.has_active_task_run("task-1"), "a finished run must not block the next one")


class RestartRecoveryTests(StoreFixture):
    def test_orphaned_runs_are_failed_and_tasks_unstuck(self):
        run = self.store.create_task_run(task_id="task-1", user_id=self.owner["id"], status="PENDING")
        self.store.update_task_run(run_id=run["id"], user_id=self.owner["id"], status="RUNNING")
        self.store.update_task_status(
            task_id="task-1", status="PROCESSING", user_id=self.owner["id"], is_admin=False
        )

        reaped = self.store.reap_orphaned_task_runs()
        self.assertEqual(reaped, 1)

        current = self.store.get_task_run_for_user(run_id=run["id"], user_id=self.owner["id"], is_admin=False)
        self.assertEqual(current["status"], "FAILED")
        self.assertIn("restart", current["error"].lower())

        task = self.store.get_task_for_user(task_id="task-1", user_id=self.owner["id"], is_admin=False)
        self.assertEqual(task["status"], "FAILED", "task left stuck in PROCESSING after restart")
        self.assertIsNone(self.store.has_active_task_run("task-1"))

    def test_reaper_leaves_finished_runs_alone(self):
        run = self.store.create_task_run(task_id="task-1", user_id=self.owner["id"], status="PENDING")
        self.store.update_task_run(run_id=run["id"], user_id=self.owner["id"], status="SUCCEEDED")
        self.assertEqual(self.store.reap_orphaned_task_runs(), 0)
        current = self.store.get_task_run_for_user(run_id=run["id"], user_id=self.owner["id"], is_admin=False)
        self.assertEqual(current["status"], "SUCCEEDED")


class JobQueueTests(unittest.TestCase):
    def test_caller_supplied_job_id_is_used(self):
        queue = BackgroundJobQueue(max_workers=1)
        job_id = queue.new_job_id()
        done = threading.Event()

        def callback():
            done.set()
            return {"ok": True}

        job = queue.submit(task_id="t", owner_user_id="u", callback=callback, job_id=job_id)
        self.assertEqual(job["id"], job_id)
        done.wait(timeout=5)

    def test_finished_jobs_are_evicted(self):
        import job_queue as job_queue_module

        original_retention = job_queue_module.JOB_RETENTION_SECONDS
        job_queue_module.JOB_RETENTION_SECONDS = 0
        try:
            queue = BackgroundJobQueue(max_workers=1)
            finished = threading.Event()
            first = queue.submit(
                task_id="t1", owner_user_id="u", callback=lambda: (finished.set(), {"ok": True})[1]
            )
            finished.wait(timeout=5)
            # Give the worker a moment to record the terminal state.
            for _ in range(50):
                if queue.get(first["id"], is_admin=True)["status"] in ("SUCCEEDED", "FAILED"):
                    break
                threading.Event().wait(0.02)

            second_done = threading.Event()
            queue.submit(task_id="t2", owner_user_id="u", callback=lambda: (second_done.set(), {})[1])
            second_done.wait(timeout=5)

            self.assertIsNone(
                queue.get(first["id"], is_admin=True),
                "finished job was retained past its TTL — the queue leaks payloads",
            )
        finally:
            job_queue_module.JOB_RETENTION_SECONDS = original_retention

    def test_progress_ignores_terminal_jobs(self):
        queue = BackgroundJobQueue(max_workers=1)
        done = threading.Event()
        job = queue.submit(task_id="t", owner_user_id="u", callback=lambda: (done.set(), {"ok": True})[1])
        done.wait(timeout=5)
        for _ in range(50):
            if queue.get(job["id"], is_admin=True)["status"] == "SUCCEEDED":
                break
            threading.Event().wait(0.02)

        queue.update_progress(task_id="t", progress_percent=10.0, stage="late update")
        snapshot = queue.get(job["id"], is_admin=True)
        self.assertEqual(snapshot["progress_percent"], 100.0)
        self.assertNotEqual(snapshot["stage"], "late update")


if __name__ == "__main__":
    unittest.main()
