"""Assistant Q&A and action routes."""


def register_assistant_routes(app, deps):
    @app.post("/api/assistant")
    @deps.require_auth
    def api_assistant():
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        mode = str(payload.get("mode", "qna") or "qna").strip().lower()
        message = str(payload.get("message", "") or "").strip()
        task_id = str(payload.get("task_id", "") or "").strip()
        include_admin_activity = bool(payload.get("include_admin_activity", False))

        task = None
        if task_id:
            task, error = deps.get_owned_task_or_error(context, task_id)
            if error is not None:
                return error

        if mode == "qna":
            answer = deps.assistant_qna_response(context, message, task, include_admin_activity=include_admin_activity)
            deps.record_audit(
                event_type="assistant_qna",
                actor_user_id=context.user_id,
                entity_type="task" if task_id else "",
                entity_id=task_id,
                metadata={
                    "has_message": bool(message),
                    "has_task": bool(task_id),
                    "include_admin_activity": bool(include_admin_activity and context.role == deps.role_admin),
                },
            )
            return deps.json_response(
                {
                    "success": True,
                    "mode": "qna",
                    "assistant": answer,
                },
                session_id=context.session_id,
            )

        if mode == "action":
            confirmed = bool(payload.get("confirm", False))
            if not confirmed:
                return deps.json_response(
                    deps.error_payload(
                        "ASSISTANT_CONFIRMATION_REQUIRED",
                        "Assistant action requires explicit confirmation. Send confirm=true to continue.",
                    ),
                    status=400,
                    session_id=context.session_id,
                )
            action = str(payload.get("action", "") or "").strip().lower()
            if action not in {"reprocess_task", "apply_correction_group_decisions"}:
                return deps.json_response(
                    deps.error_payload("ASSISTANT_ACTION_UNSUPPORTED", "Unsupported assistant action"),
                    status=400,
                    session_id=context.session_id,
                )
            if not task_id:
                return deps.json_response(
                    deps.error_payload("TASK_REQUIRED", "No task selected"),
                    status=400,
                    session_id=context.session_id,
                )
            if task is None:
                task, error = deps.get_owned_task_or_error(context, task_id)
                if error is not None:
                    return error

            try:
                if action == "reprocess_task":
                    raw_options = payload.get("options", {})
                    options = raw_options
                    if not isinstance(options, dict):
                        options = {}
                    options = deps.apply_global_runtime_settings(
            options,
            deps.read_global_runtime_settings(),
            is_admin=context.role == deps.role_admin,
        )
                    # Assistant action must honor caller-provided AI overrides for safe execution.
                    if isinstance(raw_options, dict):
                        ai_in = raw_options.get("ai", {})
                        if isinstance(ai_in, dict):
                            ai_out = options.get("ai", {}) if isinstance(options.get("ai"), dict) else {}
                            if "enabled" in ai_in:
                                ai_out["enabled"] = bool(ai_in.get("enabled"))
                            if "provider" in ai_in and str(ai_in.get("provider") or "").strip():
                                ai_out["provider"] = str(ai_in.get("provider") or "").strip()
                            if "model" in ai_in and str(ai_in.get("model") or "").strip():
                                ai_out["model"] = str(ai_in.get("model") or "").strip()
                            options["ai"] = ai_out
                    process_payload = deps.process_task(context, task, options)
                else:
                    group_decisions = payload.get("group_decisions", {})
                    if not isinstance(group_decisions, dict):
                        group_decisions = {}
                    process_payload = deps.apply_group_decisions(
                        context,
                        task,
                        group_decisions,
                        fallback_full_corrected=str(payload.get("full_corrected_text", "") or ""),
                    )
            except Exception as exc:
                deps.record_audit(
                    event_type="assistant_action_failed",
                    actor_user_id=context.user_id,
                    entity_type="task",
                    entity_id=task_id,
                    metadata={"action": action, "error": str(exc)},
                )
                error_code = "TASK_PROCESS_FAILED" if action == "reprocess_task" else "TASK_DECISION_APPLY_FAILED"
                return deps.json_response(deps.error_payload(error_code, str(exc)), status=500, session_id=context.session_id)
            deps.record_audit(
                event_type="assistant_action_executed",
                actor_user_id=context.user_id,
                entity_type="task",
                entity_id=task_id,
                metadata={"action": action},
            )
            return deps.json_response(
                {
                    "success": True,
                    "mode": "action",
                    "action": action,
                    "task_id": task_id,
                    "result": process_payload,
                },
                session_id=context.session_id,
            )

        return deps.json_response(
            deps.error_payload("ASSISTANT_MODE_UNSUPPORTED", "Unsupported assistant mode"),
            status=400,
            session_id=context.session_id,
        )
