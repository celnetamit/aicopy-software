"""Unified, centralized processing and export logic for Manuscript Editor.

This service eliminates code drift and redundancy between the Eel backend (main.py)
and the WSGI webapp (webapp.py) by providing a single source of truth.
"""

import os
import re
import base64
import zipfile
import tempfile
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional

def get_default_runtime_telemetry() -> Dict[str, Any]:
    """Return the standardized runtime telemetry dictionary schema."""
    return {
        "export_attempts": 0,
        "export_successes": 0,
        "export_failures": 0,
        "save_attempts": 0,
        "save_successes": 0,
        "save_failures": 0,
        "save_fallback_used": 0,
        "process_runs_started": 0,
        "process_runs_succeeded": 0,
        "process_runs_failed": 0,
        "process_async_started": 0,
        "process_async_succeeded": 0,
        "process_async_failed": 0,
        "task_run_pending": 0,
        "task_run_running": 0,
        "task_run_succeeded": 0,
        "task_run_failed": 0,
        "async_run_duration_samples": {"count": 0, "total_seconds": 0.0, "max_seconds": 0.0},
        "mode_counts": {},
        "editing_mode_counts": {},
        "tone_counts": {},
        "rewrite_strength_counts": {},
        "explain_edits_counts": {},
        "fallback_reason_counts": {},
        "errors_by_code": {},
    }

def extract_docx_preview_images(source_docx_path: str, max_images: int = 20, max_bytes: int = 6 * 1024 * 1024) -> List[Dict[str, Any]]:
    """Extract embedded DOCX media images in document order for browser preview."""
    if not source_docx_path or not os.path.exists(source_docx_path):
        return []

    mime_by_ext = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
    }

    def _safe_media_target(target: str) -> str:
        candidate = str(target or "").replace("\\", "/").strip()
        if not candidate:
            return ""
        if candidate.startswith("/"):
            candidate = candidate[1:]
        if candidate.startswith("../"):
            candidate = candidate[3:]
        if candidate.startswith("word/"):
            return candidate
        if candidate.startswith("media/"):
            return "word/" + candidate
        return "word/" + candidate

    images: List[Dict[str, Any]] = []
    seen_targets = set()
    try:
        with zipfile.ZipFile(source_docx_path) as archive:
            names = set(archive.namelist())
            ordered_targets: List[str] = []
            if "word/document.xml" in names and "word/_rels/document.xml.rels" in names:
                try:
                    doc_xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
                    rel_root = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
                    rel_map: Dict[str, str] = {}
                    for node in rel_root.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
                        rel_id = str(node.attrib.get("Id") or "")
                        target = _safe_media_target(str(node.attrib.get("Target") or ""))
                        if rel_id and target.startswith("word/media/"):
                            rel_map[rel_id] = target
                    for rel_id in re.findall(r'r:embed="([^"]+)"', doc_xml):
                        target = rel_map.get(rel_id)
                        if target and target not in ordered_targets:
                            ordered_targets.append(target)
                except Exception:
                    ordered_targets = []

            if not ordered_targets:
                ordered_targets = sorted(
                    [name for name in names if name.startswith("word/media/")],
                    key=lambda item: item.lower(),
                )

            total_bytes = 0
            for target in ordered_targets:
                if len(images) >= max(1, int(max_images or 1)):
                    break
                if target in seen_targets:
                    continue
                seen_targets.add(target)
                _, ext = os.path.splitext(target.lower())
                mime = mime_by_ext.get(ext)
                if not mime:
                    continue
                if target not in names:
                    continue
                blob = archive.read(target)
                if not blob:
                    continue
                total_bytes += len(blob)
                if total_bytes > max_bytes:
                    break
                encoded = base64.b64encode(blob).decode("ascii")
                images.append(
                    {
                        "name": os.path.basename(target),
                        "mime_type": mime,
                        "size_bytes": len(blob),
                        "data_url": f"data:{mime};base64,{encoded}",
                    }
                )
    except Exception:
        return []

    return images

def build_process_payload(
    processor,
    task_id: str,
    original_text: str,
    corrected_text: str,
    full_corrected_text: str,
    source_type: str,
    source_docx_path: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build standard process response payload with rich metadata and features."""
    corrections_report = processor.build_corrections_report(original_text, corrected_text)
    edit_explanations = processor.build_edit_explanations(corrections_report, options or {})
    process_payload = {
        "success": True,
        "task_id": task_id,
        "text": corrected_text,
        "original": original_text,
        "full_corrected_text": full_corrected_text or corrected_text,
        "word_count": len(str(corrected_text or "").split()),
        "redline_html": processor.build_redline_html(original_text, corrected_text),
        "prose_only_diff": processor.build_prose_only_diff_text(original_text, corrected_text),
        "strict_cmos_issues": processor.build_strict_cmos_issues_summary(original_text, corrected_text, options or {}),
        "corrected_annotated_html": processor.build_foreign_annotated_html(corrected_text),
        "corrections_report": corrections_report,
        "noun_report": processor.build_noun_report(corrected_text),
        "domain_report": processor.get_domain_report(),
        "journal_profile_report": processor.get_journal_profile_report(),
        "citation_reference_report": processor.get_citation_reference_report(),
        "processing_audit": processor.get_processing_audit(),
        "processing_note": getattr(processor, "_last_selection_note", ""),
        "edit_explanations": edit_explanations,
    }
    
    if str(source_type or "").lower() == "docx" and source_docx_path:
        preview_images = extract_docx_preview_images(source_docx_path)
        process_payload["docx_preview_images"] = preview_images
        audit = process_payload.get("processing_audit") if isinstance(process_payload.get("processing_audit"), dict) else {}
        summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
        summary["docx_preview_images"] = preview_images
        audit["summary"] = summary
        process_payload["processing_audit"] = audit
        
    return process_payload

def generate_docx_export_base64(
    processor,
    original_text: str,
    corrected_text: str,
    file_type: str,
    source_docx_path: str = "",
) -> Dict[str, Any]:
    """Generate clean/highlighted/tracked docx, returning base64 string, size, and mime-type."""
    ft_clean = str(file_type or "").strip().lower()
    
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as handle:
            temp_path = handle.name

        if ft_clean == "clean":
            processor.generate_clean_docx(corrected_text, temp_path, source_docx_path=source_docx_path)
        else:
            export_mode = "visual"
            if ft_clean == "highlighted_comments":
                export_mode = "visual_comments"
            elif ft_clean == "track_changes":
                export_mode = "track_changes"
                
            processor.generate_highlighted_docx(
                original_text,
                corrected_text,
                temp_path,
                source_docx_path=source_docx_path,
                export_mode=export_mode,
            )

        with open(temp_path, "rb") as infile:
            blob = infile.read()
            encoded = base64.b64encode(blob).decode("ascii")
            
        return {
            "success": True,
            "base64_data": encoded,
            "size_bytes": len(blob),
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass

def generate_docx_file(
    processor,
    original_text: str,
    corrected_text: str,
    file_type: str,
    dest_path: str,
    source_docx_path: str = "",
) -> None:
    """Generate clean or styled DOCX file to a destination path."""
    ft_clean = str(file_type or "").strip().lower()
    if ft_clean == "clean":
        processor.generate_clean_docx(corrected_text, dest_path, source_docx_path=source_docx_path)
    else:
        export_mode = "visual"
        if ft_clean == "highlighted_comments":
            export_mode = "visual_comments"
        elif ft_clean == "track_changes":
            export_mode = "track_changes"
            
        processor.generate_highlighted_docx(
            original_text,
            corrected_text,
            dest_path,
            source_docx_path=source_docx_path,
            export_mode=export_mode,
        )
