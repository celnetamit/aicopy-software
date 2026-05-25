# Manuscript Editor

Professional AI-powered copy editing application following The Chicago Manual of Style.

Need a very simple version of instructions?
See [KID_GUIDE.md](KID_GUIDE.md).

## Features

- **AI-Powered Editing**: Uses local Ollama AI for intelligent context-aware corrections
- **Autonomous Bibliography Healing (v1.2.0)**: AI-driven reference enrichment (via Crossref/OpenAlex/Serper metadata verification), compliant reference formatting, Vancouver citation remapping, and full audit logs
- **Interactive Split-Canvas Editor (v1.2.0)**: Side-by-side synchronized comparison view with ratio-locked scroll sync and HSL-pulsed highlights for healed bibliographic items
- **Secure Access (Auth Upgrade)**: Google Sign-In only with domain allowlist enforcement
- **Role Hierarchy (v1)**: `ADMIN` and `USER` roles with admin monitoring capabilities
- **Task Dashboard**: Each signed-in user gets task history with downloadable outputs
- **Admin Activity Tracking**: Admin panel for user status control and audit timeline
- **Multi-Provider AI Settings**: Switch between local Ollama and Google Gemini from the UI
- **First-Run Setup Wizard**: Guided setup text for API keys and Ollama host on first launch (fully complete and verified)
- **Chicago Style Compliance**: Applies The Chicago Manual of Style formatting rules
- **Journal Profiles (Week 5)**: Profile-aware Vancouver presets for initials punctuation, title case, and journal abbreviation rules
- **Spelling Corrections**: Fixes misspellings using American spellings
- **Sentence Case Fixes**: Corrects capitalization (first word, days, months, proper nouns)
- **Punctuation Refinements**: Fixes spacing, quotes, ellipsis formatting
- **Four Premium Export Formats**:
  - **Clean DOCX**: Standard copyedited document ready for publication
  - **Visual Redline DOCX**: Inline red/strikethrough deletions and green/underline insertions
  - **Interactive Comments DOCX**: Clean text with premium side-bubble comments explaining copyediting decisions
  - **MS Word Tracked Changes DOCX**: Native Word `w:ins`/`w:del` tracked changes allowing inline Accept/Reject review with native comments

## Requirements

- Python 3.8+
- Ollama (optional, for AI-enhanced editing)
- Google OAuth Client ID for web login (`GOOGLE_CLIENT_ID`)
- PostgreSQL recommended for production (`DATABASE_URL`)

### Python Dependencies

```bash
pip install -r requirements.lock
```

`requirements.lock` is the reproducible install file for local release checks, Docker, and packaged builds. `requirements.txt` remains the editable dependency intent file. It includes `setuptools` because `eel` imports `pkg_resources` on some Python and Windows setups, and it pins `bottle` directly because the deployable web server imports it outside the Eel desktop wrapper.

Upgrade policy:
1. Edit `requirements.txt` first when dependency intent changes.
2. Refresh `requirements.lock` in a clean Python 3.12 environment.
3. Run `python3 scripts/check_dependency_lock.py`.
4. Run `./scripts/run_quality_checks.sh`.

### Ollama Setup (Optional)

For AI-enhanced editing, install Ollama and download the model:

```bash
# Install Ollama (Linux/macOS)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the llama3.2 model
ollama pull llama3.2
```

The application will still work without Ollama using built-in rule-based editing.

## Installation

1. Clone or download this repository
2. Install Python dependencies
3. (Optional) Install and configure Ollama
4. Copy `.env.example` to `.env` and set deployment values (`GOOGLE_CLIENT_ID`, `DATABASE_URL`, provider keys as needed)

## Quality Checks (Week 1 Baseline)

Run the full local quality gate:

```bash
./scripts/run_quality_checks.sh
```

This runs:
1. Python compile checks
2. Frontend JavaScript syntax check
3. Regression tests (citations, references, superscripts, URL/DOI protection, redline)

## Runtime Telemetry (Week 2)

Backend now tracks save/export reliability counters:
1. `export_attempts`, `export_successes`, `export_failures`
2. `save_attempts`, `save_successes`, `save_failures`, `save_fallback_used`
3. `errors_by_code` map

Eel exposed helpers:
1. `get_runtime_telemetry()`
2. `reset_runtime_telemetry()`

Save/export failures also include stable `error_code` values for user-facing handling.

## Online Reference Validation (Phase 1 Serper)

Reference validation remains references-only (journal entries) and can use Serper as a safe fallback.

1. Keep `online_reference_validation` enabled in app settings/options.
2. Set `SERPER_API_KEY` in the runtime environment to enable Serper fallback.
3. If `SERPER_API_KEY` is missing, Crossref/OpenAlex validation continues and Serper stays disabled.

Safety controls in this phase:
1. Redacted lookup query building (no full manuscript text, URLs, emails, or raw DOI literals sent to Serper).
2. In-memory TTL caching for remote lookup results to reduce repeated external calls.

Phase 2 runtime controls:
1. `online_reference_serper_fallback` (processing/global runtime option, default `true`) controls whether Serper is used as a fallback when `SERPER_API_KEY` exists.
2. Online validation payload now includes:
   - `serper_requested`, `serper_available`, `serper_enabled`
   - `lookup_metrics` (`cache_hits`, `cache_misses`, `crossref_requests`, `openalex_requests`, `serper_requests`, `serper_cache_hits`)

Phase 3+4 UI/admin surfacing:
1. Task option and Admin global setting each include an independent `Serper Fallback` toggle wired to `online_reference_serper_fallback`.
2. Corrections tab `Online Reference Validation` card now displays Serper flags (`requested`, `available`, `enabled`) and lookup metrics for quick diagnostics.

Phase 5 observability + cache hardening:
1. Online reference lookup cache is process-wide and thread-safe, improving cache reuse across processing jobs in the web runtime.
2. Admin Dashboard includes `Reference Validation Diagnostics` with safe JSON diagnostics from `/api/admin/reference-validation-diagnostics`.
3. Diagnostics include Serper configured/effective state, lookup limits, cache health, and last-run lookup metrics without exposing secret values.

Phase 6 diagnostics operations:
1. Admin can reset shared reference-validation cache without restarting runtime.
2. New admin endpoint: `POST /api/admin/reference-validation-diagnostics/reset`.
3. Admin Diagnostics UI now includes `Reset Cache` action and reports removed cache-entry count.

Phase 7 diagnostics accuracy:
1. Online lookup metrics are now published as process-shared `last run` diagnostics after each validation run.
2. Admin diagnostics payload now includes `lookup_metrics_last_run_at` timestamp.
3. This ensures admin diagnostics reflects real recent validation activity (not just a fresh instance snapshot).

## Week 3: Section Quality Audit

For long manuscripts using section-wise AI mode, backend now emits per-section quality decisions:
1. decision per section: `accepted` or `fallback`
2. risk scores and reasons (`baseline_score`, `ai_score`, `decision_reason`)
3. section boundaries (`line_start`, `line_end`)

This appears in process response as:
1. `processing_audit.mode`
2. `processing_audit.sections`
3. `processing_audit.summary`

## Week 4: Consistency Scoring + UI Summary Card

Refinements added:
1. configurable decision tolerances:
   `section_accept_tolerance`, `consistency_tolerance`
2. richer score metrics:
   baseline vs AI risk/quality averages, quality deltas, fallback reason counts
3. Corrections tab now shows an **AI Section Audit Summary** card:
   sections accepted/fallback, consistency decision, score snapshots

## Week 5: Journal Profiles + Profile-Aware Reference Validation

Added:
1. structured journal profile system (`journal_profile`) with Vancouver variants
2. stronger profile-aware reference formatting:
   initials punctuation, title-case policy, journal abbreviation policy
3. profile-aware validation messages in Corrections tab to flag mismatches against selected profile

## Week 6: Citation + Reference Validator

Added:
1. in-text citation validation:
   malformed bracket syntax, duplicate citation numbers inside a block, citations missing matching references
2. reference list validation:
   source-type-aware checks for journal articles, books, websites, and simple book chapters
3. automatic Vancouver renumbering:
   citations and references are remapped to first appearance order, with uncited references appended after cited ones
4. missing metadata placeholders:
   unresolved fields can be surfaced inline as gray markers like `[place missing]` or `[cited date missing]`
5. Corrections tab warning card:
   issue totals, category counts, and actionable validation messages

## Week 7: Pro Editing UX

Added:
1. side-by-side **Compare** view for Original vs Corrected vs Redline
2. Corrections tab actions to accept/reject change groups
   (`spelling`, `capitalization`, `punctuation`, `citation`, `reference`, `style`)
3. deterministic accepted-text pipeline:
   DOCX save/export now follows the currently accepted/rejected group state

## Week 8: First-Run Setup Wizard (Completed & Verified)

Added:
1. first-run setup wizard overlay for API keys and Ollama host
2. provider-aware guidance text (Ollama, Gemini, OpenRouter, Agent Router)
3. reusable "Open First-Run Setup Wizard" button under AI Settings

## Week 8: Windows Packaging Pipeline (Completed & Verified)

Added:
1. Windows build dependency file: `requirements-build.txt`
2. Portable `.exe` build scripts (`scripts/windows/build_exe.bat`, `scripts/windows/build_exe.ps1`)
3. Installer build script (`scripts/windows/build_installer.bat`) and Inno Setup configuration (`packaging/windows/ManuscriptEditor.iss`)
4. GitHub Actions workflow `.github/workflows/windows-installer.yml` to build/upload Windows artifacts

## Week 8: Ubuntu Packaging Pipeline (Completed & Verified)

Added:
1. Debian package build script (`scripts/linux/build_deb.sh`)
2. Linux launcher + desktop entry (`packaging/linux/manuscript-editor`, `packaging/linux/manuscript-editor.desktop`)
3. GitHub Actions workflow `.github/workflows/ubuntu-deb.yml` to build/upload Ubuntu `.deb` artifact

## Week 8: Release Ops Checklist (Completed & Verified)

Added:
1. release operations checklist (`RELEASE_CHECKLIST.md`), changelog (`CHANGELOG.md`), and QA template (`QA_SIGNOFF_TEMPLATE.md`)
2. Fully documented versioning policy, upgrade notes, and rollback instructions

## v1.2.0: Autonomous Bibliography-Healing & Split-Canvas UI (Completed & Wired)

Added:
1. **Autonomous Bibliography-Healing Engine**: Auto-corrects, enriches, and reformats reference lists using Crossref/OpenAlex/Serper query verification, exporting high-confidence DOIs, formatted author initials, and Vancouver-style numbering order.
2. **Interactive Split-Canvas Editor**: Side-by-side comparison panels with a ratio-based scroll lock, HSL-pulsed highlights for modified items, and seamless user correction acceptance.
3. **Healing API Endpoint**: `POST /api/tasks/<task_id>/heal-bibliography` schedules background jobs via the in-process queue with full telemetry/audit.

## Repo Status

Current status: `Active Development — v1.2.0-dev`

What this means:
1. Core features and packaging pipelines (v1.1.1) were fully verified and signed off on **2026-05-23**.
2. Major Premium research features for bibliography healing and split-canvas interactive editing are fully implemented and running under the `v1.2.0-dev` stage.
3. All quality check gates and local/regression tests pass cleanly (`Ran 159 tests ... OK`).

Immediate priorities:
1. `P0`: Add unit/integration tests for the bibliography healing engine (Phase C)
2. `P1`: Centralize secret management, background job progress polling, and eliminate any remaining Eel/web duplicate logic
3. `P2`: Broaden custom journal profiles beyond Vancouver variant preset styles

Full roadmap:
1. `REPO_STATUS_ROADMAP.md`

## Usage

### Linux/Ubuntu

```bash
./run.sh
```

Or:
```bash
python3 main.py
```

### Windows

```bash
run.bat
```

Or:
```bash
python main.py
```

If you see `ModuleNotFoundError: No module named 'pkg_resources'`, reinstall dependencies:

```bash
py -m pip install -r requirements.lock
```

### Browser/Web App

Run the deployable web server:

```bash
python webapp.py
```

Or use the launch helpers:

```bash
run_web.bat
run_web.sh
```

Then open:

```text
http://127.0.0.1:8000
```

To bind for LAN access or a hosting platform:

```bash
MANUSCRIPT_EDITOR_HOST=0.0.0.0 MANUSCRIPT_EDITOR_PORT=8000 python3 webapp.py
```

The WSGI entrypoint is `webapp:app`.

Web mode now requires authentication for all editing/task APIs.

Required auth env vars for web mode:
1. `GOOGLE_CLIENT_ID` (OAuth client for Google Sign-In)
2. `ALLOWED_EMAIL_DOMAINS` (comma-separated allowlist)
3. `ADMIN_EMAILS` (comma-separated admin users)

Recommended persistence env vars:
1. `DATABASE_URL` (PostgreSQL URL; SQLite fallback works for local/test)
2. `DATA_DIR` (persistent storage for uploaded/generated task files)
3. `SESSION_TTL_HOURS` (default `12`)
4. `FILE_RETENTION_DAYS` (default `30`)

### Coolify Deployment

Recommended setup: deploy this repo with the `Dockerfile` build pack.

Coolify settings:
1. Build Pack: `Dockerfile`
2. Base Directory: `/`
3. Port: `8000`
4. Domain: `https://aicopyeditor.celnet.in`
5. Health Check Path: `/api/health`

Suggested environment variables:
1. `PORT=8000`
2. `GUNICORN_WORKERS=2` (or higher once PostgreSQL is configured)
3. `GUNICORN_THREADS=8`
4. `GUNICORN_TIMEOUT=600`
5. `DATABASE_URL=postgresql://...`
6. `GOOGLE_CLIENT_ID=...`
7. `ALLOWED_EMAIL_DOMAINS=celnet.in,conwiz.in,stmjournals.in,stmjournals.com,nanoschool.in,nstc.in`
8. `ADMIN_EMAILS=amit@conwiz.in,puneet.mehrotra@celnet.in`
9. `DATA_DIR=/app/data`
10. `SESSION_TTL_HOURS=12`
11. `FILE_RETENTION_DAYS=30`

Important:
1. Use a managed PostgreSQL service/container and persist `DATA_DIR` with a mounted volume.
2. The container includes `curl`, so Coolify UI health checks can probe `/api/health`, and the Dockerfile also defines a container health check.
3. Point the DNS `A` record for `aicopyeditor.celnet.in` to your Coolify server IP before enabling HTTPS.
4. Google Sign-In must be configured with your deployment domain in Google Cloud console.
5. If you use AI providers server-side, add their keys in Coolify environment variables or enter them from the browser UI after deployment.

### Windows Packaging (`.exe` Installer)

On a Windows machine:

1. Build portable executable:
```bat
scripts\windows\build_exe.bat
```

2. Build installer executable (requires Inno Setup `iscc`):
```bat
scripts\windows\build_installer.bat
```

Expected outputs:
1. Portable app: `dist\ManuscriptEditor\ManuscriptEditor.exe`
2. Installer: `dist_installer\ManuscriptEditor_Setup_<VERSION>.exe`

If a built `.exe` fails with `No module named 'pkg_resources'`, rebuild after refreshing build dependencies:

```bat
py -m pip install -r requirements-build.txt
scripts\windows\build_exe.bat
```

### Ubuntu Packaging (`.deb`)

On an Ubuntu machine:

1. Build Debian package:
```bash
./scripts/linux/build_deb.sh
```

Expected output:
1. Debian package: `dist_deb/manuscript-editor_<VERSION>_amd64.deb` (architecture may vary)

### Release Process Files

1. Release checklist: `RELEASE_CHECKLIST.md`
2. Changelog: `CHANGELOG.md`
3. Week 8 completion summary: `WEEK8_COMPLETION.md`
4. QA sign-off template: `QA_SIGNOFF_TEMPLATE.md`

## How to Use

1. **Launch** the application
2. On first launch, complete the setup wizard:
   - choose provider
   - set Ollama host or paste API key
   - click **Save and Start**
3. **Upload** your manuscript by:
   - Drag and drop a `.txt` or `.docx` file
   - Click the upload zone and browse
4. **Select options** for editing:
   - Spelling Corrections
   - Sentence Case Fixes
   - Punctuation Refinements
   - Chicago Style Formatting
   - AI provider/model settings (Ollama or Gemini)
5. **Click "Process Document"** to begin editing
6. **Preview** results in the right panel
7. **Save** your work:
   - "Save Clean Version" - Corrected document without markup
   - "Save Highlighted Version" - Shows all changes with track changes

## Project Structure

```
manuscript_editor/
├── main.py              # Application entry point and UI
├── document_processor.py # Document loading, AI processing, DOCX generation
├── chicago_editor.py    # Chicago Manual of Style editing rules
├── requirements.txt    # Editable Python dependency intent
├── requirements.lock   # Pinned runtime dependency lock
├── tests/              # Regression tests
├── scripts/            # Quality and utility scripts
├── run.sh              # Linux launcher
├── run.bat             # Windows launcher
└── README.md           # This file
```

## Output Files

### Clean Version (.docx)
A fully formatted Word document with all corrections applied. Ready for publication or sharing.

### Highlighted Version (.docx)
A Word document with track changes enabled showing:
- **Red strikethrough** - Deleted original text
- **Green underline** - Added corrections
- Both versions visible for easy comparison

## Troubleshooting

**"AI not available" error**:
- Ensure Ollama is installed and running: `ollama serve`
- Check that the llama3.2 model is downloaded: `ollama pull llama3.2`

**File won't load**:
- Ensure the file is `.txt` or `.docx` format
- Check that the file isn't password-protected

**Processing seems slow**:
- AI processing depends on your hardware
- Without Ollama, rule-based editing is faster but less comprehensive
- Admins can tune Ollama transport in Global Settings: generate timeout,
  health timeout, retry count, retry backoff, and fallback-model retry. The same
  defaults can be set with `MANUSCRIPT_EDITOR_OLLAMA_GENERATE_TIMEOUT_SECONDS`,
  `MANUSCRIPT_EDITOR_OLLAMA_HEALTH_TIMEOUT_SECONDS`,
  `MANUSCRIPT_EDITOR_OLLAMA_RETRY_COUNT`,
  `MANUSCRIPT_EDITOR_OLLAMA_RETRY_BACKOFF_SECONDS`, and
  `MANUSCRIPT_EDITOR_OLLAMA_FALLBACK_MODEL_RETRY`.

## License

MIT License
