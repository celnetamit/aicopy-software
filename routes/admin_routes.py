"""Admin user, audit, settings, diagnostics, and provider validation routes."""

from bottle import request


def register_admin_routes(app, deps):
    def _as_list(raw):
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        if isinstance(raw, str):
            return [chunk.strip() for chunk in raw.replace("\n", ",").split(",") if chunk.strip()]
        return []

    @app.get("/api/admin/users")
    @deps.require_admin
    def api_admin_users():
        context = deps.auth_context_from_request()
        try:
            limit = int(str(request.query.get("limit", "200") or "200"))
        except Exception:
            limit = 200

        users = deps.store.list_users(limit=limit)
        payload = []
        for user in users:
            payload.append(
                {
                    "id": str(user.get("id") or ""),
                    "email": str(user.get("email") or ""),
                    "display_name": str(user.get("display_name") or ""),
                    "domain": str(user.get("domain") or ""),
                    "role": str(user.get("role") or "USER"),
                    "status": str(user.get("status") or deps.status_active),
                    "last_login_at": int(user.get("last_login_at") or 0),
                    "created_at": int(user.get("created_at") or 0),
                    "updated_at": int(user.get("updated_at") or 0),
                }
            )

        deps.record_audit(event_type="admin_users_viewed", actor_user_id=context.user_id)
        return deps.json_response({"success": True, "users": payload}, session_id=context.session_id)

    @app.post("/api/admin/users/<user_id>/status")
    @deps.require_admin
    def api_admin_set_user_status(user_id: str):
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        status = str(payload.get("status", deps.status_active) or deps.status_active).upper().strip()
        if status not in (deps.status_active, deps.status_inactive):
            status = deps.status_inactive

        if user_id == context.user_id and status == deps.status_inactive:
            return deps.json_response(deps.error_payload("ADMIN_SELF_DEACTIVATE_BLOCKED", "Admin cannot deactivate self"), status=400)

        user = deps.store.set_user_status(user_id=user_id, status=status)
        if user is None:
            return deps.json_response(deps.error_payload("USER_NOT_FOUND", "User not found"), status=404)

        deps.record_audit(
            event_type="admin_user_status_changed",
            actor_user_id=context.user_id,
            target_user_id=user_id,
            entity_type="user",
            entity_id=user_id,
            metadata={"status": status},
        )

        return deps.json_response(
            {
                "success": True,
                "user": {
                    "id": str(user.get("id") or ""),
                    "email": str(user.get("email") or ""),
                    "display_name": str(user.get("display_name") or ""),
                    "role": str(user.get("role") or "USER"),
                    "status": str(user.get("status") or deps.status_active),
                },
            },
            session_id=context.session_id,
        )

    @app.get("/api/admin/audit-events")
    @deps.require_admin
    def api_admin_audit_events():
        context = deps.auth_context_from_request()

        try:
            limit = int(str(request.query.get("limit", "200") or "200"))
        except Exception:
            limit = 200

        actor_user_id = str(request.query.get("actor_user_id", "") or "").strip()
        event_type = str(request.query.get("event_type", "") or "").strip()

        try:
            date_from = int(str(request.query.get("date_from", "0") or "0"))
        except Exception:
            date_from = 0

        try:
            date_to = int(str(request.query.get("date_to", "0") or "0"))
        except Exception:
            date_to = 0

        events = deps.store.list_audit_events(
            limit=limit,
            actor_user_id=actor_user_id,
            event_type=event_type,
            date_from=date_from,
            date_to=date_to,
        )

        deps.record_audit(event_type="admin_audit_viewed", actor_user_id=context.user_id)
        return deps.json_response({"success": True, "events": events}, session_id=context.session_id)

    @app.get("/api/admin/global-settings")
    @deps.require_admin
    def api_admin_get_global_settings():
        context = deps.auth_context_from_request()
        settings = deps.read_global_runtime_settings()
        deps.record_audit(event_type="admin_global_settings_viewed", actor_user_id=context.user_id)
        return deps.json_response({"success": True, "settings": settings}, session_id=context.session_id)

    @app.post("/api/admin/global-settings")
    @deps.require_admin
    def api_admin_update_global_settings():
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        incoming = payload.get("settings", payload)
        if not isinstance(incoming, dict):
            incoming = {}
        normalized = deps.normalize_global_runtime_settings(incoming)
        deps.store.upsert_app_setting(
            key=deps.app_setting_key_global_runtime,
            value=normalized,
            updated_by_user_id=context.user_id,
        )
        deps.record_audit(
            event_type="admin_global_settings_updated",
            actor_user_id=context.user_id,
            metadata={
                "ai_provider": normalized.get("ai", {}).get("provider"),
                "ai_enabled": normalized.get("ai", {}).get("enabled"),
                "domain_profile": normalized.get("editing", {}).get("domain_profile"),
            },
        )
        return deps.json_response({"success": True, "settings": normalized}, session_id=context.session_id)

    @app.get("/api/admin/reference-validation-diagnostics")
    @deps.require_admin
    def api_admin_reference_validation_diagnostics():
        context = deps.auth_context_from_request()
        diagnostics = deps.build_reference_validation_diagnostics_payload()
        deps.record_audit(
            event_type="admin_reference_validation_diagnostics_viewed",
            actor_user_id=context.user_id,
            metadata={
                "serper_configured": bool((diagnostics.get("serper", {}) or {}).get("configured")),
                "serper_effective_enabled": bool((diagnostics.get("serper", {}) or {}).get("effective_enabled")),
            },
        )
        return deps.json_response({"success": True, "diagnostics": diagnostics}, session_id=context.session_id)

    @app.post("/api/admin/reference-validation-diagnostics/reset")
    @deps.require_admin
    def api_admin_reference_validation_diagnostics_reset():
        context = deps.auth_context_from_request()
        result = deps.reset_reference_validation_diagnostics_payload()
        diagnostics = result.get("diagnostics", {}) if isinstance(result, dict) else {}
        removed_cache_entries = int((result or {}).get("removed_cache_entries", 0))
        deps.record_audit(
            event_type="admin_reference_validation_diagnostics_reset",
            actor_user_id=context.user_id,
            metadata={
                "removed_cache_entries": removed_cache_entries,
                "serper_configured": bool((diagnostics.get("serper", {}) or {}).get("configured")),
                "serper_effective_enabled": bool((diagnostics.get("serper", {}) or {}).get("effective_enabled")),
            },
        )
        return deps.json_response(
            {
                "success": True,
                "removed_cache_entries": removed_cache_entries,
                "diagnostics": diagnostics,
            },
            session_id=context.session_id,
        )

    @app.post("/api/admin/validate-ai-provider")
    @deps.require_admin
    def api_admin_validate_ai_provider():
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        provider = str(payload.get("provider", "") or "").strip().lower()
        model = str(payload.get("model", "") or "").strip()
        api_key = str(payload.get("api_key", "") or "").strip()
        ollama_host = str(payload.get("ollama_host", "") or "").strip()

        saved_settings = deps.read_global_runtime_settings()
        saved_ai = saved_settings.get("ai", {}) if isinstance(saved_settings.get("ai", {}), dict) else {}
        saved_provider = str(saved_ai.get("provider", "") or "").strip().lower()
        if not model and saved_provider == provider:
            model = str(saved_ai.get("model", "") or "").strip()
        if provider == "ollama" and not ollama_host:
            ollama_host = str(saved_ai.get("ollama_host", "") or "").strip()
        if provider == "gemini" and not api_key:
            api_key = str(saved_ai.get("gemini_api_key", "") or "").strip()
        if provider == "openrouter" and not api_key:
            api_key = str(saved_ai.get("openrouter_api_key", "") or "").strip()
        if provider == "agent_router" and not api_key:
            api_key = str(saved_ai.get("agent_router_api_key", "") or "").strip()

        ok, message = deps.validate_ai_provider_runtime(provider, model, api_key, ollama_host)
        deps.record_audit(
            event_type="admin_ai_provider_validated",
            actor_user_id=context.user_id,
            metadata={
                "provider": provider,
                "model": model,
                "ok": bool(ok),
            },
        )
        return deps.json_response(
            {
                "success": True,
                "provider": provider,
                "model": model,
                "valid": bool(ok),
                "message": str(message or ""),
            },
            session_id=context.session_id,
        )

    @app.get("/api/admin/journal-profiles")
    @deps.require_admin
    def api_admin_journal_profiles():
        context = deps.auth_context_from_request()
        task_id = str(request.query.get("task_id", "") or "").strip()
        
        from chicago_editor import ChicagoEditor
        profiles = ChicagoEditor.JOURNAL_PROFILES
        
        task = None
        if task_id:
            task = deps.store.get_task_for_user(task_id=task_id, user_id=context.user_id, is_admin=True)
            
        payload = []
        for pid, pdata in profiles.items():
            item = {
                "id": pid,
                "label": pdata.get("label", pid),
                "initials_with_periods": bool(pdata.get("initials_with_periods", False)),
                "title_case": str(pdata.get("title_case", "sentence")),
                "journal_abbrev": str(pdata.get("journal_abbrev", "nlm")),
                "match_score": 100,
                "issue_total": 0,
                "reference_count": 0,
                "validation_messages": []
            }
            if task:
                text_to_analyze = str(task.get("original_text") or "")
                editor = ChicagoEditor()
                # Run the report with a mock options for this specific profile
                report = editor.build_reference_profile_report(text_to_analyze, {"journal_profile": pid})
                ref_count = report.get("reference_count", 0)
                issue_counts = report.get("issue_counts", {})
                issue_total = sum(issue_counts.values())
                
                # Compute Guidelines Match Score
                if ref_count > 0:
                    # Deduction formula: start at 100, deduct points per issue type, down to a minimum of 25
                    deduction = sum(min(20, count * 5) for count in issue_counts.values())
                    match_score = max(25, 100 - deduction)
                else:
                    match_score = 100
                    
                item["match_score"] = match_score
                item["issue_total"] = issue_total
                item["reference_count"] = ref_count
                item["validation_messages"] = report.get("validation_messages", [])
                
            payload.append(item)
            
        deps.record_audit(event_type="admin_journal_profiles_viewed", actor_user_id=context.user_id)
        return deps.json_response({"success": True, "profiles": payload}, session_id=context.session_id)

    @app.get("/api/admin/journals")
    @deps.require_admin
    def api_admin_list_journals():
        context = deps.auth_context_from_request()
        include_inactive = str(request.query.get("include_inactive", "true") or "true").strip().lower() not in {"false", "0", "no"}
        journals = deps.store.list_journals(include_inactive=include_inactive, limit=1000)
        deps.record_audit(event_type="admin_journals_viewed", actor_user_id=context.user_id)
        return deps.json_response({"success": True, "journals": journals}, session_id=context.session_id)

    @app.post("/api/admin/journals")
    @deps.require_admin
    def api_admin_create_journal():
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        name = str(payload.get("name") or "").strip()
        if not name:
            return deps.json_response(deps.error_payload("JOURNAL_NAME_REQUIRED", "Journal name is required"), status=400, session_id=context.session_id)
        created = deps.store.create_journal(
            {
                "name": name,
                "scope": str(payload.get("scope") or "").strip(),
                "keywords": _as_list(payload.get("keywords")),
                "subject_areas": _as_list(payload.get("subject_areas")),
                "article_types": _as_list(payload.get("article_types")),
                "issn_print": str(payload.get("issn_print") or "").strip(),
                "issn_online": str(payload.get("issn_online") or "").strip(),
                "publisher": str(payload.get("publisher") or "").strip(),
                "quartile": str(payload.get("quartile") or "").strip().upper(),
                "open_access": bool(payload.get("open_access", False)),
                "apc_usd": payload.get("apc_usd", 0),
                "submission_url": str(payload.get("submission_url") or "").strip(),
                "is_active": bool(payload.get("is_active", True)),
            }
        )
        deps.record_audit(
            event_type="admin_journal_created",
            actor_user_id=context.user_id,
            entity_type="journal",
            entity_id=str(created.get("id") or ""),
            metadata={"name": name},
        )
        return deps.json_response({"success": True, "journal": created}, session_id=context.session_id)

    @app.put("/api/admin/journals/<journal_id>")
    @deps.require_admin
    def api_admin_update_journal(journal_id: str):
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        updated = deps.store.update_journal(
            journal_id,
            {
                "name": str(payload.get("name") or "").strip() if "name" in payload else None,
                "scope": str(payload.get("scope") or "").strip() if "scope" in payload else None,
                "keywords": _as_list(payload.get("keywords")) if "keywords" in payload else None,
                "subject_areas": _as_list(payload.get("subject_areas")) if "subject_areas" in payload else None,
                "article_types": _as_list(payload.get("article_types")) if "article_types" in payload else None,
                "issn_print": str(payload.get("issn_print") or "").strip() if "issn_print" in payload else None,
                "issn_online": str(payload.get("issn_online") or "").strip() if "issn_online" in payload else None,
                "publisher": str(payload.get("publisher") or "").strip() if "publisher" in payload else None,
                "quartile": str(payload.get("quartile") or "").strip().upper() if "quartile" in payload else None,
                "open_access": bool(payload.get("open_access")) if "open_access" in payload else None,
                "apc_usd": payload.get("apc_usd") if "apc_usd" in payload else None,
                "submission_url": str(payload.get("submission_url") or "").strip() if "submission_url" in payload else None,
                "is_active": bool(payload.get("is_active")) if "is_active" in payload else None,
            },
        )
        if updated is None:
            return deps.json_response(deps.error_payload("JOURNAL_NOT_FOUND", "Journal not found"), status=404, session_id=context.session_id)
        deps.record_audit(
            event_type="admin_journal_updated",
            actor_user_id=context.user_id,
            entity_type="journal",
            entity_id=str(journal_id),
        )
        return deps.json_response({"success": True, "journal": updated}, session_id=context.session_id)

    @app.delete("/api/admin/journals/<journal_id>")
    @deps.require_admin
    def api_admin_delete_journal(journal_id: str):
        context = deps.auth_context_from_request()
        updated = deps.store.deactivate_journal(journal_id)
        if updated is None:
            return deps.json_response(deps.error_payload("JOURNAL_NOT_FOUND", "Journal not found"), status=404, session_id=context.session_id)
        deps.record_audit(
            event_type="admin_journal_deactivated",
            actor_user_id=context.user_id,
            entity_type="journal",
            entity_id=str(journal_id),
        )
        return deps.json_response({"success": True, "journal": updated}, session_id=context.session_id)
