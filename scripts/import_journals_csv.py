#!/usr/bin/env python3
"""Import journals CSV into manuscript_editor journals table.

Safe behavior:
- Upsert by case-insensitive journal name
- Preserve existing records while updating mapped fields
- Keep is_active=True for imported records
"""

from __future__ import annotations

import csv
import os
from typing import Dict, List

from app_store import AppStore

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
DEFAULT_DB = f"sqlite:///{os.path.join(DATA_DIR, 'manuscript_editor.sqlite3')}"


def split_csv_list(raw: str) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    parts = [p.strip(" -\t\n\r") for p in text.replace("\n", ",").split(",")]
    out: List[str] = []
    seen = set()
    for part in parts:
        if not part:
            continue
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out[:120]


def compact_scope(focus_scope: str, about: str, category: str) -> str:
    focus = " ".join(str(focus_scope or "").split())
    about_text = " ".join(str(about or "").split())
    category_text = str(category or "").strip()
    scope = focus if focus else about_text
    if category_text:
        scope = f"[{category_text}] {scope}" if scope else category_text
    # Keep payload manageable while preserving meaning for ranking.
    return scope[:4000]


def main() -> int:
    csv_path = os.path.join(ROOT_DIR, "docs", "journals_export_2026-06-01.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    database_url = str(os.getenv("DATABASE_URL", "") or "").strip() or DEFAULT_DB
    store = AppStore(database_url=database_url, data_dir=DATA_DIR)

    existing = store.list_journals(include_inactive=True, limit=50000)
    by_name: Dict[str, Dict] = {}
    for row in existing:
        name_key = str(row.get("name") or "").strip().lower()
        if name_key:
            by_name[name_key] = row

    created = 0
    updated = 0
    skipped = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = str((row or {}).get("Name") or "").strip()
            if not name:
                skipped += 1
                continue

            category = str((row or {}).get("Category") or "").strip()
            submission_url = str((row or {}).get("Submission URL") or "").strip()
            focus_scope = str((row or {}).get("Focus & Scope") or "").strip()
            keywords = split_csv_list(str((row or {}).get("Keywords") or ""))
            subject_areas = split_csv_list(str((row or {}).get("Primary Domains") or ""))
            about = str((row or {}).get("About") or "").strip()

            payload = {
                "name": name,
                "scope": compact_scope(focus_scope, about, category),
                "keywords": keywords,
                "subject_areas": subject_areas,
                "article_types": [],
                "issn_print": "",
                "issn_online": "",
                "publisher": category,
                "quartile": "",
                "open_access": False,
                "apc_usd": 0,
                "submission_url": submission_url,
                "is_active": True,
            }

            key = name.lower()
            current = by_name.get(key)
            if current is None:
                created_row = store.create_journal(payload)
                if created_row and created_row.get("id"):
                    created += 1
                    by_name[key] = created_row
                else:
                    skipped += 1
                continue

            updated_row = store.update_journal(str(current.get("id") or ""), payload)
            if updated_row and updated_row.get("id"):
                updated += 1
                by_name[key] = updated_row
            else:
                skipped += 1

    print(f"database_url={database_url}")
    print(f"csv_path={csv_path}")
    print(f"created={created}")
    print(f"updated={updated}")
    print(f"skipped={skipped}")
    print(f"total_after={len(store.list_journals(include_inactive=True, limit=50000))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
