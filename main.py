#!/usr/bin/env python3
"""Manuscript Editor backend for Eel web UI."""

import base64
import os
import sys
import tempfile
import traceback

import eel

from document_processor import DocumentProcessor
import manuscript_service


processor = DocumentProcessor()
current_file = None
current_source_docx_path = ""
original_text = ""
corrected_text = ""
full_corrected_text = ""
runtime_telemetry = manuscript_service.get_default_runtime_telemetry()

def _runtime_base_dir() -> str:
    """Return base directory for source and PyInstaller-frozen runtime."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


web_folder = os.path.join(_runtime_base_dir(), "web")
required_web_assets = ("index.html", "style.css", "app.js")


def _record_error(code: str):
    """Increase per-error-code telemetry counter."""
    bucket = runtime_telemetry.setdefault("errors_by_code", {})
    bucket[code] = int(bucket.get(code, 0)) + 1


def _error_payload(code: str, message: str, **extra):
    """Standardized error payload with code for UI handling."""
    payload = {"success": False, "error": message, "error_code": code}
    payload.update(extra)
    _record_error(code)
    return payload


def setup_web_folder():
    """Validate that static web assets exist."""
    os.makedirs(web_folder, exist_ok=True)
    missing = [name for name in required_web_assets if not os.path.isfile(os.path.join(web_folder, name))]
    if missing:
        raise FileNotFoundError(f"Missing web assets in {web_folder}: {', '.join(missing)}")


@eel.expose
def get_runtime_telemetry():
    """Return current runtime telemetry counters."""
    return {"success": True, "telemetry": runtime_telemetry}


@eel.expose
def reset_runtime_telemetry():
    """Reset runtime telemetry counters."""
    runtime_telemetry["export_attempts"] = 0
    runtime_telemetry["export_successes"] = 0
    runtime_telemetry["export_failures"] = 0
    runtime_telemetry["save_attempts"] = 0
    runtime_telemetry["save_successes"] = 0
    runtime_telemetry["save_failures"] = 0
    runtime_telemetry["save_fallback_used"] = 0
    runtime_telemetry["errors_by_code"] = {}
    return {"success": True}


@eel.expose
def reset_session():
    """Clear the currently loaded document and derived outputs."""
    global current_file, current_source_docx_path, original_text, corrected_text, full_corrected_text
    current_file = None
    current_source_docx_path = ""
    original_text = ""
    corrected_text = ""
    full_corrected_text = ""
    return {"success": True}


def _load_text_to_state(file_name: str, text: str, source_docx_path: str = ""):
    """Store loaded text in global app state and return payload."""
    global original_text, corrected_text, full_corrected_text, current_file, current_source_docx_path
    current_file = file_name
    current_source_docx_path = source_docx_path if str(source_docx_path or "").lower().endswith(".docx") else ""
    original_text = text
    corrected_text = ""
    full_corrected_text = ""
    return {
        "success": True,
        "text": original_text,
        "word_count": len(original_text.split()),
    }


def _build_process_payload(original: str, corrected: str, options: dict = None):
    """Build standard process response payload."""
    source_type = "docx" if current_source_docx_path else "text"
    return manuscript_service.build_process_payload(
        processor=processor,
        task_id="",
        original_text=original,
        corrected_text=corrected,
        full_corrected_text=full_corrected_text,
        source_type=source_type,
        source_docx_path=current_source_docx_path,
        options=options,
    )


def _build_download_filename(file_type: str) -> str:
    """Build a friendly output filename based on loaded manuscript name."""
    base_name = os.path.splitext(os.path.basename(current_file or "manuscript"))[0].strip() or "manuscript"
    prefix = "clean" if file_type == "clean" else "highlighted"
    return f"{prefix}_{base_name}.docx"


def _build_fallback_save_path(file_type: str) -> str:
    """Build non-dialog fallback path (prefer ~/Downloads)."""
    candidates = [
        os.getcwd(),
        tempfile.gettempdir(),
        os.path.join(os.path.expanduser("~"), "Downloads"),
    ]
    target_dir = os.getcwd()
    for folder in candidates:
        if os.path.isdir(folder) and os.access(folder, os.W_OK):
            target_dir = folder
            break

    base_name = _build_download_filename(file_type)
    root, ext = os.path.splitext(base_name)
    candidate = os.path.join(target_dir, base_name)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(target_dir, f"{root}_{counter}{ext}")
        counter += 1
    return candidate


@eel.expose
def load_file(file_path):
    """Load a .txt or .docx file from a local filesystem path."""
    try:
        text, _ = processor.load_document(file_path)
        source_docx_path = file_path if str(file_path or "").lower().endswith(".docx") else ""
        return _load_text_to_state(os.path.basename(file_path), text, source_docx_path=source_docx_path)
    except Exception as e:
        return {"success": False, "error": str(e)}


@eel.expose
def load_text_content(file_name, content):
    """Load plain text content from browser file reader."""
    try:
        return _load_text_to_state(file_name, content)
    except Exception as e:
        return {"success": False, "error": str(e)}


@eel.expose
def load_docx_content(file_name, base64_data):
    """Load DOCX content from base64 payload."""
    try:
        byte_data = base64.b64decode(base64_data)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as handle:
            handle.write(byte_data)
            temp_path = handle.name

        try:
            text, _ = processor.load_document(temp_path)
            return _load_text_to_state(file_name, text, source_docx_path="")
        finally:
            os.unlink(temp_path)
    except Exception as e:
        return {"success": False, "error": str(e) + "\n" + traceback.format_exc()}


@eel.expose
def process_document(options):
    """Process the currently loaded document with selected options."""
    global original_text, corrected_text, full_corrected_text
    try:
        if not original_text.strip():
            return {"success": False, "error": "No document loaded"}

        full_corrected_text = processor.process_text(original_text, options or {})
        corrected_text = full_corrected_text
        return _build_process_payload(original_text, corrected_text, options)
    except Exception as e:
        return {"success": False, "error": str(e)}


@eel.expose
def apply_correction_group_decisions(group_decisions):
    """Apply accept/reject decisions by correction group and refresh preview/export state."""
    global original_text, corrected_text, full_corrected_text
    try:
        if not original_text.strip():
            return {"success": False, "error": "No document loaded"}
        if not full_corrected_text.strip():
            return {"success": False, "error": "No corrected document available"}

        corrected_text = processor.apply_group_decisions(original_text, full_corrected_text, group_decisions or {})
        return _build_process_payload(original_text, corrected_text, None)
    except Exception as e:
        return {"success": False, "error": str(e)}


@eel.expose
def get_redline_preview():
    """Get redline HTML for current original and corrected text."""
    global original_text, corrected_text
    try:
        if not original_text.strip():
            return {"success": False, "error": "No document loaded"}
        if not corrected_text.strip():
            return {"success": False, "error": "No corrected document available"}
        return {
            "success": True,
            "redline_html": processor.build_redline_html(original_text, corrected_text),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@eel.expose
def get_ollama_models(ollama_host=None):
    """Return detected Ollama models for dropdown population."""
    try:
        host = str(ollama_host or processor.ollama_host).strip() or processor.ollama_host
        models = processor._get_ollama_models(host)
        default_model = processor._resolve_ollama_model(host, processor.model)
        return {
            "success": True,
            "models": models,
            "default_model": default_model,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "models": []}


@eel.expose
def export_file(file_type):
    """Export clean/highlighted DOCX as base64 for browser download."""
    global original_text, corrected_text
    runtime_telemetry["export_attempts"] += 1
    try:
        if not corrected_text.strip():
            runtime_telemetry["export_failures"] += 1
            return _error_payload("EXPORT_NO_CORRECTED_DOC", "No corrected document available")

        if file_type not in ("clean", "highlighted", "redline"):
            runtime_telemetry["export_failures"] += 1
            return _error_payload("EXPORT_UNSUPPORTED_TYPE", "Unsupported file type", file_type=str(file_type))

        res = manuscript_service.generate_docx_export_base64(
            processor=processor,
            original_text=original_text,
            corrected_text=corrected_text,
            file_type=file_type,
            source_docx_path=current_source_docx_path,
        )
        runtime_telemetry["export_successes"] += 1
        res["file_name"] = _build_download_filename(file_type)
        return res
    except Exception as e:
        runtime_telemetry["export_failures"] += 1
        return _error_payload("EXPORT_EXCEPTION", str(e))


@eel.expose
def save_file(file_type):
    """Save clean or highlighted DOCX output."""
    global original_text, corrected_text
    runtime_telemetry["save_attempts"] += 1

    try:
        if not corrected_text.strip():
            runtime_telemetry["save_failures"] += 1
            return _error_payload("SAVE_NO_CORRECTED_DOC", "No corrected document available")

        path = ""
        tk_failed = False
        tk_error = ""

        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            try:
                if file_type == "clean":
                    path = filedialog.asksaveasfilename(
                        title="Save Clean Version",
                        defaultextension=".docx",
                        filetypes=[("Word documents", "*.docx")],
                    )
                else:
                    path = filedialog.asksaveasfilename(
                        title="Save Highlighted Version",
                        defaultextension=".docx",
                        filetypes=[("Word documents", "*.docx")],
                    )
            finally:
                root.destroy()
        except Exception as e:
            tk_failed = True
            tk_error = str(e)

        if not path:
            if not tk_failed:
                runtime_telemetry["save_failures"] += 1
                return _error_payload("SAVE_NO_PATH_SELECTED", "No path selected")
            path = _build_fallback_save_path(file_type)
            runtime_telemetry["save_fallback_used"] += 1

        if file_type not in ("clean", "highlighted", "redline"):
            runtime_telemetry["save_failures"] += 1
            return _error_payload("SAVE_UNSUPPORTED_TYPE", "Unsupported file type", file_type=str(file_type))

        manuscript_service.generate_docx_file(
            processor=processor,
            original_text=original_text,
            corrected_text=corrected_text,
            file_type=file_type,
            dest_path=path,
            source_docx_path=current_source_docx_path,
        )

        runtime_telemetry["save_successes"] += 1
        result = {"success": True, "path": path}
        if tk_failed and tk_error:
            result["warning_code"] = "SAVE_DIALOG_UNAVAILABLE_FALLBACK_USED"
            result["note"] = f"Save dialog unavailable; auto-saved to fallback path. ({tk_error})"
        return result
    except Exception as e:
        runtime_telemetry["save_failures"] += 1
        return _error_payload("SAVE_EXCEPTION", str(e))


def main():
    """Main entry point."""
    setup_web_folder()
    eel.init(web_folder)
    eel.start("index.html", size=(1000, 700), port=8000)


if __name__ == "__main__":
    main()
