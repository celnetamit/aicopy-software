"""Journal recommendation service.

Computes deterministic suitability scores from manuscript and journal metadata,
then optionally enhances top recommendations with short AI rationales.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests


TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9\-]{1,}")
STOPWORDS = {
    "the", "and", "for", "with", "that", "from", "this", "have", "has", "were", "was", "are", "is", "into", "their",
    "manuscript", "study", "paper", "journal", "using", "used", "based", "between", "within", "analysis", "results",
}


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(str(text or "")) if t and t.lower() not in STOPWORDS]


def _top_terms(tokens: Sequence[str], limit: int = 80) -> List[str]:
    counts: Dict[str, int] = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
    return [term for term, _ in ranked[: max(1, int(limit))]]


def _to_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(v).strip() for v in raw if str(v).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except Exception:
            pass
        return [chunk.strip() for chunk in re.split(r"[,;\n]", text) if chunk.strip()]
    return []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _build_ai_prompt(manuscript_excerpt: str, journal_name: str, matched_signals: List[str]) -> str:
    signal_text = ", ".join(matched_signals[:6]) if matched_signals else "general scope fit"
    return (
        "You are an academic publishing assistant. "
        "Write one concise sentence (max 28 words) explaining why this journal is suitable for the manuscript. "
        "Do not use markdown or bullets.\n"
        f"Journal: {journal_name}\n"
        f"Matched signals: {signal_text}\n"
        f"Manuscript excerpt: {manuscript_excerpt[:700]}"
    )


def _build_ai_ranking_prompt(manuscript_text: str, candidates: Sequence[Dict[str, Any]]) -> str:
    packed = []
    for item in candidates:
        packed.append(
            {
                "journal_id": str(item.get("journal_id") or ""),
                "journal_name": str(item.get("journal_name") or ""),
                "scope": str(item.get("scope") or ""),
                "keywords": item.get("keywords") if isinstance(item.get("keywords"), list) else [],
                "subject_areas": item.get("subject_areas") if isinstance(item.get("subject_areas"), list) else [],
                "article_types": item.get("article_types") if isinstance(item.get("article_types"), list) else [],
            }
        )
    return (
        "You are an expert manuscript-to-journal matching assistant.\n"
        "Read the manuscript and rank the top 3 best-fit journals from the candidate list.\n"
        "Return strict JSON only with this shape: "
        "{\"top\":[{\"journal_id\":\"...\",\"reason\":\"...\"},...]} "
        "where top has at most 3 items in rank order.\n"
        "Keep each reason concise (max 24 words).\n\n"
        f"MANUSCRIPT:\n{manuscript_text[:24000]}\n\n"
        f"CANDIDATES_JSON:\n{json.dumps(packed, ensure_ascii=False)}"
    )


def _ai_rationale_from_provider(prompt: str, ai_settings: Dict[str, Any]) -> Optional[str]:
    provider = str(ai_settings.get("provider", "") or "").strip().lower()
    model = str(ai_settings.get("model", "") or "").strip()
    timeout = 7

    if provider == "ollama":
        host = str(ai_settings.get("ollama_host", "http://localhost:11434") or "http://localhost:11434").strip()
        use_model = model or "llama3.1"
        response = requests.post(
            f"{host}/api/generate",
            json={"model": use_model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        if response.status_code >= 300:
            return None
        data = response.json() if response.content else {}
        return str(data.get("response", "") or "").strip() or None

    if provider == "gemini":
        key = str(ai_settings.get("gemini_api_key", "") or ai_settings.get("api_key", "") or "").strip()
        if not key:
            return None
        use_model = model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent?key={key}"
        response = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=timeout,
        )
        if response.status_code >= 300:
            return None
        data = response.json() if response.content else {}
        candidates = data.get("candidates") if isinstance(data, dict) else []
        if not isinstance(candidates, list) or not candidates:
            return None
        parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
        for part in parts:
            txt = str((part or {}).get("text", "") or "").strip()
            if txt:
                return txt
        return None

    if provider in {"openrouter", "agent_router"}:
        if provider == "openrouter":
            key = str(ai_settings.get("openrouter_api_key", "") or ai_settings.get("api_key", "") or "").strip()
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            use_model = model or "openrouter/auto"
        else:
            key = str(ai_settings.get("agent_router_api_key", "") or ai_settings.get("api_key", "") or "").strip()
            url = "https://api.agentrouter.ai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            use_model = model or "deepseek-v3.1"
        if not key:
            return None
        response = requests.post(
            url,
            headers=headers,
            json={
                "model": use_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 80,
            },
            timeout=timeout,
        )
        if response.status_code >= 300:
            return None
        data = response.json() if response.content else {}
        choices = data.get("choices") if isinstance(data, dict) else []
        if not isinstance(choices, list) or not choices:
            return None
        content = ((choices[0] or {}).get("message") or {}).get("content")
        return str(content or "").strip() or None

    return None


def _parse_ai_rank_json(text: str) -> List[Dict[str, str]]:
    if not text:
        return []
    raw = str(text).strip()
    # try direct JSON
    for candidate in (raw, raw.replace("```json", "").replace("```", "").strip()):
        try:
            obj = json.loads(candidate)
            top = obj.get("top") if isinstance(obj, dict) else None
            if isinstance(top, list):
                out: List[Dict[str, str]] = []
                for row in top:
                    if not isinstance(row, dict):
                        continue
                    jid = str(row.get("journal_id") or "").strip()
                    reason = str(row.get("reason") or "").strip()
                    if not jid:
                        continue
                    out.append({"journal_id": jid, "reason": reason})
                if out:
                    return out
        except Exception:
            continue
    return []


def recommend_top_journals(
    *,
    journals: Sequence[Dict[str, Any]],
    manuscript_text: str,
    corrected_text: str,
    journal_profile_report: Optional[Dict[str, Any]] = None,
    citation_reference_report: Optional[Dict[str, Any]] = None,
    ai_settings: Optional[Dict[str, Any]] = None,
    top_k: int = 3,
) -> Dict[str, Any]:
    safe_journals = [dict(j) for j in journals if isinstance(j, dict) and bool(j.get("is_active", True))]
    if not safe_journals:
        return {"success": True, "recommendations": [], "warning": "No active journals configured."}

    manuscript = str(corrected_text or manuscript_text or "")
    tokens = _tokenize(manuscript)
    top_terms = set(_top_terms(tokens, limit=90))

    safe_journal_report = journal_profile_report if isinstance(journal_profile_report, dict) else {}
    safe_citation_report = citation_reference_report if isinstance(citation_reference_report, dict) else {}
    ref_count = int(safe_journal_report.get("reference_count") or 0)
    issue_total = int((safe_citation_report.get("summary") or {}).get("total_issues") or 0) if isinstance(safe_citation_report.get("summary"), dict) else 0

    scored: List[Tuple[float, Dict[str, Any]]] = []

    for journal in safe_journals:
        name = str(journal.get("name") or "").strip()
        scope = str(journal.get("scope") or "").strip()
        keywords = _to_list(journal.get("keywords") or journal.get("keywords_json"))
        subject_areas = _to_list(journal.get("subject_areas") or journal.get("subject_areas_json"))
        article_types = _to_list(journal.get("article_types") or journal.get("article_types_json"))
        quartile = str(journal.get("quartile") or "").strip().upper()
        open_access = bool(journal.get("open_access", False))
        apc_usd = _safe_float(journal.get("apc_usd"), 0.0)

        key_terms = set(_tokenize(" ".join([name, scope] + keywords + subject_areas + article_types)))
        overlap_terms = sorted(list(top_terms.intersection(key_terms)))

        overlap_score = min(50.0, float(len(overlap_terms)) * 5.0)
        subject_score = min(20.0, float(len([s for s in subject_areas if any(tok in _tokenize(s) for tok in top_terms)])) * 6.0)
        article_type_score = 0.0
        if article_types:
            lower_text = manuscript.lower()
            if any((t.lower() in lower_text) for t in article_types):
                article_type_score = 12.0

        reference_readiness = 10.0
        if ref_count > 0 and issue_total > 0:
            penalty = min(10.0, float(issue_total) * 0.8)
            reference_readiness = max(0.0, 10.0 - penalty)

        quartile_bonus = {"Q1": 8.0, "Q2": 6.0, "Q3": 4.0, "Q4": 2.0}.get(quartile, 0.0)
        oa_bonus = 3.0 if open_access else 0.0
        apc_penalty = 0.0 if apc_usd <= 0 else (2.0 if apc_usd > 3000 else 1.0)

        score = overlap_score + subject_score + article_type_score + reference_readiness + quartile_bonus + oa_bonus - apc_penalty
        score = max(0.0, min(100.0, score))

        matched_signals: List[str] = []
        if overlap_terms:
            matched_signals.append("Keyword overlap: " + ", ".join(overlap_terms[:5]))
        if subject_areas:
            matched_signals.append("Subject fit: " + ", ".join(subject_areas[:3]))
        if article_type_score > 0:
            matched_signals.append("Article type alignment")
        if quartile:
            matched_signals.append(f"Quartile: {quartile}")
        if open_access:
            matched_signals.append("Open access")
        matched_signals.append(f"Reference readiness score {reference_readiness:.1f}/10")

        scored.append(
            (
                score,
                {
                    "journal_id": str(journal.get("id") or ""),
                    "journal_name": name,
                    "score": round(score, 2),
                    "matched_signals": matched_signals,
                    "rationale": "",
                    "scope": scope,
                    "keywords": keywords,
                    "subject_areas": subject_areas,
                    "article_types": article_types,
                },
            )
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    top_results = [item[1] for item in scored[: max(1, int(top_k))]]

    ai_warning = ""
    ai_used = False
    ai_conf = ai_settings if isinstance(ai_settings, dict) else {}
    ai_enabled = bool(ai_conf.get("enabled", False))

    if ai_enabled:
        try:
            shortlist = [item[1] for item in scored[: min(15, len(scored))]]
            ranking_prompt = _build_ai_ranking_prompt(manuscript, shortlist)
            ranking_text = _ai_rationale_from_provider(ranking_prompt, ai_conf)
            ranked = _parse_ai_rank_json(ranking_text or "")
            if ranked:
                by_id = {str(item.get("journal_id") or ""): item for item in shortlist}
                ai_top: List[Dict[str, Any]] = []
                for row in ranked[:3]:
                    jid = str(row.get("journal_id") or "")
                    if jid in by_id:
                        base = dict(by_id[jid])
                        base["rationale"] = str(row.get("reason") or "").strip()
                        ai_top.append(base)
                if ai_top:
                    ai_used = True
                    top_results = ai_top
            else:
                ai_warning = "AI ranking unavailable; used deterministic ranking."
        except Exception:
            ai_warning = "AI ranking failed; used deterministic ranking."

    for entry in top_results:
        if ai_enabled:
            try:
                if str(entry.get("rationale") or "").strip():
                    ai_text = str(entry.get("rationale") or "").strip()
                else:
                    prompt = _build_ai_prompt(manuscript[:1200], entry["journal_name"], entry.get("matched_signals") or [])
                    ai_text = _ai_rationale_from_provider(prompt, ai_conf)
                if ai_text:
                    entry["rationale"] = ai_text
                    ai_used = True
                else:
                    entry["rationale"] = "Suitable based on scope alignment, keyword overlap, and manuscript-reference fit."
                    ai_warning = ai_warning or "AI rationale unavailable; used fallback rationale."
            except Exception:
                entry["rationale"] = "Suitable based on scope alignment, keyword overlap, and manuscript-reference fit."
                ai_warning = ai_warning or "AI rationale generation failed; used fallback rationale."
        else:
            entry["rationale"] = "Suitable based on scope alignment, keyword overlap, and manuscript-reference fit."

        # Hide internal fields before returning payload.
        entry.pop("scope", None)
        entry.pop("keywords", None)
        entry.pop("subject_areas", None)
        entry.pop("article_types", None)

    return {
        "success": True,
        "recommendations": top_results,
        "ai_used": ai_used,
        "warning": ai_warning,
    }
