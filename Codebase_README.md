# Codebase README: Manuscript Editor (Full Technical + Non-Technical Guide)

## 1) What This Codebase/Application Is (Non-Technical)

Manuscript Editor is a professional copyediting system for `.txt` and `.docx` manuscripts.

It helps teams:
1. Improve language quality (spelling, sentence case, punctuation, style)
2. Enforce Chicago/Vancouver formatting behavior
3. Validate citation/reference consistency
4. Export clean and highlighted DOCX outputs for reviewer workflows

Primary user outcomes:
1. Faster editorial turnaround
2. More consistent manuscript formatting
3. Safer references through online validation checks
4. Clear auditability via highlighted (redline) exports

Current product stage:
1. `Active Development — v1.2.0-dev`
2. Core features and packaging pipelines (v1.1.1) were fully verified and signed off on 2026-05-23.

## 2) Who Uses It

1. Editors and copy editors: process manuscripts and export final outputs
2. QA/review teams: inspect highlighted DOCX and corrections reports
3. Admin users: manage runtime settings, provider validation, and user access
4. Ops/support: validate deployment health, telemetry, and release readiness

## 3) Core Features (Business View)

1. Authenticated web experience with role-based admin capabilities
2. Multi-provider AI support (Ollama/Gemini/OpenRouter/AgentRouter) + fallback rules engine
3. Autonomous Bibliography-Healing Engine (v1.2.0) with Crossref/OpenAlex/Serper remote lookup validation and Vancouver renumbering
4. Side-by-Side Interactive Split-Canvas Editor (v1.2.0) with ratio-locked scroll synchronization and HSL-pulsed reference corrections
5. Citation/reference validator with online lookup support
6. Reference-profile-aware formatting behavior
7. Compare view and grouped accept/reject correction workflow
8. Clean DOCX + highlighted DOCX export paths
9. Runtime and admin diagnostics

## 4) Technology Stack (Technical)

Backend:
1. Python 3
2. Bottle web server (`webapp.py`)
3. Business logic in `document_processor.py` and `chicago_editor.py`
4. `requests` for external provider and metadata lookups

Frontend:
1. Vanilla HTML/CSS/JS (modular scripts in `web/`)
2. Eel-compatible bridge adapted for web mode (`web/eel_web_bridge.js`)

Data/Storage:
1. App/user/task persistence via `app_store.py`
2. Task files under `DATA_DIR/tasks`
3. Runtime global settings persisted as app settings

Packaging/Release:
1. Windows installer pipeline artifacts
2. Ubuntu `.deb` pipeline artifacts
3. Release/QA templates and checklists in root markdown docs

## 5) High-Level Architecture

Main layers:
1. Presentation layer (`web/*.html`, `web/*.js`, `web/style.css`)
2. API/auth/admin layer (`webapp.py`)
3. Processing orchestrator (`document_processor.py`)
4. Rule engine + reference intelligence (`chicago_editor.py`)
5. Persistence (`app_store.py`, task file storage)

Two runtime modes exist:
1. Web mode (primary active production path): `webapp.py`
2. Legacy desktop/Eel path (`main.py`) still present for compatibility

## 6) End-to-End Logic Flow (How the Code Works)

### A) Auth + Session
1. User signs in via `/api/auth/google-login` (or local manual login when enabled)
2. Session cookie (`manuscript_editor_sid`) is issued
3. `require_auth` / `require_admin` guards protected APIs

### B) Upload and Task Creation
1. Text upload: `POST /api/tasks/upload-text`
2. DOCX upload: `POST /api/tasks/upload-docx`
3. Task metadata and source stored, task appears in history

### C) Processing
1. Frontend submits process request to `POST /api/tasks/<task_id>/process`
2. `webapp.py` merges user options with global runtime settings
3. `DocumentProcessor.process_text(...)` orchestrates:
   - rules pass via `ChicagoEditor.correct_all(...)`
   - optional AI pass + selection/fallback logic
   - audit reports, domain/profile reports, citation/reference reports

### D) Reference Validation Logic
1. Citation/reference report is built in `ChicagoEditor`
2. Online validation checks journal-style references
3. Lookup order:
   - Crossref DOI/search
   - Serper fallback (if enabled and configured)
   - OpenAlex fallback
4. Results are scored and labeled (`verified`, `likely_match`, `not_found`, `ambiguous`, `error`)

### E) Preview + Correction Groups
1. Backend returns corrected text + reports + redline HTML
2. Frontend renders tabs/views and corrections cards
3. Group accept/reject decisions can regenerate deterministic accepted text

### F) Export
1. Clean export path generates formatted corrected DOCX
2. Highlighted export path produces review-friendly redline DOCX
3. Task-bound download endpoints provide final file retrieval

## 7) Serper Integration Logic (Current Stage)

Implemented through Phase 5:
1. Phase 1: references-only safe fallback, strict query redaction, cache basics
2. Phase 2: runtime toggle + lookup metrics in payload
3. Phase 3: separate UI/admin Serper fallback controls
4. Phase 4: corrections-tab diagnostics chips
5. Phase 5: process-wide thread-safe cache + admin diagnostics endpoint/UI

Important safety behavior:
1. No full manuscript content is sent to Serper
2. URLs, emails, and raw DOI literals are stripped/redacted from query fragments
3. Diagnostics expose status/metrics, not secret values

## 8) API Surface Map (Important Groups)

Auth:
1. `/api/auth/config`
2. `/api/auth/google-login`
3. `/api/auth/local-login`
4. `/api/auth/me`
5. `/api/auth/logout`

Task and processing:
1. `/api/tasks`
2. `/api/tasks/upload-text`
3. `/api/tasks/upload-docx`
4. `/api/tasks/<id>/process`
5. `/api/tasks/<id>/heal-bibliography` (Phase A bibliography-healing async task)
6. `/api/tasks/<id>/apply-correction-group-decisions`
7. `/api/tasks/<id>/download`

Admin:
1. `/api/admin/users`
2. `/api/admin/users/<id>/status`
3. `/api/admin/audit-events`
4. `/api/admin/global-settings`
5. `/api/admin/validate-ai-provider`
6. `/api/admin/reference-validation-diagnostics`

Diagnostics/ops:
1. `/api/health`
2. `/api/runtime-telemetry`
3. `/api/runtime-telemetry/reset`

## 9) Codebase Map (Where to Read First)

1. `webapp.py`: auth/session, APIs, task lifecycle, admin APIs, bridge-compatible behavior, and healing task orchestration
2. `document_processor.py`: orchestration layer for editing, AI routing, reporting, DOCX generation
3. `chicago_editor.py`: core rules, reference normalization, citation/reference parsing, online validation, and bibliography-healing engine
4. `web/app-*.js`: frontend state, settings, admin interactions, rendering logic (including `web/app-heal-bibliography.js` for compare-view splits)
5. `tests/`: regression tests for rules, DOCX fidelity, and authenticated web API behavior

## 10) Non-Technical Operations Guide

For product/ops stakeholders:
1. If quality drifts, run the quality gate and inspect regression failures first
2. If AI provider complaints occur, use Admin API Validation and runtime diagnostics
3. If reference issues are reported, inspect corrections-tab online validation section and admin diagnostics
4. For releases, follow `RELEASE_CHECKLIST.md` and collect evidence via `QA_SIGNOFF_TEMPLATE.md`

## 11) Quality and Validation

Primary local gate:
1. `./scripts/run_quality_checks.sh`

This covers:
1. Python compile checks
2. Frontend syntax checks
3. Regression tests (rules, DOCX structure, API/auth flows, diagnostics behavior)

## 12) Security + Governance Highlights

1. Auth required for editing APIs
2. Admin-only routes are explicitly guarded
3. Non-admin runtime payloads do not expose server API keys
4. Serper diagnostics and telemetry avoid secret leakage

## 13) Current Risks and Next Work

Current main risk:
1. Lack of full unit and integration tests for the new `v1.2.0-dev` bibliography-healing engine API

Immediate roadmap focus:
1. P0: Add API + unit tests for bibliography healing engine (Phase C)
2. P1: Eliminate duplicate request/processing/export logic between main wrapper and web bridge
3. P2: Expand custom journal profiles beyond fixed Vancouver variants

## 14) Related Docs

1. `README.md` (primary operational README)
2. `LATEST_APPLICATION_STATUS.md` (latest stage handoff snapshot)
3. `REPO_STATUS_ROADMAP.md` (status + prioritized roadmap)
4. `MULTIPAGE_ARCHITECTURE.md` (frontend route/module architecture direction)
5. `WEEK8_COMPLETION.md` (packaging/release milestone completion report)
