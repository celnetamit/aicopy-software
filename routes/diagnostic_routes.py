"""Health, version, runtime telemetry, runtime settings, and client error routes."""


def register_diagnostic_routes(app, deps):
    @app.post("/api/client-errors")
    @deps.require_auth
    def api_report_client_error():
        """Accept an uncaught browser error so frontend faults stop being invisible.

        Rate limited per user: a page stuck in a render loop must not be able to
        flood the error log.
        """
        context = deps.auth_context_from_request()
        if not deps.client_error_reporting_enabled:
            return deps.json_response({"success": True, "recorded": False, "reason": "disabled"},
                                      session_id=context.session_id)

        allowed, retry_after = deps.check_rate_limit(
            "client_errors",
            context.user_id or deps.get_client_ip(),
            deps.client_error_rate_limit_count,
            deps.client_error_rate_limit_window_seconds,
        )
        if not allowed:
            return deps.json_response(
                deps.error_payload(
                    "RATE_LIMITED",
                    f"Too many client error reports. Retry after {retry_after} seconds.",
                    retry_after=retry_after,
                ),
                status=429,
                session_id=context.session_id,
            )

        payload = deps.read_json_payload()
        message = str(payload.get("message", "") or "").strip()[:1000]
        if not message:
            return deps.json_response(
                deps.error_payload("CLIENT_ERROR_MESSAGE_REQUIRED", "A message is required"),
                status=400,
                session_id=context.session_id,
            )

        kind = str(payload.get("kind", "error") or "error").strip().lower()
        code = "CLIENT_UNHANDLED_REJECTION" if kind == "unhandledrejection" else "CLIENT_SCRIPT_ERROR"

        deps.record_error(
            code=code,
            message=message,
            source="client",
            level="ERROR",
            include_traceback=False,
            # The path is the page the fault happened on, not the beacon call.
            request_method="CLIENT",
            request_path=str(payload.get("page", "") or "")[:512],
            actor_user_id=context.user_id,
            task_id=str(payload.get("task_id", "") or "")[:128],
            context={
                "stack": str(payload.get("stack", "") or "")[:4000],
                "script": str(payload.get("source", "") or "")[:512],
                "line": payload.get("line"),
                "column": payload.get("column"),
                "user_agent": deps.get_user_agent()[:300],
                "app_version": deps.app_version,
            },
        )
        return deps.json_response({"success": True, "recorded": True}, session_id=context.session_id)

    @app.get("/api/health")
    def api_health():
        return deps.json_response(
            {
                "success": True,
                "status": "ok",
                "storage_backend": deps.store.backend,
                "auth_required": True,
                "version": deps.app_version,
            }
        )

    @app.get("/api/version")
    def api_version():
        return deps.json_response(
            {
                "success": True,
                "version": deps.app_version,
                "asset_version": deps.web_asset_version,
            }
        )

    @app.get("/api/runtime-telemetry")
    @deps.require_auth
    def get_runtime_telemetry():
        context = deps.auth_context_from_request()
        return deps.json_response({"success": True, "telemetry": deps.read_runtime_telemetry(context.session_id)})

    @app.post("/api/runtime-telemetry/reset")
    @deps.require_auth
    def reset_runtime_telemetry():
        context = deps.auth_context_from_request()
        deps.reset_runtime_telemetry(context.session_id)
        return deps.json_response({"success": True})

    @app.post("/api/reset-session")
    @deps.require_auth
    def reset_session():
        context = deps.auth_context_from_request()
        deps.reset_runtime_telemetry(context.session_id)
        return deps.json_response({"success": True})

    @app.get("/api/settings/runtime")
    @deps.require_auth
    def api_runtime_settings():
        context = deps.auth_context_from_request()
        settings = deps.read_global_runtime_settings()
        payload_settings = (
            settings
            if context.role == deps.role_admin
            else deps.global_runtime_settings_for_user_payload(settings)
        )
        return deps.json_response({"success": True, "settings": payload_settings}, session_id=context.session_id)
