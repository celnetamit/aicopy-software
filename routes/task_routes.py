"""Task upload, processing, retrieval, and download routes."""

import base64
import time

from bottle import HTTPResponse, request


def register_task_routes(app, deps):
    def _is_transient_autopilot_error(exc: Exception) -> bool:
        text = str(exc or "").strip().lower()
        if not text:
            return False
        transient_markers = (
            "timeout",
            "timed out",
            "connection reset",
            "connection aborted",
            "temporary failure",
            "temporarily unavailable",
            "service unavailable",
            "bad gateway",
            "gateway timeout",
            "too many requests",
            "rate limit",
            "429",
            "502",
            "503",
            "504",
        )
        return any(marker in text for marker in transient_markers)

    @app.post("/api/tasks/upload-text")
    @deps.require_auth
    def api_tasks_upload_text():
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        file_name = str(payload.get("file_name", "manuscript.txt") or "manuscript.txt")
        content = str(payload.get("content", "") or "")
        if len(content) > int(deps.max_text_chars):
            return deps.json_response(
                deps.error_payload("TASK_UPLOAD_TOO_LARGE", f"Text exceeds maximum size of {deps.max_text_chars} characters"),
                status=413,
                session_id=context.session_id,
            )

        try:
            result = deps.upload_text_to_task(context, file_name=file_name, text=content, source_type="text")
            return deps.json_response(result, session_id=context.session_id)
        except Exception as exc:
            return deps.json_response(deps.error_payload("TASK_UPLOAD_FAILED", str(exc)), status=400, session_id=context.session_id)

    @app.post("/api/tasks/upload-docx")
    @deps.require_auth
    def api_tasks_upload_docx():
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        file_name = str(payload.get("file_name", "manuscript.docx") or "manuscript.docx")
        base64_data = str(payload.get("base64_data", "") or "")

        try:
            byte_data = base64.b64decode(base64_data, validate=True)
        except Exception:
            return deps.json_response(deps.error_payload("TASK_UPLOAD_INVALID_BASE64", "Invalid base64 document payload"), status=400)
        if len(byte_data) > int(deps.max_upload_bytes):
            return deps.json_response(
                deps.error_payload("TASK_UPLOAD_TOO_LARGE", f"DOCX exceeds maximum size of {deps.max_upload_bytes} bytes"),
                status=413,
                session_id=context.session_id,
            )

        try:
            result = deps.upload_docx_to_task(context, file_name=file_name, byte_data=byte_data)
            return deps.json_response(result, session_id=context.session_id)
        except Exception as exc:
            return deps.json_response(deps.error_payload("TASK_UPLOAD_FAILED", str(exc)), status=400, session_id=context.session_id)

    @app.get("/api/tasks")
    @deps.require_auth
    def api_tasks_list():
        context = deps.auth_context_from_request()
        try:
            limit = int(str(request.query.get("limit", "100") or "100"))
        except Exception:
            limit = 100
        limit = max(1, min(int(deps.task_list_limit_max), limit))
        status_filter = str(request.query.get("status", "") or "").strip().upper()
        tasks = deps.store.list_tasks_for_user(user_id=context.user_id, limit=limit, status=status_filter)
        return deps.json_response(
            {
                "success": True,
                "tasks": [deps.task_summary(task) for task in tasks],
            },
            session_id=context.session_id,
        )

    @app.get("/api/tasks/<task_id>")
    @deps.require_auth
    def api_tasks_get(task_id: str):
        context = deps.auth_context_from_request()
        task, error = deps.get_owned_task_or_error(context, task_id)
        if error is not None:
            return error

        reports = task.get("reports") or {}

        summary = deps.task_summary(task)
        # Non-eager variants are generated on first download, so availability is a
        # function of task state rather than of what happens to be cached now.
        clean_available = bool(summary.get("can_download_clean"))
        highlighted_available = bool(summary.get("can_download_highlighted"))
        if not clean_available:
            clean_available = deps.store.get_task_file_for_user(
                task_id=task_id,
                file_type="clean",
                user_id=context.user_id,
                is_admin=context.role == deps.role_admin,
            ) is not None
        if not highlighted_available:
            highlighted_available = deps.store.get_task_file_for_user(
                task_id=task_id,
                file_type="highlighted",
                user_id=context.user_id,
                is_admin=context.role == deps.role_admin,
            ) is not None

        payload = {
            "success": True,
            "task": {
                **summary,
                "original_text": str(task.get("original_text") or ""),
                "corrected_text": str(task.get("corrected_text") or ""),
                "full_corrected_text": str(task.get("full_corrected_text") or ""),
                "options": task.get("options") or {},
                "reports": reports,
                "downloads": {
                    "clean": clean_available,
                    "highlighted": highlighted_available,
                },
            },
        }
        return deps.json_response(payload, session_id=context.session_id)

    @app.post("/api/tasks/<task_id>/process")
    @deps.require_auth
    def api_tasks_process(task_id: str):
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        options = payload.get("options", {})
        if not isinstance(options, dict):
            options = {}
        options = deps.apply_global_runtime_settings(
            options,
            deps.read_global_runtime_settings(),
            is_admin=context.role == deps.role_admin,
        )

        task, error = deps.get_owned_task_or_error(context, task_id)
        if error is not None:
            return error

        if bool(payload.get("async", False) or payload.get("background", False)):
            if not bool(payload.get("force", False)):
                active_run = deps.store.has_active_task_run(task_id)
                if active_run is not None:
                    return deps.json_response(
                        deps.error_payload(
                            "TASK_ALREADY_PROCESSING",
                            "This task already has a run in progress. Wait for it to finish, or resend with force=true.",
                            task_run=active_run,
                        ),
                        status=409,
                        session_id=context.session_id,
                    )

            deps.increment_runtime_counter(context.session_id, "process_async_started")
            deps.store.update_task_status(
                task_id=task_id,
                status="PROCESSING",
                user_id=context.user_id,
                is_admin=context.role == deps.role_admin,
            )
            # Allocate the job id up front so it is durable at INSERT time and the
            # request thread never writes back to the row after the worker starts.
            job_id = deps.processing_job_queue.new_job_id()
            task_run = deps.store.create_task_run(
                task_id=task_id,
                user_id=str(task.get("user_id") or context.user_id),
                status="PENDING",
                options=options,
                job_id=job_id,
            )
            task_run_id = str(task_run.get("id") or "")
            deps.increment_runtime_counter(context.session_id, "task_run_pending")
            deps.record_audit(
                event_type="task_run_pending",
                actor_user_id=context.user_id,
                entity_type="task_run",
                entity_id=task_run_id,
                metadata={"task_id": task_id, "status": "PENDING"},
            )

            def run_processing_job():
                started_run = deps.store.update_task_run(
                    run_id=task_run_id,
                    user_id=str(task.get("user_id") or context.user_id),
                    is_admin=context.role == deps.role_admin,
                    status="RUNNING",
                )
                deps.increment_runtime_counter(context.session_id, "task_run_running")
                if isinstance(started_run, dict):
                    created_at = int(started_run.get("created_at") or 0)
                    started_at = int(started_run.get("started_at") or 0)
                    queue_seconds = max(0.0, float(started_at - created_at))
                else:
                    queue_seconds = 0.0
                deps.record_audit(
                    event_type="task_run_running",
                    actor_user_id=context.user_id,
                    entity_type="task_run",
                    entity_id=task_run_id,
                    metadata={"task_id": task_id, "status": "RUNNING", "queue_seconds": queue_seconds},
                )
                try:
                    result = deps.process_task(context, task, options, task_run_id=task_run_id)
                    completed_run = deps.store.update_task_run(
                        run_id=task_run_id,
                        user_id=str(task.get("user_id") or context.user_id),
                        is_admin=context.role == deps.role_admin,
                        status="SUCCEEDED",
                        result=deps.summarize_run_result(result),
                    )
                    deps.increment_runtime_counter(context.session_id, "task_run_succeeded")
                    deps.increment_runtime_counter(context.session_id, "process_async_succeeded")
                    duration_seconds = 0.0
                    if isinstance(completed_run, dict):
                        started_at = int(completed_run.get("started_at") or 0)
                        finished_at = int(completed_run.get("finished_at") or 0)
                        duration_seconds = max(0.0, float(finished_at - started_at))
                    deps.add_runtime_duration_sample(context.session_id, duration_seconds)
                    deps.record_audit(
                        event_type="task_run_succeeded",
                        actor_user_id=context.user_id,
                        entity_type="task_run",
                        entity_id=task_run_id,
                        metadata={"task_id": task_id, "status": "SUCCEEDED", "duration_seconds": duration_seconds},
                    )
                    return result
                except Exception as exc:
                    deps.store.update_task_status(
                        task_id=task_id,
                        status="FAILED",
                        user_id=context.user_id,
                        is_admin=context.role == deps.role_admin,
                    )
                    deps.record_audit(
                        event_type="task_process_failed",
                        actor_user_id=context.user_id,
                        entity_type="task",
                        entity_id=task_id,
                        metadata={
                            "error": str(exc),
                            "async": True,
                            "editing_mode": str(options.get("editing_mode") or "copyedit"),
                            "tone": str(options.get("tone") or "neutral"),
                            "rewrite_strength": str(options.get("rewrite_strength") or "minimal"),
                            "explain_edits": bool(options.get("explain_edits", False)),
                        },
                    )
                    failed_run = deps.store.update_task_run(
                        run_id=task_run_id,
                        user_id=str(task.get("user_id") or context.user_id),
                        is_admin=context.role == deps.role_admin,
                        status="FAILED",
                        error=str(exc),
                    )
                    deps.increment_runtime_counter(context.session_id, "task_run_failed")
                    deps.increment_runtime_counter(context.session_id, "process_async_failed")
                    deps.increment_runtime_counter(context.session_id, "process_runs_failed")
                    duration_seconds = 0.0
                    if isinstance(failed_run, dict):
                        started_at = int(failed_run.get("started_at") or 0)
                        finished_at = int(failed_run.get("finished_at") or 0)
                        duration_seconds = max(0.0, float(finished_at - started_at))
                    deps.add_runtime_duration_sample(context.session_id, duration_seconds)
                    deps.record_audit(
                        event_type="task_run_failed",
                        actor_user_id=context.user_id,
                        entity_type="task_run",
                        entity_id=task_run_id,
                        metadata={"task_id": task_id, "status": "FAILED", "duration_seconds": duration_seconds, "error": str(exc)},
                    )
                    raise

            job = deps.processing_job_queue.submit(
                task_id=task_id,
                owner_user_id=str(task.get("user_id") or context.user_id),
                callback=run_processing_job,
                job_id=job_id,
            )
            deps.record_audit(
                event_type="task_process_queued",
                actor_user_id=context.user_id,
                entity_type="task",
                entity_id=task_id,
                metadata={"job_id": job.get("id", "")},
            )
            return deps.json_response(
                {
                    "success": True,
                    "queued": True,
                    "task_id": task_id,
                    "job": job,
                    "task_run": deps.store.get_task_run_for_user(
                        run_id=task_run_id,
                        user_id=context.user_id,
                        is_admin=context.role == deps.role_admin,
                    ),
                },
                status=202,
                session_id=context.session_id,
            )

        try:
            process_payload = deps.process_task(context, task, options)
            return deps.json_response(process_payload, session_id=context.session_id)
        except Exception as exc:
            deps.increment_runtime_counter(context.session_id, "process_runs_failed")
            deps.record_audit(
                event_type="task_process_failed",
                actor_user_id=context.user_id,
                entity_type="task",
                entity_id=task_id,
                metadata={
                    "error": str(exc),
                    "editing_mode": str(options.get("editing_mode") or "copyedit"),
                    "tone": str(options.get("tone") or "neutral"),
                    "rewrite_strength": str(options.get("rewrite_strength") or "minimal"),
                    "explain_edits": bool(options.get("explain_edits", False)),
                },
            )
            return deps.json_response(deps.error_payload("TASK_PROCESS_FAILED", str(exc)), status=500, session_id=context.session_id)

    @app.get("/api/tasks/<task_id>/process-status")
    @deps.require_auth
    def api_tasks_process_status(task_id: str):
        context = deps.auth_context_from_request()
        task, error = deps.get_owned_task_or_error(context, task_id)
        if error is not None:
            return error

        job = deps.processing_job_queue.latest_for_task(
            task_id=task_id,
            owner_user_id=str(task.get("user_id") or context.user_id),
            is_admin=context.role == deps.role_admin,
        )
        task_run = deps.store.get_latest_task_run_for_task(
            task_id=task_id,
            user_id=context.user_id,
            is_admin=context.role == deps.role_admin,
        )
        # The in-memory job only exists on the worker that ran it. task_runs is
        # authoritative, so synthesize a job-shaped view from it when the local
        # queue has nothing — otherwise progress vanishes on every other worker.
        if job is None and isinstance(task_run, dict) and task_run:
            job = {
                "id": str(task_run.get("job_id") or ""),
                "task_id": task_id,
                "status": str(task_run.get("status") or ""),
                "created_at": int(task_run.get("created_at") or 0),
                "started_at": int(task_run.get("started_at") or 0),
                "finished_at": int(task_run.get("finished_at") or 0),
                "error": str(task_run.get("error") or ""),
                "result": None,
                "progress_percent": float(task_run.get("progress_percent") or 0.0),
                "stage": str(task_run.get("stage") or ""),
                "tokens_consumed": int(task_run.get("tokens_consumed") or 0),
                "estimated_seconds_remaining": int(task_run.get("estimated_seconds_remaining") or 0),
                "from_store": True,
            }

        summary = deps.task_summary(task)
        return deps.json_response(
            {
                "success": True,
                "task_id": task_id,
                "status": str(task.get("status") or ""),
                "job": job,
                "task_run": task_run,
                "task_summary": summary,
                # Deprecated alias: this has never carried task text or reports.
                # Clients must re-fetch GET /api/tasks/<id> for full content.
                "task": summary,
            },
            session_id=context.session_id,
        )

    @app.post("/api/tasks/<task_id>/apply-correction-group-decisions")
    @deps.require_auth
    def api_tasks_apply_group_decisions(task_id: str):
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        group_decisions = payload.get("group_decisions", {})
        if not isinstance(group_decisions, dict):
            group_decisions = {}

        task, error = deps.get_owned_task_or_error(context, task_id)
        if error is not None:
            return error

        try:
            process_payload = deps.apply_group_decisions(
                context,
                task,
                group_decisions,
                fallback_full_corrected=str(payload.get("full_corrected_text", "") or ""),
            )
            return deps.json_response(process_payload, session_id=context.session_id)
        except Exception as exc:
            return deps.json_response(deps.error_payload("TASK_DECISION_APPLY_FAILED", str(exc)), status=500, session_id=context.session_id)

    @app.post("/api/tasks/<task_id>/save-corrected-rich-html")
    @deps.require_auth
    def api_tasks_save_corrected_rich_html(task_id: str):
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        task, error = deps.get_owned_task_or_error(context, task_id)
        if error is not None:
            return error

        corrected_rich_html = str(payload.get("corrected_rich_html", "") or "")
        max_rich_html_chars = int(deps.max_text_chars) * 4
        if len(corrected_rich_html) > max_rich_html_chars:
            return deps.json_response(
                deps.error_payload(
                    "TASK_RICH_HTML_TOO_LARGE",
                    f"Corrected rich HTML exceeds maximum size of {max_rich_html_chars} characters",
                ),
                status=413,
                session_id=context.session_id,
            )

        reports = task.get("reports") if isinstance(task.get("reports"), dict) else {}
        next_reports = dict(reports)
        next_reports["corrected_rich_html"] = corrected_rich_html

        updated = deps.store.update_task_corrected_text(
            task_id=str(task.get("id") or task_id),
            user_id=str(task.get("user_id") or context.user_id),
            corrected_text=str(task.get("corrected_text") or ""),
            reports=next_reports,
            is_admin=context.role == deps.role_admin,
        )
        if updated is None:
            return deps.json_response(
                deps.error_payload("TASK_RICH_HTML_SAVE_FAILED", "Task update failed"),
                status=500,
                session_id=context.session_id,
            )

        deps.record_audit(
            event_type="task_corrected_rich_html_saved",
            actor_user_id=context.user_id,
            entity_type="task",
            entity_id=str(task.get("id") or task_id),
            metadata={"rich_html_chars": len(corrected_rich_html)},
        )

        return deps.json_response(
            {
                "success": True,
                "task_id": str(task.get("id") or task_id),
                "saved": True,
                "corrected_rich_html_chars": len(corrected_rich_html),
            },
            session_id=context.session_id,
        )

    @app.get("/api/tasks/<task_id>/download")
    @deps.require_auth
    def api_tasks_download(task_id: str):
        context = deps.auth_context_from_request()
        file_type = str(request.query.get("type", "") or request.query.get("file_type", "") or "clean")

        try:
            deps.increment_runtime_counter(context.session_id, "export_attempts")
            payload = deps.read_task_download_payload(context, task_id=task_id, file_type=file_type)
            deps.increment_runtime_counter(context.session_id, "export_successes")
            return deps.json_response(payload, session_id=context.session_id)
        except Exception as exc:
            deps.increment_runtime_counter(context.session_id, "export_failures", "EXPORT_FILE_MISSING")
            return deps.json_response(
                deps.error_payload("EXPORT_FILE_MISSING", str(exc)),
                status=404,
                session_id=context.session_id,
            )

    @app.get("/api/tasks/<task_id>/download-file")
    @deps.require_auth
    def api_tasks_download_file(task_id: str):
        """Download generated DOCX as binary stream (avoids JSON/base64 transport)."""
        context = deps.auth_context_from_request()
        file_type = str(request.query.get("type", "") or request.query.get("file_type", "") or "clean")

        try:
            deps.increment_runtime_counter(context.session_id, "export_attempts")
            file_row, file_abs, normalized_type = deps.resolve_task_download_file(
                context=context,
                task_id=task_id,
                file_type=file_type,
            )

            download_name = str(file_row.get("download_name") or deps.build_download_filename("manuscript", normalized_type))
            mime_type = str(file_row.get("mime_type") or deps.mime_docx)

            with open(file_abs, "rb") as infile:
                body = infile.read()

            deps.record_audit(
                event_type="task_downloaded",
                actor_user_id=context.user_id,
                entity_type="task",
                entity_id=task_id,
                metadata={"file_type": normalized_type, "transport": "binary"},
            )
            deps.increment_runtime_counter(context.session_id, "export_successes")

            http_response = HTTPResponse(status=200, body=body)
            http_response.set_header("Content-Type", mime_type)
            http_response.set_header("Content-Disposition", f'attachment; filename="{download_name}"')
            http_response.set_header("Cache-Control", "no-store")
            return http_response
        except Exception as exc:
            deps.increment_runtime_counter(context.session_id, "export_failures", "EXPORT_FILE_MISSING")
            return deps.json_response(
                deps.error_payload("EXPORT_FILE_MISSING", str(exc)),
                status=404,
                session_id=context.session_id,
            )

    @app.post("/api/tasks/<task_id>/heal-bibliography")
    @deps.require_auth
    def api_tasks_heal_bibliography(task_id: str):
        """Autonomous Bibliography-Healing Engine: enrich, validate, and reformat all references in the task."""
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        options = payload.get("options", {})
        if not isinstance(options, dict):
            options = {}
        options = deps.apply_global_runtime_settings(
            options,
            deps.read_global_runtime_settings(),
            is_admin=context.role == deps.role_admin,
        )

        task, error = deps.get_owned_task_or_error(context, task_id)
        if error is not None:
            return error

        if not bool(payload.get("force", False)):
            active_run = deps.store.has_active_task_run(task_id)
            if active_run is not None:
                return deps.json_response(
                    deps.error_payload(
                        "TASK_ALREADY_PROCESSING",
                        "This task already has a run in progress. Wait for it to finish, or resend with force=true.",
                        task_run=active_run,
                    ),
                    status=409,
                    session_id=context.session_id,
                )

        deps.increment_runtime_counter(context.session_id, "heal_bibliography_requests")

        deps.store.update_task_status(
            task_id=task_id,
            status="PROCESSING",
            user_id=context.user_id,
            is_admin=context.role == deps.role_admin,
        )
        job_id = deps.processing_job_queue.new_job_id()
        task_run = deps.store.create_task_run(
            task_id=task_id,
            user_id=str(task.get("user_id") or context.user_id),
            status="PENDING",
            options=options,
            job_id=job_id,
        )
        task_run_id = str(task_run.get("id") or "")
        deps.record_audit(
            event_type="heal_bibliography_queued",
            actor_user_id=context.user_id,
            entity_type="task",
            entity_id=task_id,
            metadata={"task_run_id": task_run_id},
        )

        def run_healing_job():
            deps.store.update_task_run(
                run_id=task_run_id,
                user_id=str(task.get("user_id") or context.user_id),
                is_admin=context.role == deps.role_admin,
                status="RUNNING",
            )
            try:
                result = deps.heal_bibliography_task(context, task, options, task_run_id=task_run_id)
                deps.store.update_task_run(
                    run_id=task_run_id,
                    user_id=str(task.get("user_id") or context.user_id),
                    is_admin=context.role == deps.role_admin,
                    status="SUCCEEDED",
                    result=deps.summarize_run_result(result),
                )
                deps.increment_runtime_counter(context.session_id, "heal_bibliography_succeeded")
                deps.record_audit(
                    event_type="heal_bibliography_succeeded",
                    actor_user_id=context.user_id,
                    entity_type="task_run",
                    entity_id=task_run_id,
                    metadata={"task_id": task_id},
                )
                return result
            except Exception as exc:
                deps.store.update_task_status(
                    task_id=task_id,
                    status="FAILED",
                    user_id=context.user_id,
                    is_admin=context.role == deps.role_admin,
                )
                deps.store.update_task_run(
                    run_id=task_run_id,
                    user_id=str(task.get("user_id") or context.user_id),
                    is_admin=context.role == deps.role_admin,
                    status="FAILED",
                    error=str(exc),
                )
                deps.increment_runtime_counter(context.session_id, "heal_bibliography_failed")
                deps.record_audit(
                    event_type="heal_bibliography_failed",
                    actor_user_id=context.user_id,
                    entity_type="task_run",
                    entity_id=task_run_id,
                    metadata={"task_id": task_id, "error": str(exc)},
                )
                raise

        job = deps.processing_job_queue.submit(
            task_id=task_id,
            owner_user_id=str(task.get("user_id") or context.user_id),
            callback=run_healing_job,
            job_id=job_id,
        )

        return deps.json_response(
            {
                "success": True,
                "queued": True,
                "task_id": task_id,
                "job": job,
                "task_run": deps.store.get_task_run_for_user(
                    run_id=task_run_id,
                    user_id=context.user_id,
                    is_admin=context.role == deps.role_admin,
                ),
            },
            status=202,
            session_id=context.session_id,
        )

    @app.post("/api/tasks/<task_id>/autopilot")
    @deps.require_auth
    def api_tasks_autopilot(task_id: str):
        """Autonomous pipeline: process task and optionally heal bibliography based on policy gates."""
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        options = payload.get("options", {})
        if not isinstance(options, dict):
            options = {}
        options = deps.apply_global_runtime_settings(
            options,
            deps.read_global_runtime_settings(),
            is_admin=context.role == deps.role_admin,
        )

        task, error = deps.get_owned_task_or_error(context, task_id)
        if error is not None:
            return error

        if not bool(payload.get("force", False)):
            active_run = deps.store.has_active_task_run(task_id)
            if active_run is not None:
                return deps.json_response(
                    deps.error_payload(
                        "TASK_ALREADY_PROCESSING",
                        "This task already has a run in progress. Wait for it to finish, or resend with force=true.",
                        task_run=active_run,
                    ),
                    status=409,
                    session_id=context.session_id,
                )

        deps.increment_runtime_counter(context.session_id, "autopilot_requests")
        deps.store.update_task_status(
            task_id=task_id,
            status="PROCESSING",
            user_id=context.user_id,
            is_admin=context.role == deps.role_admin,
        )
        job_id = deps.processing_job_queue.new_job_id()
        task_run = deps.store.create_task_run(
            task_id=task_id,
            user_id=str(task.get("user_id") or context.user_id),
            status="PENDING",
            options=options,
            job_id=job_id,
        )
        task_run_id = str(task_run.get("id") or "")
        deps.record_audit(
            event_type="task_autopilot_queued",
            actor_user_id=context.user_id,
            entity_type="task",
            entity_id=task_id,
            metadata={"task_run_id": task_run_id},
        )

        def run_autopilot_job():
            deps.store.update_task_run(
                run_id=task_run_id,
                user_id=str(task.get("user_id") or context.user_id),
                is_admin=context.role == deps.role_admin,
                status="RUNNING",
            )
            max_attempts = 2
            attempt = 0
            last_error = None
            while attempt < max_attempts:
                attempt += 1
                try:
                    result = deps.autopilot_task(context, task, options, task_run_id=task_run_id)
                    deps.store.update_task_run(
                        run_id=task_run_id,
                        user_id=str(task.get("user_id") or context.user_id),
                        is_admin=context.role == deps.role_admin,
                        status="SUCCEEDED",
                        result=deps.summarize_run_result(result),
                    )
                    deps.increment_runtime_counter(context.session_id, "autopilot_succeeded")
                    deps.record_audit(
                        event_type="task_autopilot_succeeded",
                        actor_user_id=context.user_id,
                        entity_type="task_run",
                        entity_id=task_run_id,
                        metadata={"task_id": task_id, "attempt": attempt, "retried": attempt > 1},
                    )
                    return result
                except Exception as exc:
                    last_error = exc
                    if attempt < max_attempts and _is_transient_autopilot_error(exc):
                        deps.increment_runtime_counter(context.session_id, "autopilot_retries")
                        deps.record_audit(
                            event_type="task_autopilot_retrying",
                            actor_user_id=context.user_id,
                            entity_type="task_run",
                            entity_id=task_run_id,
                            metadata={"task_id": task_id, "attempt": attempt, "error": str(exc)},
                        )
                        time.sleep(1)
                        continue
                    break

            deps.store.update_task_status(
                task_id=task_id,
                status="FAILED",
                user_id=context.user_id,
                is_admin=context.role == deps.role_admin,
            )
            deps.store.update_task_run(
                run_id=task_run_id,
                user_id=str(task.get("user_id") or context.user_id),
                is_admin=context.role == deps.role_admin,
                status="FAILED",
                error=str(last_error),
            )
            deps.increment_runtime_counter(context.session_id, "autopilot_failed")
            deps.record_audit(
                event_type="task_autopilot_failed",
                actor_user_id=context.user_id,
                entity_type="task_run",
                entity_id=task_run_id,
                metadata={"task_id": task_id, "error": str(last_error), "attempts": attempt},
            )
            raise last_error

        job = deps.processing_job_queue.submit(
            task_id=task_id,
            owner_user_id=str(task.get("user_id") or context.user_id),
            callback=run_autopilot_job,
            job_id=job_id,
        )

        return deps.json_response(
            {
                "success": True,
                "queued": True,
                "task_id": task_id,
                "job": job,
                "task_run": deps.store.get_task_run_for_user(
                    run_id=task_run_id,
                    user_id=context.user_id,
                    is_admin=context.role == deps.role_admin,
                ),
            },
            status=202,
            session_id=context.session_id,
        )
