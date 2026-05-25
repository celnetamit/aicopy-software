"""Compatibility routes for older Eel/SPA bridge calls."""

import base64
import os
import tempfile

from bottle import request


def register_legacy_routes(app, deps):
    @app.post("/api/load-text")
    @deps.require_auth
    def load_text_content_legacy():
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

    @app.post("/api/load-docx")
    @deps.require_auth
    def load_docx_content_legacy():
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

    @app.post("/api/process-document")
    @deps.require_auth
    def process_document_legacy():
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        options = payload.get("options", {})
        if not isinstance(options, dict):
            options = {}
        options = deps.apply_global_runtime_settings(options, deps.read_global_runtime_settings())

        task_id = str(payload.get("task_id", "") or "").strip()
        source_text = str(payload.get("source_text", "") or "")
        source_file_name = str(payload.get("source_file_name", "manuscript.txt") or "manuscript.txt")
        source_type = str(payload.get("source_type", "text") or "text").strip().lower()
        source_docx_base64 = str(payload.get("source_docx_base64", "") or "")

        try:
            if not task_id:
                if source_type == "docx" and source_docx_base64.strip():
                    try:
                        source_docx_bytes = base64.b64decode(source_docx_base64, validate=True)
                    except Exception:
                        return deps.json_response(
                            deps.error_payload("TASK_UPLOAD_INVALID_BASE64", "Invalid base64 document payload"),
                            status=400,
                        )
                    if len(source_docx_bytes) > int(deps.max_upload_bytes):
                        return deps.json_response(
                            deps.error_payload("TASK_UPLOAD_TOO_LARGE", f"DOCX exceeds maximum size of {deps.max_upload_bytes} bytes"),
                            status=413,
                        )
                    uploaded = deps.upload_docx_to_task(
                        context,
                        file_name=source_file_name if source_file_name.lower().endswith(".docx") else "manuscript.docx",
                        byte_data=source_docx_bytes,
                    )
                    task_id = str(uploaded.get("task_id") or "")
                elif source_text.strip():
                    if len(source_text) > int(deps.max_text_chars):
                        return deps.json_response(
                            deps.error_payload("TASK_UPLOAD_TOO_LARGE", f"Text exceeds maximum size of {deps.max_text_chars} characters"),
                            status=413,
                        )
                    uploaded = deps.upload_text_to_task(
                        context,
                        file_name=source_file_name,
                        text=source_text,
                        source_type="text",
                    )
                    task_id = str(uploaded.get("task_id") or "")

            if not task_id:
                return deps.json_response(deps.error_payload("TASK_REQUIRED", "No task selected"), status=400)

            task, error = deps.get_owned_task_or_error(context, task_id)
            if error is not None:
                return error

            process_payload = deps.process_task(context, task, options)
            return deps.json_response(process_payload, session_id=context.session_id)
        except Exception as exc:
            return deps.json_response(deps.error_payload("TASK_PROCESS_FAILED", str(exc)), status=500, session_id=context.session_id)

    @app.post("/api/apply-correction-group-decisions")
    @deps.require_auth
    def apply_correction_group_decisions_legacy():
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        task_id = str(payload.get("task_id", "") or "").strip()
        group_decisions = payload.get("group_decisions", {})
        if not isinstance(group_decisions, dict):
            group_decisions = {}

        if not task_id:
            return deps.json_response(deps.error_payload("TASK_REQUIRED", "No task selected"), status=400)

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

    @app.get("/api/redline-preview")
    @deps.require_auth
    def get_redline_preview_legacy():
        context = deps.auth_context_from_request()
        task_id = str(request.query.get("task_id", "") or "").strip()
        if not task_id:
            return deps.json_response(deps.error_payload("TASK_REQUIRED", "No task selected"), status=400)

        task, error = deps.get_owned_task_or_error(context, task_id)
        if error is not None:
            return error

        original = str(task.get("original_text") or "")
        corrected = str(task.get("corrected_text") or "")
        if not original.strip():
            return deps.json_response(deps.error_payload("TASK_EMPTY", "No document loaded"), status=400)
        if not corrected.strip():
            return deps.json_response(deps.error_payload("TASK_NOT_PROCESSED", "No corrected document available"), status=400)

        processor = deps.document_processor()
        redline_html = processor.build_redline_html(original, corrected)
        return deps.json_response({"success": True, "task_id": task_id, "redline_html": redline_html}, session_id=context.session_id)

    @app.get("/api/ollama-models")
    @deps.require_auth
    def get_ollama_models_legacy():
        context = deps.auth_context_from_request()
        try:
            processor = deps.document_processor()
            host = str(request.query.get("ollama_host", "") or processor.ollama_host).strip() or processor.ollama_host
            models = processor._get_ollama_models(host)
            default_model = processor._resolve_ollama_model(host, processor.model)
            return deps.json_response(
                {
                    "success": True,
                    "models": models,
                    "default_model": default_model,
                },
                session_id=context.session_id,
            )
        except Exception as exc:
            return deps.json_response({"success": False, "error": str(exc), "models": []}, status=500, session_id=context.session_id)

    @app.post("/api/export-file")
    @deps.require_auth
    def export_file_legacy():
        context = deps.auth_context_from_request()
        payload = deps.read_json_payload()
        task_id = str(payload.get("task_id", "") or "").strip()
        file_type = str(payload.get("file_type", "") or "clean")

        deps.increment_runtime_counter(context.session_id, "export_attempts")

        try:
            if task_id:
                response_payload = deps.read_task_download_payload(context, task_id=task_id, file_type=file_type)
                deps.increment_runtime_counter(context.session_id, "export_successes")
                return deps.json_response(response_payload, session_id=context.session_id)

            original_text = str(payload.get("original_text", "") or "")
            corrected_text = str(payload.get("corrected_text", "") or "")
            _corrected_rich_html = str(payload.get("corrected_rich_html", "") or "")
            file_name = str(payload.get("file_name", "manuscript.docx") or "manuscript.docx")
            source_type = str(payload.get("source_type", "text") or "text").strip().lower()
            source_docx_base64 = str(payload.get("source_docx_base64", "") or "").strip()
            normalized_type = "clean" if file_type == "clean" else "highlighted"

            if not corrected_text.strip():
                deps.increment_runtime_counter(context.session_id, "export_failures", "EXPORT_NO_CORRECTED_DOC")
                return deps.json_response(
                    deps.error_payload("EXPORT_NO_CORRECTED_DOC", "No corrected document available"),
                    status=400,
                    session_id=context.session_id,
                )

            processor = deps.document_processor()
            temp_path = None
            source_docx_temp_path = None
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as handle:
                temp_path = handle.name

            try:
                if source_type == "docx" and source_docx_base64:
                    try:
                        source_docx_bytes = base64.b64decode(source_docx_base64.encode("ascii"), validate=True)
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as source_handle:
                            source_handle.write(source_docx_bytes)
                            source_docx_temp_path = source_handle.name
                    except Exception:
                        source_docx_temp_path = None

                if normalized_type == "clean":
                    processor.generate_clean_docx(corrected_text, temp_path, source_docx_path=source_docx_temp_path or "")
                else:
                    processor.generate_highlighted_docx(
                        original_text,
                        corrected_text,
                        temp_path,
                        source_docx_path=source_docx_temp_path or "",
                    )

                with open(temp_path, "rb") as infile:
                    encoded = base64.b64encode(infile.read()).decode("ascii")

                deps.increment_runtime_counter(context.session_id, "export_successes")
                return deps.json_response(
                    {
                        "success": True,
                        "file_name": deps.build_download_filename(file_name, normalized_type),
                        "mime_type": deps.mime_docx,
                        "base64_data": encoded,
                    },
                    session_id=context.session_id,
                )
            finally:
                if source_docx_temp_path and os.path.exists(source_docx_temp_path):
                    os.unlink(source_docx_temp_path)
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
        except Exception as exc:
            deps.increment_runtime_counter(context.session_id, "export_failures", "EXPORT_EXCEPTION")
            return deps.json_response(deps.error_payload("EXPORT_EXCEPTION", str(exc)), status=500, session_id=context.session_id)

    @app.post("/api/save-file")
    @deps.require_auth
    def save_file_legacy():
        context = deps.auth_context_from_request()
        deps.increment_runtime_counter(context.session_id, "save_attempts")
        deps.increment_runtime_counter(context.session_id, "save_failures", "SAVE_BROWSER_MODE_UNSUPPORTED")
        return deps.json_response(
            deps.error_payload(
                "SAVE_BROWSER_MODE_UNSUPPORTED",
                "Browser mode uses downloads instead of server-side save dialogs.",
            ),
            status=400,
            session_id=context.session_id,
        )
