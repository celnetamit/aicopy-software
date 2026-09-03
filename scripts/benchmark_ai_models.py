#!/usr/bin/env python3
"""Compare AI providers/models on the copyedit workload this app actually runs.

Why acceptance rate is the headline metric
------------------------------------------
``DocumentProcessor._select_best_correction`` scores each candidate on how far
it drifts from the source and discards it in favour of the rules-only baseline
when it drifts too far. So a model is not judged on prose quality here — it is
judged on restraint. A model that rewrites enthusiastically produces a high
fallback rate, and the audit trail records "fallback" as though the AI failed.

The columns below therefore separate three different questions:

  accept%     did the pipeline trust the model's output?
  fallback    if not, why — "heavy rewrite" (too creative) vs "citation loss"
              (mangles invariants, which is disqualifying regardless of prose)
  cites/dois  did the invariants that must never change survive?

Usage
-----
    # bundled fixture, two candidates
    python3 scripts/benchmark_ai_models.py \\
        --target gemini:gemini-2.0-flash \\
        --target ollama:llama3.1

    # your own manuscript, three runs each, JSON for later comparison
    python3 scripts/benchmark_ai_models.py \\
        --manuscript path/to/paper.docx \\
        --target openrouter:openai/gpt-4o-mini \\
        --runs 3 --json results.json

A target is ``provider:model``, split on the first colon only, so
``ollama:llama3.1:8b`` and ``openrouter:vendor/model`` both parse correctly.
Provider must be one of: ollama, gemini, openrouter, agent_router.

Credentials come from the environment (GEMINI_API_KEY, OPENROUTER_API_KEY,
AGENT_ROUTER_TOKEN) exactly as the app reads them. Online reference validation
is off by default: it adds network time and variance that has nothing to do
with the model under test.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document_processor import (  # noqa: E402
    AI_TEMPERATURE_DEFAULT,
    DocumentProcessor,
)

VALID_PROVIDERS = ("ollama", "gemini", "openrouter", "agent_router")
DEFAULT_FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests",
    "fixtures",
    "benchmark_manuscript.txt",
)

CITATION_RE = re.compile(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s,;)\]]+", re.IGNORECASE)
URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://[^\s<>\"']+")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Disqualifying regardless of how good the prose is.
INVARIANT_FALLBACK_REASONS = ("citation_loss", "missing_doi", "missing_urls", "missing_emails")


def parse_target(raw: str) -> Tuple[str, str]:
    """Split ``provider:model`` on the first colon only."""
    value = str(raw or "").strip()
    if ":" not in value:
        raise argparse.ArgumentTypeError(
            f"target {raw!r} must be provider:model (e.g. gemini:gemini-2.0-flash)"
        )
    provider, model = value.split(":", 1)
    provider = provider.strip().lower()
    model = model.strip()
    if provider not in VALID_PROVIDERS:
        raise argparse.ArgumentTypeError(
            f"unknown provider {provider!r}; expected one of {', '.join(VALID_PROVIDERS)}"
        )
    if not model:
        raise argparse.ArgumentTypeError(f"target {raw!r} has no model")
    return provider, model


def load_manuscript(path: str) -> str:
    if path.lower().endswith(".docx"):
        text, _ = DocumentProcessor().load_document(path)
        return text
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def build_options(provider: str, model: str, args: argparse.Namespace) -> Dict[str, Any]:
    """Mirror the option shape the web app hands to the processor."""
    return {
        "spelling": True,
        "sentence_case": True,
        "punctuation": True,
        "chicago_style": True,
        "cmos_strict_mode": True,
        "cmos_profile": "strict",
        "editing_mode": "copyedit",
        "tone": "neutral",
        "rewrite_strength": "minimal",
        "journal_profile": "vancouver_nlm",
        "reference_profile": "vancouver_nlm",
        "online_reference_validation": bool(args.online_validation),
        "online_reference_serper_fallback": bool(args.online_validation),
        "ai": {
            "enabled": True,
            "provider": provider,
            "model": model,
            "temperature": args.temperature,
            "ollama_host": args.ollama_host,
            "section_wise": True,
            "section_threshold_chars": args.section_threshold_chars,
            "section_chunk_chars": args.chunk_chars,
            "section_concurrency": args.concurrency,
            "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
            "openrouter_api_key": os.getenv("OPENROUTER_API_KEY", ""),
            "agent_router_api_key": os.getenv("AGENT_ROUTER_TOKEN", ""),
        },
    }


def missing_credential(provider: str) -> str:
    required = {
        "gemini": "GEMINI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "agent_router": "AGENT_ROUTER_TOKEN",
    }.get(provider)
    if required and not str(os.getenv(required, "") or "").strip():
        return required
    return ""


def citation_numbers(text: str) -> set:
    """Every distinct citation number, regardless of bracket spelling.

    The rules pass legitimately rewrites ``[2,3]`` to ``[2, 3]``, so comparing
    bracket literals would report a loss where nothing was lost. What matters is
    whether citation 3 still appears anywhere.
    """
    numbers = set()
    for group in CITATION_RE.findall(text):
        numbers.update(int(n) for n in re.findall(r"\d+", group))
    return numbers


def normalized_identifiers(pattern: re.Pattern, text: str) -> set:
    """Identifiers with trailing punctuation and case differences folded away.

    Reference normalization appends a period to DOIs; that is formatting, not
    loss, and must not be reported as a dropped invariant.
    """
    found = set()
    for raw in pattern.findall(text):
        value = str(raw).strip().rstrip(".,;:)]}").lower()
        if value:
            found.add(value)
    return found


def measure(original: str, corrected: str) -> Dict[str, Any]:
    """Invariant retention and edit volume, independent of the pipeline's own verdict."""
    processor = DocumentProcessor()
    report = processor.build_corrections_report(original, corrected)

    def retained(pattern: re.Pattern) -> Tuple[int, int]:
        before = normalized_identifiers(pattern, original)
        after = normalized_identifiers(pattern, corrected)
        return len(before & after), len(before)

    cites_before = citation_numbers(original)
    cites_kept = len(cites_before & citation_numbers(corrected))
    cites_total = len(cites_before)
    dois_kept, dois_total = retained(DOI_RE)
    urls_kept, urls_total = retained(URL_RE)
    emails_kept, emails_total = retained(EMAIL_RE)

    return {
        "length_ratio": round(len(corrected) / max(1, len(original)), 4),
        "word_count_original": len(original.split()),
        "word_count_corrected": len(corrected.split()),
        "edits": int(report.get("total") or 0),
        "edit_counts": report.get("counts") or {},
        "citations_kept": cites_kept,
        "citations_total": cites_total,
        "dois_kept": dois_kept,
        "dois_total": dois_total,
        "urls_kept": urls_kept,
        "urls_total": urls_total,
        "emails_kept": emails_kept,
        "emails_total": emails_total,
    }


def run_once(original: str, provider: str, model: str, args: argparse.Namespace) -> Dict[str, Any]:
    processor = DocumentProcessor(ollama_host=args.ollama_host)
    options = build_options(provider, model, args)

    started = time.perf_counter()
    try:
        corrected = processor.process_text(original, options)
        error = ""
    except Exception as exc:  # noqa: BLE001 - a provider failure is a result, not a crash
        corrected = ""
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started

    audit = processor.get_processing_audit() or {}
    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}

    result: Dict[str, Any] = {
        "provider": provider,
        "model": model,
        "error": error,
        "wall_seconds": round(elapsed, 2),
        "mode": str(audit.get("mode") or "unknown"),
        "total_sections": int(summary.get("total_sections") or 0),
        "accepted_sections": int(summary.get("accepted_sections") or 0),
        "acceptance_rate": float(summary.get("acceptance_rate") or 0.0),
        "fallback_reason_counts": summary.get("fallback_reason_counts") or {},
        "selection_note": str(getattr(processor, "_last_selection_note", "") or "")[:300],
        "tokens": int(getattr(processor, "_tokens_consumed", 0) or 0),
    }
    if corrected:
        result.update(measure(original, corrected))
    return result


def aggregate(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Collapse repeat runs, carrying spread where it matters."""
    ok = [r for r in runs if not r.get("error")]
    if not ok:
        return {**runs[0], "runs": len(runs), "acceptance_spread": 0.0}

    def mean(key: str) -> float:
        values = [float(r.get(key) or 0.0) for r in ok]
        return round(statistics.fmean(values), 4) if values else 0.0

    merged_reasons: Dict[str, int] = {}
    for run in ok:
        for reason, count in (run.get("fallback_reason_counts") or {}).items():
            merged_reasons[reason] = merged_reasons.get(reason, 0) + int(count or 0)

    rates = [float(r.get("acceptance_rate") or 0.0) for r in ok]
    return {
        **ok[0],
        "runs": len(runs),
        "failed_runs": len(runs) - len(ok),
        "wall_seconds": mean("wall_seconds"),
        "acceptance_rate": mean("acceptance_rate"),
        "acceptance_spread": round(max(rates) - min(rates), 2) if len(rates) > 1 else 0.0,
        "length_ratio": mean("length_ratio"),
        "edits": round(mean("edits")),
        "tokens": round(mean("tokens")),
        "fallback_reason_counts": dict(sorted(merged_reasons.items(), key=lambda p: (-p[1], p[0]))),
    }


def format_reasons(reasons: Dict[str, int]) -> str:
    if not reasons:
        return "-"
    return ", ".join(f"{name} x{count}" for name, count in list(reasons.items())[:3])


def render_table(rows: List[Dict[str, Any]]) -> str:
    headers = ["target", "mode", "sect", "acc", "accept%", "fallback reasons", "len", "cites", "dois", "edits", "tokens", "wall"]
    table: List[List[str]] = []

    for row in rows:
        target = f"{row['provider']}:{row['model']}"
        if row.get("error"):
            table.append([target, "ERROR", "-", "-", "-", row["error"][:44], "-", "-", "-", "-", "-", "-"])
            continue
        accept = f"{row['acceptance_rate']:.1f}%"
        if row.get("acceptance_spread"):
            accept += f" ±{row['acceptance_spread']:.0f}"
        table.append([
            target,
            row.get("mode", "-"),
            str(row.get("total_sections", 0)) if row.get("total_sections") else "-",
            str(row.get("accepted_sections", 0)) if row.get("total_sections") else "-",
            accept,
            format_reasons(row.get("fallback_reason_counts") or {}),
            f"{row.get('length_ratio', 0):.3f}",
            f"{row.get('citations_kept', 0)}/{row.get('citations_total', 0)}",
            f"{row.get('dois_kept', 0)}/{row.get('dois_total', 0)}",
            str(row.get("edits", 0)),
            str(row.get("tokens") or "-"),
            f"{row.get('wall_seconds', 0):.1f}s",
        ])

    widths = [max(len(headers[i]), *(len(r[i]) for r in table)) for i in range(len(headers))] if table \
        else [len(h) for h in headers]
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    rule = "  ".join("-" * widths[i] for i in range(len(headers)))
    body = "\n".join("  ".join(r[i].ljust(widths[i]) for i in range(len(headers))) for r in table)
    return f"{line}\n{rule}\n{body}"


def render_verdicts(rows: List[Dict[str, Any]]) -> List[str]:
    """Flag results that disqualify a model regardless of its acceptance rate."""
    notes: List[str] = []
    for row in rows:
        target = f"{row['provider']}:{row['model']}"
        if row.get("error"):
            continue
        reasons = row.get("fallback_reason_counts") or {}
        broke = [name for name in reasons if name in INVARIANT_FALLBACK_REASONS]
        if broke:
            notes.append(f"  ! {target}: dropped invariants ({', '.join(broke)}) — disqualifying for this pipeline")
        if row.get("citations_total") and row.get("citations_kept", 0) < row["citations_total"]:
            notes.append(f"  ! {target}: lost {row['citations_total'] - row['citations_kept']} citation marker(s) in the final text")
        if row.get("dois_total") and row.get("dois_kept", 0) < row["dois_total"]:
            notes.append(f"  ! {target}: lost {row['dois_total'] - row['dois_kept']} DOI(s) in the final text")
        if row.get("mode") == "rule_only":
            notes.append(f"  ! {target}: AI produced nothing usable — output is rules-only ({row.get('selection_note', '')[:80]})")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare AI providers/models on this app's copyedit workload.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", action="append", type=parse_target, required=True,
                        metavar="PROVIDER:MODEL", help="repeatable; e.g. gemini:gemini-2.0-flash")
    parser.add_argument("--manuscript", default=DEFAULT_FIXTURE,
                        help="path to a .txt or .docx manuscript (default: bundled fixture)")
    parser.add_argument("--runs", type=int, default=1, help="repeat each target N times (default 1)")
    parser.add_argument("--temperature", type=float, default=AI_TEMPERATURE_DEFAULT,
                        help=f"sampling temperature for every target (default {AI_TEMPERATURE_DEFAULT})")
    parser.add_argument("--concurrency", type=int, default=4, help="section prompts in flight (default 4)")
    parser.add_argument("--chunk-chars", type=int, default=5500, dest="chunk_chars")
    parser.add_argument("--section-threshold-chars", type=int, default=12000, dest="section_threshold_chars")
    parser.add_argument("--ollama-host", default=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    parser.add_argument("--online-validation", action="store_true",
                        help="also run online reference validation (slower, adds network variance)")
    parser.add_argument("--json", dest="json_path", default="", help="write full results to this path")
    args = parser.parse_args()

    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if not os.path.isfile(args.manuscript):
        parser.error(f"manuscript not found: {args.manuscript}")

    original = load_manuscript(args.manuscript)
    if not original.strip():
        parser.error(f"manuscript is empty: {args.manuscript}")

    print(f"\nAI MODEL BENCHMARK — {os.path.basename(args.manuscript)} "
          f"({len(original):,} chars, {len(original.split()):,} words)")
    print(f"temperature={args.temperature}  concurrency={args.concurrency}  "
          f"chunk={args.chunk_chars}  online_validation={'on' if args.online_validation else 'off'}  "
          f"runs={args.runs}\n")

    rows: List[Dict[str, Any]] = []
    all_runs: Dict[str, List[Dict[str, Any]]] = {}

    for provider, model in args.target:
        target = f"{provider}:{model}"
        missing = missing_credential(provider)
        if missing:
            print(f"  skipping {target}: {missing} is not set")
            rows.append({"provider": provider, "model": model, "error": f"{missing} not set"})
            continue

        print(f"  running {target} ...", end="", flush=True)
        runs = [run_once(original, provider, model, args) for _ in range(args.runs)]
        all_runs[target] = runs
        merged = aggregate(runs)
        rows.append(merged)
        print(f" {merged.get('wall_seconds', 0):.1f}s"
              + (f"  ({merged['error'][:60]})" if merged.get("error") else ""))

    print("\n" + render_table(rows) + "\n")

    notes = render_verdicts(rows)
    if notes:
        print("Findings")
        print("\n".join(notes) + "\n")

    print("How to read this")
    print("  accept%   share of sections the pipeline trusted; low means the model drifted too far")
    print("  fallback  why sections were rejected — 'heavy rewrite' is style, 'citation loss' is disqualifying")
    print("  len       corrected/original length; the scorer penalises outside 0.75-1.35")
    print("  edits     corrections the model plus rules produced — more is not automatically better\n")

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "manuscript": os.path.abspath(args.manuscript),
                    "chars": len(original),
                    "settings": {
                        "temperature": args.temperature,
                        "concurrency": args.concurrency,
                        "chunk_chars": args.chunk_chars,
                        "section_threshold_chars": args.section_threshold_chars,
                        "online_validation": bool(args.online_validation),
                        "runs": args.runs,
                    },
                    "summary": rows,
                    "runs": all_runs,
                },
                handle,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        print(f"Full results written to {args.json_path}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
