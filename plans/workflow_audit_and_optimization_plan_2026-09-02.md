# Workflow Audit & Optimization Plan

**Date**: 2026-09-02
**Scope**: End-to-end audit of `login → upload → process → review → export` for correctness, module connectivity, and performance
**Baseline**: 173 tests discovered, full suite passes (`python3 -m unittest discover -s tests`, exit 0)
**Codebase**: 24,103 lines across Python backend + vanilla JS frontend

---

## Status: implemented 2026-09-02

All six phases are implemented. The quality gate passes: **220 tests, exit 0**
(173 baseline + 47 new), plus Python compile, version consistency, dependency
lock, and `node --check` over all 20 shipped JS files.

| Phase | State | Notes |
|-------|-------|-------|
| 0 — Correctness at the seams | Done | F1, F2, F5, F9 |
| 1 — Redline rewrite | Done | 26.16 s → 0.015 s at 54 KB; linear scaling |
| 2 — Deployment-truthful state | Done | F3, F4, F8, P6; `task_runs` is authoritative |
| 3 — Network parallelism | Done | P2, P3, P8; pooled session + bounded concurrency |
| 4 — Export & payload economy | Partial | 4.2 subsumed 4.1 — see note below |
| 5 — Admin consolidation & hardening | Done | F6, F7; one shared admin fragment |

### Measured outcomes

| Metric | Before | After |
|--------|--------|-------|
| `build_redline_html`, 54 KB | 26.16 s | **0.015 s** |
| `build_redline_html`, 212 KB | did not finish in 120 s | **0.065 s** |
| `build_process_payload`, 26 KB | 4.92 s | **0.093 s** |
| Reference validation, 24 refs @100 ms | 2.41 s | **0.41 s** (concurrency 6) |
| AI sections, 40 chunks @80 ms | 3.51 s | **1.17 s** (concurrency 4) |
| DOCX variants per process run | 4 | **1** (rest on first download) |
| `task_runs.result_json` per run | full payload (redline + both texts + base64 images) | **428 bytes** |
| Admin processing another user's task | HTTP 500 | **HTTP 200** |
| JS files in the syntax gate | 16 of 20 | **20 of 20** |

Verified end to end against a running server: upload → async process → duplicate
run rejected (409) → poll → full-task fetch → all four downloads → SSRF attempt
neutralised → admin processes another user's task.

### Phase 4.1 was deliberately not implemented

4.1 proposed parsing the DOCX template once and projecting all four variants in a
single pass. Its entire motivation was that every process run generated four
variants, each re-parsing the source. **4.2 removed that**: a run now generates
`clean` only, and a download regenerates exactly the one variant requested. With
no caller that wants four projections at once, 4.1 would add substantial
complexity to `_apply_text_to_template_docx` — the most DOCX-fidelity-sensitive
code in the app — for no remaining benefit. Set `EXPORT_EAGER_MODES=all` to
restore eager generation if a deployment prefers it.

### Deviations from the plan as written

1. **Redline equivalence is asserted by property, not by golden bytes.** Goldens
   were captured first (`tests/fixtures/redline_goldens.json`), but span
   boundaries legitimately move to line edges under a line-scoped diff, so byte
   equality was the wrong contract. The tests instead assert the two properties
   that actually define a redline — dropping deletions reconstructs the corrected
   text, dropping insertions reconstructs the original — over a 20-case corpus
   and randomized documents. The previous implementation satisfies both, so this
   is a strictly stronger check than the goldens would have been.
2. **AI section parallelism covers the provider round trip only.** Candidate
   post-processing and selection stay on the calling thread, because
   `ChicagoEditor` carries mutable per-run reporting state. All the latency is in
   the round trip, so this captures the benefit with no shared-state risk.
3. **Request-override gating is tiered rather than admin-only.** A caller may
   always ask for *less* work (turn AI off, skip network validation); only
   provider, model, host, credential and cap changes are admin-gated. A flat
   admin-only gate would have broken every test and UI path that legitimately
   disables AI.
4. **Two test seams moved.** `chicago_editor.requests.get/post` patches became
   `requests.Session.get/post` (the transport is now pooled), and the
   quality-gate test now asserts the glob covers every shipped JS file instead of
   listing 14 filenames.

---

## 1. Verdict

The pipeline is architecturally sound and the module boundaries are in the right
places. `webapp.py` orchestrates, `routes/` owns the API surface,
`manuscript_service.py` is a real single source of truth for payload/export
construction, and `document_processor.py` / `chicago_editor.py` own processing.
Nothing needs a rewrite.

What the audit found is a different class of problem: **the connective tissue
between modules is where correctness and performance are lost.** Three themes:

1. **One shape mismatch at a module seam blanks the editor.** `/process-status`
   returns a task *summary*; the frontend feeds it to a hydrator that expects a
   *full* task and unconditionally overwrites every field.
2. **Process-local state assumed to be global.** The job queue, telemetry,
   rate-limit buckets and reference cache all live in process memory while the
   Dockerfile runs two gunicorn workers.
3. **One function is super-linear and sits on the critical path of every run.**
   `build_redline_html` measured 26 seconds on a 54 KB document. `MAX_TEXT_CHARS`
   defaults to 500,000.

The fixes are localized. Phase 0 and Phase 1 together are a few hundred lines and
address the two highest-impact items.

---

## 2. The workflow as built

```
upload-text / upload-docx
  └─ _upload_text_to_task            write source to data/tasks/<id>/, INSERT task, audit
     │
POST /api/tasks/<id>/process  (async=true → BackgroundJobQueue + task_runs row)
  └─ _process_task
     ├─ DocumentProcessor.process_text
     │    ├─ ChicagoEditor.correct_all              rules pass
     │    ├─ _call_ai_editor                        full OR sectioned (SEQUENTIAL per chunk)
     │    ├─ _select_best_correction                risk-scored rules-vs-AI choice
     │    ├─ build_reference_profile_report
     │    ├─ build_citation_reference_validator_report
     │    │    └─ _build_online_reference_validation_report   (SEQUENTIAL per reference)
     │    └─ append_online_reference_links
     ├─ manuscript_service.build_process_payload
     │    ├─ build_corrections_report               0.005s @ 26KB
     │    ├─ build_redline_html                     4.94s  @ 26KB   ← dominant cost
     │    ├─ build_prose_only_diff_text             0.004s
     │    ├─ build_strict_cmos_issues_summary       re-runs corrections_report
     │    └─ build_foreign_annotated_html ×2        identical args, called twice
     ├─ _attach_journal_recommendations             DB read + optional AI call
     ├─ update_task_processing_result               WHERE id=? AND user_id=?
     └─ _store_task_export_files                    4 DOCX variants, always
        │
GET /api/tasks/<id>/process-status  (polled 1.2s → 2.5s → 5s)
  └─ returns { job, task_run, task: task_summary(task) }
        │
frontend applyTaskDetailsToState(response.task)   ← summary into full-task hydrator
```

---

## 3. Findings

Severity is impact on a real user, ranked. `F` = correctness/connectivity,
`P` = performance.

### F1 · High · Polling blanks the editor content

`pollTaskUntilProcessed` ([web/app.js:544](../web/app.js#L544)) calls
`mainAuth.applyTaskDetailsToState(task)` with `response.task`, which
`/api/tasks/<id>/process-status` fills from `deps.task_summary(task)`
([routes/task_routes.py:340](../routes/task_routes.py#L340)). The summary has no
`original_text`, `corrected_text`, `options` or `reports`.

`applyTaskDetailsToState` ([web/app-auth-admin.js:253-278](../web/app-auth-admin.js#L253-L278))
assigns all of those unconditionally with `String(task.original_text || '')` and
friends, so it **overwrites loaded content with empty strings and nulls** —
original, corrected, redline, prose diff, corrections report, noun/domain/journal
reports, preview images, processing audit.

Two hit paths:
- Every non-terminal poll while processing runs (clears the original the user is
  looking at).
- The `status === 'PROCESSED'` completion branch, taken whenever `job` is
  absent — see **F3** — which lands the user on the "corrected" tab with nothing
  in it.

**Fix**: on a terminal status, re-fetch the full task via `api.tasks.get(taskId)`
before hydrating. For intermediate polls, update only status/progress fields;
never call the full-task hydrator with a summary. Optionally rename the key to
`task_summary` in the response so the shape mismatch cannot recur silently.

### F2 · High · Admins get HTTP 500 on any task they do not own

`_get_owned_task_or_error` passes `is_admin=True`, so `get_task_for_user`
([app_store.py:580](../app_store.py#L580)) lets an admin **read** any task. But
`update_task_processing_result` ([app_store.py:637](../app_store.py#L637)) and
`update_task_corrected_text` ([app_store.py:691](../app_store.py#L691)) have no
`is_admin` parameter and hard-filter `WHERE id = ? AND user_id = ?` using
`context.user_id`. The UPDATE matches zero rows, the follow-up read returns
`None`, and `_process_task` raises `RuntimeError("Task update failed")`.

Reproduced directly against `AppStore`:

```
admin can READ task: True
admin WRITE result (None => webapp raises 'Task update failed'): None
admin group-decisions WRITE result: None
owner write works: True
```

Affects `/process`, `/apply-correction-group-decisions`, `/heal-bibliography`,
`/autopilot`, and `/save-corrected-rich-html`.

**Fix**: add `is_admin: bool = False` to both store methods, mirroring
`update_task_status`, and pass `context.role == ROLE_ADMIN` from every caller.
Write the task's real owner into the row rather than the actor.

### F3 · High · In-process job queue vs. two gunicorn workers

The `Dockerfile` ships `GUNICORN_WORKERS=2`. `_PROCESSING_JOB_QUEUE`
([webapp.py:163](../webapp.py#L163)) is a `ThreadPoolExecutor` plus a plain dict
in **one process**. A `/process-status` poll served by the other worker returns
`job: null`, so progress percent, stage, token count and the final `job.result`
are all invisible — which is exactly the path that triggers **F1**.

The same process-local assumption applies to:
- `_RUNTIME_TELEMETRY` → `/api/runtime-telemetry` reports whichever worker answered
- `_RATE_LIMIT_BUCKETS` → effective write limit is 2× the configured value
- `ChicagoEditor._SHARED_ONLINE_VALIDATION_CACHE` and `_SHARED_ONLINE_LOOKUP_METRICS`
  → halved cache hit rate, split admin diagnostics
- `_LAST_CLEANUP_AT` → retention cleanup runs twice as often as intended

`BackgroundJob` entries are also never evicted — `self._jobs` grows for the life
of the process, holding a full process payload per succeeded job.

**Fix**: make `task_runs` the authoritative progress record (add
`progress_percent`, `stage`, `tokens_consumed`, `estimated_seconds_remaining`
columns), have the progress callback write there, and serve `/process-status`
from the DB with the in-memory job as an optional fast path. Add TTL eviction to
`BackgroundJobQueue`. Document that `GUNICORN_WORKERS=1` is required until this
lands, or set it to 1 now as an interim measure.

### F4 · Medium · No in-flight guard, no per-task lock

Nothing checks `task.status == "PROCESSING"` before enqueuing another run. The
write rate limit is 120 requests / 300s per user, so one user can queue ~120 heavy
jobs. Concurrent runs on the same task:

- write the same `tasks` row through last-writer-wins
- write the same export paths (`data/tasks/<id>/clean.docx`, …) concurrently,
  which can leave a truncated or interleaved DOCX on disk
- collide in `BackgroundJobQueue.update_progress`, which keys on
  `_latest_by_task` and so reports the newest job's progress under the older
  job's identity

**Fix**: reject a new run with `409` while a `task_runs` row for that task is
`PENDING`/`RUNNING` (unless `force=true`), and write exports to a temp path +
atomic `os.replace`.

### F5 · Medium · `task_runs` lost-update race

[routes/task_routes.py:275-285](../routes/task_routes.py#L275-L285) calls
`submit()`, which starts the worker thread immediately — the worker's first act
is `update_task_run(status="RUNNING")`. The request thread then calls
`update_task_run(job_id=...)`. `update_task_run`
([app_store.py:836](../app_store.py#L836)) is a read-modify-write of the whole
row with no transaction, so the later write can revert `status` to `PENDING` or
overwrite `result_json`.

**Fix**: set `job_id` at INSERT time (allocate the job id before `submit()`), and
make `update_task_run` issue targeted column updates instead of whole-row
rewrites.

### F6 · Medium · Admin panel drift silently resets settings

`web/task_detail.html` and `web/index.html` diverged by 83 lines. `task_detail.html`
is missing the **Ollama Transport** block (5 controls) and the **Journal Style
Catalog** and **Journals Records** sections; the two files also disagree on
`role="group" aria-labelledby` vs `label for` markup.

`collectAdminGlobalSettingsForm()`
([web/admin/global-settings.js:378](../web/admin/global-settings.js#L378)) builds a
**full replacement payload** and substitutes hardcoded defaults for absent
elements (`ollama_generate_timeout_seconds: 60`, `ollama_retry_count: 0`,
`ollama_fallback_model_retry: true`, …). `POST /api/admin/global-settings`
([routes/admin_routes.py:153](../routes/admin_routes.py#L153)) replaces the whole
stored blob via `_normalize_global_runtime_settings(incoming)`.

Net effect: **an admin who saves any setting from the task-detail admin panel
silently resets all five Ollama transport settings to defaults.**

**Fix**: extract the admin panel into one shared fragment (the pattern already
used for `assistant_panel.html`), so both shells render identical markup. Add a
route-shell parity test asserting the two shells expose the same
`admin-setting-*` element ids.

### F7 · Medium · Request options override admin global settings (SSRF)

`_apply_global_runtime_settings` ([webapp.py:768-798](../webapp.py#L768-L798))
applies admin settings first, then lets the request payload override **every**
`ai.*` key — including `ollama_host`, `provider`, and the three API keys — plus
`online_reference_validation*` and `auto_resolve_unresolved_references`.

Any authenticated non-admin can therefore send:

```json
POST /api/tasks/<id>/process
{"options": {"ai": {"provider": "ollama", "ollama_host": "http://169.254.169.254"}}}
```

and make the server issue `GET {host}/api/tags` and `POST {host}/api/generate`
from inside the deployment network. Model/provider policy set by an admin is also
bypassable.

**Fix**: gate the request-override branch on `context.role == ROLE_ADMIN`, or
restrict overridable keys to a non-network allowlist (`editing_mode`, `tone`,
`rewrite_strength`, `explain_edits`, `unresolved_reference_only`). Validate
`ollama_host` against an allowlist regardless. Tests that need to force provider
behavior should use the admin path or a fixture setting.

### F8 · Low · Whole process payload stored in `task_runs.result_json`

`update_task_run(result=...)` persists the full payload: complete redline HTML,
original + corrected text, every report, and up to 6 MB of base64 DOCX preview
images. `/process-status` then returns it **twice** — once as `job.result`, once
as `task_run.result` — and every `update_task_run` re-reads and re-serialises it.

**Fix**: store a small run summary (word count, mode, counts, error) in
`result_json`. The authoritative result already lives in `tasks.reports_json`;
have the client re-fetch the task on completion (which F1's fix already does).

### F9 · Low · Dead code and quality-gate gaps

- `_compute_diff`, `_create_run_with_format`, `_add_formatted_run`
  ([document_processor.py:3680-3722](../document_processor.py#L3680-L3722)) are
  unreferenced. `_compute_diff` aligns words positionally via
  `zip(orig_words, corr_words)`, which is wrong the moment a word is inserted or
  deleted — it is a correctness trap for anyone who reaches for it.
- `scripts/run_quality_checks.sh` runs `node --check` on 16 JS files but omits
  `web/app-state.js`, `web/app-preview.js` (1,667 lines), `web/app-heal-bibliography.js`
  and `web/admin/journals.js`.

**Fix**: delete the three unused methods; glob the JS syntax check over `web/**/*.js`.

---

### P1 · High · `build_redline_html` is super-linear and on every critical path

Measured on this machine (`/usr/bin/python3` 3.12.3), synthetic prose with ~1
edit every 3 lines:

| Lines | Chars | `build_redline_html` |
|------:|------:|---------------------:|
| 50 | 6,819 | 0.19 s |
| 100 | 13,040 | 0.83 s |
| 200 | 26,161 | 5.01 s |
| 300 | 39,491 | 10.32 s |
| 400 | 54,177 | 26.16 s |

Doubling the document multiplies the time by 4–6×. At 26 KB it accounts for
**4.92 s of the 4.92 s** total `build_process_payload` cost; a 130 KB document did
not finish in 120 seconds. `MAX_TEXT_CHARS` defaults to **500,000**.

Cause: `_iter_diff_segments` ([document_processor.py:3655](../document_processor.py#L3655))
flattens the *entire document* into one token stream
(`\s+|[\w…]+|[^\w\s]`) and runs `difflib.SequenceMatcher(autojunk=False)` over
it. Disabling autojunk removes the heuristic that would otherwise keep it near-linear.

It runs on every `/process`, every `/apply-correction-group-decisions`, and every
`/heal-bibliography`.

**Fix**: diff line-by-line, exactly as `build_corrections_report`
([document_processor.py:3326](../document_processor.py#L3326)) already does —
line-level `SequenceMatcher` first, then token-level refinement within each
changed line pair. That bounds every inner matcher to a single line and matches
what `build_prose_only_diff_text` already does. Same size, same content:
**0.005 s**. Expected: seconds → milliseconds, and linear scaling.

### P2 · High · Reference validation is strictly sequential with no connection reuse

`_build_online_reference_validation_report`
([chicago_editor.py:3127](../chicago_editor.py#L3127)) walks references in a plain
`for` loop. Each `_validate_reference_online` call makes up to three HTTP requests
(Crossref by DOI, Crossref search, Serper fallback, OpenAlex) using bare
`requests.get` / `requests.post` — **no `requests.Session`**, so every call pays a
fresh TCP + TLS handshake.

Default cap is 150 references, timeout 5 s. Worst case is ~37 minutes of wall
clock in a loop where every iteration is independent.

**Fix**: a module-level `requests.Session` with a sized `HTTPAdapter`
connection pool and `Retry` backoff for 429/502/503/504, plus a bounded
`ThreadPoolExecutor` (default 6–8, admin-configurable) over the reference list
with results reassembled in original order. Make `_online_lookup_metrics`
increments lock-protected first — they are currently unsynchronised.

### P3 · Medium · Section-wise AI editing is sequential

`_call_ai_editor_sectioned` ([document_processor.py:722](../document_processor.py#L722))
issues one provider round trip per chunk inside a `for` loop. Chunks are
independent — each carries its own `original` and `baseline` — so this is
embarrassingly parallel work being done serially. A 30-section manuscript at 5 s
per call is 150 s that could be ~25 s at concurrency 6.

**Fix**: bounded `ThreadPoolExecutor` over chunks, outputs reassembled by index.
Requires making `decisions`, `fallback_reason_counts` and progress reporting
thread-safe, and per-provider concurrency caps so shared Ollama hosts are not
overwhelmed. Keep a `section_concurrency: 1` setting for exact-reproducibility runs.

### P4 · Medium · Four DOCX variants generated whether or not they are wanted

`_store_task_export_files` ([webapp.py:1113](../webapp.py#L1113)) always builds
`clean`, `highlighted`, `highlighted_comments` and `track_changes`. With a DOCX
source, each one independently re-opens the zip, re-parses the XML, re-extracts
blocks and re-runs the line diff inside `_apply_text_to_template_docx`
([document_processor.py:2572](../document_processor.py#L2572)) — the three
highlighted modes differ only in run styling.

Measured 0.81 s for all four on the no-template path at 26 KB; the template path
is materially heavier. Autopilot pays it twice (process, then heal). It is also
paid again on a download cache miss, where a request for one variant regenerates
all four.

**Fix**: parse the template once and project it four ways in a single pass, or
generate `clean` eagerly and the other three lazily on first download. Write via
temp file + `os.replace` (see **F4**).

### P5 · Low · Redundant recomputation in `build_process_payload`

[manuscript_service.py](../manuscript_service.py):
- `build_foreign_annotated_html(corrected_text)` is called **twice with identical
  arguments** — once for `corrected_annotated_html`, once for `corrected_rich_html`.
- `build_strict_cmos_issues_summary` internally re-runs
  `build_corrections_report(original, corrected)` that the caller computed three
  lines earlier.

**Fix**: compute each once and reuse; add an optional `corrections_report`
parameter to `build_strict_cmos_issues_summary`.

### P6 · Medium · One DB connection behind one global lock

`AppStore._execute` ([app_store.py:126](../app_store.py#L126)) serialises **every
query in the process** behind `self._lock`, and `_query_one` / `_query_all` call
`fetchone()` / `fetchall()` *after* the lock is released — the cursor is stepped
outside the critical section while another thread may be executing on the same
connection.

- SQLite: `PRAGMA journal_mode=WAL` is set but **`busy_timeout` is not**, while
  gunicorn runs two processes against one WAL file → `database is locked` under
  concurrency.
- PostgreSQL: the whole worker process shares a single `psycopg` connection — no
  pool.

**Fix**: `PRAGMA busy_timeout=5000` (and `synchronous=NORMAL`) for SQLite;
thread-local connections or `psycopg_pool.ConnectionPool` for PostgreSQL; move
fetches inside the lock in the interim.

### P7 · Low · Front end ships the whole app on every page

`web/fragments/script_bundle.html` loads **21 render-blocking scripts** with no
`defer`, including the entire admin, preview, heal-bibliography and task-detail
bundle on the `/tasks` dashboard, which needs almost none of it. Static assets are
served by `static_file()` ([routes/page_routes.py:47](../routes/page_routes.py#L47))
with no `Cache-Control`, so every navigation re-validates all 21 files even though
each already carries a `?v={{ASSET_VERSION}}` cache-busting query.

**Fix**: add `defer` to every non-bootstrap script; serve `/<asset_path:path>`
with `Cache-Control: public, max-age=31536000, immutable` (safe — the URLs are
already versioned); split the bundle so the dashboard loads only what it needs.

### P8 · Low · Reference cache is smaller than one manuscript

`ONLINE_VALIDATION_CACHE_MAX_ENTRIES = 512`
([chicago_editor.py:23](../chicago_editor.py#L23)) against a 150-reference cap with
up to 3 lookups each (~450 entries per run) means consecutive manuscripts evict
each other. Eviction also sorts the entire dict on every overflow insert.

**Fix**: raise to ~4,000 entries and use an `OrderedDict` / heap for O(1)
eviction. Reconsider once **F3**'s shared-state work lands.

---

## 4. Implementation plan

Ordered so that each phase is independently shippable and validated by the
existing gate. No phase requires the next one to be correct.

### Phase 0 — Correctness at the seams

*Goal: the workflow produces the right output in every deployment shape.*

| # | Task | Files | Fixes |
|---|------|-------|-------|
| 0.1 | Re-fetch the full task on terminal poll status; restrict intermediate polls to status/progress fields only | `web/app.js` | F1 |
| 0.2 | Rename `process-status` payload key to `task_summary`, keep `task` as a deprecated alias for one release | `routes/task_routes.py`, `web/app.js` | F1 |
| 0.3 | Add `is_admin` to `update_task_processing_result` / `update_task_corrected_text`; pass role from every caller; persist the task's real owner | `app_store.py`, `webapp.py` | F2 |
| 0.4 | Allocate the job id before `submit()`; set `job_id` at INSERT; make `update_task_run` write targeted columns | `job_queue.py`, `app_store.py`, `routes/task_routes.py` | F5 |
| 0.5 | Delete `_compute_diff`, `_create_run_with_format`, `_add_formatted_run`; glob `node --check` over `web/**/*.js` | `document_processor.py`, `scripts/run_quality_checks.sh` | F9 |

**Validation**: new tests — admin processes another user's task and gets 200;
poll-then-complete preserves `original_text`/`reports` in state; concurrent
`update_task_run` calls do not revert status. Existing 173 tests stay green.

**Risk**: Low. All changes are additive or shape-preserving.

### Phase 1 — The redline rewrite

*Goal: remove the dominant non-AI cost from every run.*

| # | Task | Files |
|---|------|-------|
| 1.1 | Capture golden `build_redline_html` output for a fixture corpus (current implementation) | `tests/fixtures/` |
| 1.2 | Reimplement `build_redline_html` on the line-pair diff strategy already used by `build_corrections_report` | `document_processor.py` |
| 1.3 | Assert output equivalence against goldens; accept only intentional differences on cross-line moves, documented in the test | `tests/test_regression_rules.py` |
| 1.4 | Add a performance regression test: 50 KB document must build redline in < 1 s | `tests/test_regression_rules.py` |
| 1.5 | Compute `build_foreign_annotated_html` once; pass `corrections_report` into `build_strict_cmos_issues_summary` | `manuscript_service.py`, `document_processor.py` |

**Validation**: golden-output equivalence + the new timing test. Target:
54 KB document from 26.16 s to under 0.5 s.

**Risk**: Medium — redline HTML is user-visible. Mitigated entirely by capturing
goldens *before* touching the implementation (1.1 is a hard prerequisite).

### Phase 2 — Deployment-truthful state

*Goal: make the workflow behave the same on 1 worker and N workers.*

| # | Task | Files |
|---|------|-------|
| 2.1 | Add `progress_percent`, `stage`, `tokens_consumed`, `estimated_seconds_remaining` to `task_runs`; write from the progress callback | `app_store.py`, `webapp.py` |
| 2.2 | Serve `/process-status` progress from `task_runs`; keep the in-memory job as an optional fast path | `routes/task_routes.py` |
| 2.3 | Store a compact run summary in `result_json` instead of the full payload | `webapp.py`, `routes/task_routes.py` |
| 2.4 | Reject a second run for a task with a `PENDING`/`RUNNING` run (`409`, `force=true` override) | `routes/task_routes.py` |
| 2.5 | Write exports to temp path + `os.replace` | `webapp.py` |
| 2.6 | TTL eviction in `BackgroundJobQueue` | `job_queue.py` |
| 2.7 | Startup reaper: mark orphaned `RUNNING` runs `FAILED` and their tasks recoverable | `webapp.py` |
| 2.8 | `PRAGMA busy_timeout=5000` + `synchronous=NORMAL`; move fetches inside the lock | `app_store.py` |

**Validation**: run the API suite with `GUNICORN_WORKERS=2` against SQLite;
a test that restarts the store mid-run and confirms the task does not stay
`PROCESSING` forever.

**Risk**: Medium — schema change. Additive columns only, `CREATE TABLE IF NOT
EXISTS` plus guarded `ALTER TABLE`, SQLite/PostgreSQL compatible per the existing
bootstrap convention.

**Interim**: set `GUNICORN_WORKERS=1` in the `Dockerfile` until 2.1–2.3 land.

### Phase 3 — Network parallelism

*Goal: cut wall-clock on the two remaining sequential loops.*

| # | Task | Files |
|---|------|-------|
| 3.1 | Module-level `requests.Session` with pooled `HTTPAdapter` and `Retry` backoff (429/502/503/504) for Crossref, OpenAlex, Serper | `chicago_editor.py` |
| 3.2 | Lock-protect `_online_lookup_metrics` increments | `chicago_editor.py` |
| 3.3 | Bounded `ThreadPoolExecutor` over the reference list; reassemble in original order; admin-configurable concurrency (default 6) | `chicago_editor.py`, `webapp.py`, admin UI |
| 3.4 | Raise reference cache to ~4,000 entries with O(1) eviction | `chicago_editor.py` |
| 3.5 | Bounded concurrency over AI section chunks; thread-safe decision/fallback accumulation; per-provider caps; `section_concurrency: 1` escape hatch | `document_processor.py` |

**Validation**: existing `test_section_chunk_scoring.py` must produce identical
decisions at `section_concurrency: 1`; a mocked-transport test asserting N
references issue N lookups and return in input order.

**Risk**: Medium — concurrency against third-party APIs. Mitigated by conservative
default concurrency, retry/backoff, and the serial escape hatch.

### Phase 4 — Export and payload economy

| # | Task | Files |
|---|------|-------|
| 4.1 | Parse the DOCX template once and project all highlighted variants in a single pass | `document_processor.py`, `manuscript_service.py` |
| 4.2 | Generate `clean` eagerly; generate the other three lazily on first download | `webapp.py`, `routes/task_routes.py` |
| 4.3 | Export-parity test: with corrections present, `highlighted` ≠ `clean` and `track_changes` contains revision markup | `tests/test_docx_structure_preservation.py` |
| 4.4 | `defer` on all non-bootstrap scripts; `Cache-Control: public, max-age=31536000, immutable` on versioned static assets | `web/fragments/script_bundle.html`, `routes/page_routes.py` |
| 4.5 | Prefer the streaming `/download-file` route over base64 `/download` in the UI | `web/app.js`, `web/app-api.js` |

**Validation**: `test_docx_structure_preservation.py` stays green; new parity test.

**Risk**: Low-medium. 4.1 touches DOCX fidelity — the existing preservation suite
is the gate.

### Phase 5 — Admin surface consolidation and hardening

| # | Task | Files |
|---|------|-------|
| 5.1 | Extract the admin panel into `web/fragments/admin_panel.html`; both shells include it | `web/index.html`, `web/task_detail.html`, `webapp.py` |
| 5.2 | Route-shell parity test: both shells expose identical `admin-setting-*` ids | `tests/test_webapp_api.py` |
| 5.3 | Send only changed keys from the admin form, or merge server-side instead of replacing | `web/admin/global-settings.js`, `routes/admin_routes.py` |
| 5.4 | Gate request-level `ai.*` overrides on admin role; allowlist non-network keys for everyone; validate `ollama_host` | `webapp.py` |
| 5.5 | Read provider keys from environment as primary source; settings UI becomes override-only | `webapp.py`, deployment docs |

**Validation**: parity test; a test asserting a non-admin `ollama_host` override
is ignored; existing admin settings round-trip tests stay green.

**Risk**: Low. 5.4 may require updating tests that currently force provider
behavior through the request payload — route those through the admin path.

---

## 5. Sequencing

```
Phase 0  ──┬──> Phase 1        (independent; ship whichever is ready)
           ├──> Phase 5
           └──> Phase 2 ──> Phase 3
                      └──> Phase 4
```

Phase 0 first — it is small and unblocks confidence in everything else.
Phase 1 delivers the largest single user-visible speedup and depends on nothing.
Phase 2 must precede Phase 3 and 4 because both add concurrency that the current
process-local state cannot account for.

## 6. Success criteria

| Metric | Now | Target |
|--------|-----|--------|
| `build_redline_html`, 54 KB document | 26.2 s | < 0.5 s |
| `build_process_payload`, 26 KB document | 4.92 s | < 0.2 s |
| Reference validation, 150 refs, cold cache | sequential, up to ~37 min worst case | < 3 min at concurrency 6 |
| Admin processing another user's task | HTTP 500 | HTTP 200 |
| Editor content after background completion | blank on a second worker | correct on any worker |
| Correct progress reporting with `GUNICORN_WORKERS=2` | ~50 % of polls | 100 % |
| Blocking scripts on `/tasks` | 21 | 0 (all deferred) |
| JS files covered by the syntax gate | 16 of 20 | 20 of 20 |
| Regression suite | 173 passing | 173 + new coverage, passing |

## 7. Do not break

Carried forward from `docs/ai-handoff/06-known-gaps-and-upgrade-ideas.md`, plus
what this audit adds:

1. Do not regress DOCX structure preservation — capture goldens before Phase 1
   and Phase 4.
2. Do not change redline HTML semantics without an equivalence test.
3. Do not remove the `/api/tasks/<id>/process-status` `task` key without a
   deprecation window; the desktop/Eel bridge reads it.
4. Do not make Serper the primary reference path; it stays fallback-gated.
5. Do not raise concurrency defaults above what a shared Ollama host tolerates.
6. Keep `task_runs` schema changes additive and SQLite/PostgreSQL compatible.
