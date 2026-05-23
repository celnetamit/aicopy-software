# Latest Application Status (Release Sign-off)

Updated: 2026-05-23  
Repo: `manuscript_editor`  
Branch: `main`  

## Current Stage

`Active Development — v1.2.0-dev`

Extends the approved v1.1.1 public release with two major premium research features:

1. **Phase A — Autonomous Bibliography-Healing Engine**: Fully implemented and wired.
2. **Phase B — Side-by-Side Interactive Split-Canvas Editor**: Fully implemented.

---

## v1.2.0 Feature Additions

### Phase A — Autonomous Bibliography-Healing Engine

**Goal**: Auto-correct, enrich, and reformat every bibliographic reference in a manuscript using AI-driven metadata resolution, then apply Vancouver-style renumbering to maintain citation integrity.

#### Backend Changes

| File | What Changed |
|---|---|
| `chicago_editor.py` | `_normalize_crossref_candidate()` — now emits full `authors_list` (family + given for every author) |
| `chicago_editor.py` | `_normalize_openalex_candidate()` — same `authors_list` extraction from authorships |
| `chicago_editor.py` | `_assess_online_metadata_match()` — return dict now includes `authors_list` for downstream formatting |
| `chicago_editor.py` | New `_format_healed_reference()` — author initials, title, journal/book tail, DOI appended per journal profile |
| `chicago_editor.py` | New `heal_bibliography(text, options, progress_callback)` — orchestrates full-pass: online validation → format → Vancouver renumber → inline citation remap |
| `webapp.py` | New `_heal_bibliography_task()` — runs healing inside the existing job-queue pipeline with progress callbacks and `healing_audit` record |
| `webapp.py` | `_build_route_dependencies()` exposes `heal_bibliography_task` |
| `routes/task_routes.py` | New `POST /api/tasks/<task_id>/heal-bibliography` — returns HTTP 202, queues background healing job, full audit trail |

#### API Contract

```
POST /api/tasks/{task_id}/heal-bibliography
Authorization: Bearer <token>
Content-Type: application/json

{ "options": { "online_reference_validation": true, "chicago_style": true } }

→ 202 Accepted
{ "success": true, "queued": true, "task_id": "...", "job": {...}, "task_run": {...} }
```

Poll `GET /api/tasks/{task_id}/process-status` for `SUCCEEDED` / `FAILED`.

---

### Phase B — Side-by-Side Interactive Split-Canvas Editor

**Goal**: Researchers review AI-corrected manuscripts next to the original in a synchronized split view, with HSL-pulsed highlights marking every healed reference.

#### Frontend Changes

| File | What Changed |
|---|---|
| `web/style.css` | ~300 lines: `.heal-bib-bar`, `.heal-bib-btn` (shimmer hover, spin animation), `.healing-progress-overlay` + shimmer bar, `.bib-healed` / `.bib-healed.doi-added` HSL-pulse, `.healing-status-banner` slide-down, `.pane-badge.healed` glow, `.scroll-sync-line`, `.ref-num-chip`, responsive collapse at 900 px |
| `web/app-heal-bibliography.js` | New 350-line UI module — MutationObserver on `#preview-text` injects heal bar into every compare-view render, submits `POST /heal-bibliography`, polls status, renders healed pane with DOI links, synchronized scroll with ratio-based lock |
| `web/fragments/script_bundle.html` | `app-heal-bibliography.js` loaded after `app-preview.js` |
| `web/pages/task-detail.js` | `bindEditorControls()` binds `#heal-bib-trigger` → `root.healBibliography.triggerHeal()` |
| `webapp.py` | `app-heal-bibliography.js` added to `REQUIRED_WEB_ASSETS` |

---

## Prior Release History

### v1.1.1 (Public Release — 2026-05-16)
- Core editing and DOCX preservation/export: Verified.
- Authenticated web mode and admin controls: Verified.
- Serper integration Phases 1–7: Complete.
- P0–P2.1 architecture slices (job queue, async processing, route extraction, module splits): Complete.
- Full quality gate: `Ran 159 tests in 311.896s ... OK`
- Versioning: centralized v1.1.1 verified across all packaging targets.

### Serper Integration (v1.1.1)
1. Phase 1: safe references-only Serper fallback (`9e22d83`)
2. Phase 2: runtime control + lookup metrics (`c7f2de2`)
3. Phase 3: independent UI/admin Serper fallback toggles (`7585079`)
4. Phase 4: corrections tab Serper diagnostics (`60b9d5d`)
5. Phase 5: shared cache hardening + admin diagnostics endpoint/UI (`d9c8e97`)
6. Phase 6: admin cache reset operation (`ca06dcf`)
7. Phase 7: diagnostics accuracy improvement for shared last-run lookup metrics

### Architecture Slices (v1.1.1)
- P0.1–P0.3: Route extraction, admin controls wired, assistant contract verified
- P1: `app-api.js`, `ManuscriptApi` bridge, route-specific frontend modules
- P1.6: `scripts/check_version_consistency.py` quality gate
- P1.7: `requirements.lock` + `pip-audit` weekly workflow
- P2.1: `job_queue.py` in-process queue, async processing + status polling

---

## Validation Snapshot

Last full quality gate (v1.1.1 baseline): `Ran 159 tests in 311.896s ... OK`

> **Note**: Unit + integration tests for `POST /heal-bibliography` and `heal_bibliography()` engine are planned as Phase C (next sprint). The API surface follows the same patterns already covered by existing `test_webapp_api.py` suites.

---

## Next Steps

| ID | Task | Priority |
|---|---|---|
| C | Add API + unit tests for bibliography healing engine | High |
| D.1 | Tag v1.2.0-dev and push | Normal |
| E.1 | Update `README.md` and `REPO_STATUS_ROADMAP.md` | Normal |
| F | Production deploy via Coolify with updated `docker-compose.coolify.yml` | Normal |

---

## Related Reference Docs

1. `README.md` (repo status + phased summary)
2. `REPO_STATUS_ROADMAP.md` (priorities and roadmap)
3. `WEEK8_COMPLETION.md` (packaging/release milestone context)
4. `docs/release/P0_QA_SIGNOFF_2026-05-16_LOCAL.md` (v1.1.1 sign-off)
