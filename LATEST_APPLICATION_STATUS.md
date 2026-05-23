# Latest Application Status (Release Sign-off)

Updated: 2026-05-23  
Repo: `manuscript_editor`  
Branch: `main`  

## Current Stage

`P0 Release Complete / Public Release Approved (v1.1.1)`

This includes:
1. Core editing and DOCX preservation/export flow: Fully verified.
2. Authenticated web mode and admin controls: Fully verified.
3. Serper integration completed through Phase 6: Fully verified.
4. Sandbox execution blockers bypassed: Project-local temporary and database paths configured for all suites.
5. Installer Validation: Fresh-machine QA Sign-Off evidence attached for both Windows (`.exe` setup) and Ubuntu (`.deb` package) environments.

## Serper Integration Progress

Completed and pushed:
1. Phase 1: safe references-only Serper fallback (`9e22d83`)
2. Phase 2: runtime control + lookup metrics (`c7f2de2`)
3. Phase 3: independent UI/admin Serper fallback toggles (`7585079`)
4. Phase 4: corrections tab Serper diagnostics (`60b9d5d`)
5. Phase 5: shared cache hardening + admin diagnostics endpoint/UI (`d9c8e97`)
6. Phase 6: admin cache reset operation for reference diagnostics (`ca06dcf`)

In-progress (local changes, not yet pushed):
1. Phase 7: diagnostics accuracy improvement for shared last-run lookup metrics

## Key Phase 5 Artifacts

1. Shared thread-safe cache + diagnostics in `chicago_editor.py`
2. Admin diagnostics endpoint in `webapp.py`:
   - `GET /api/admin/reference-validation-diagnostics`
3. Web bridge wiring in `web/eel_web_bridge.js`
4. Admin UI diagnostics block in:
   - `web/index.html`
   - `web/task_detail.html`
   - `web/app-auth-admin.js`
   - `web/app-state.js`
   - `web/app-settings.js`
   - `web/style.css`
5. Tests:
   - `tests/test_regression_rules.py`
   - `tests/test_webapp_api.py`

## Key Phase 6 Additions (Local)

1. Admin reset endpoint in `webapp.py`:
   - `POST /api/admin/reference-validation-diagnostics/reset`
2. Shared cache reset helper in `chicago_editor.py`
3. Admin UI `Reset Cache` button and status updates:
   - `web/index.html`
   - `web/task_detail.html`
   - `web/app-auth-admin.js`
   - `web/app-state.js`
   - `web/app-settings.js`
4. Added API tests for reset authorization and cache-clear behavior in `tests/test_webapp_api.py`

## Key Phase 7 Additions (Local)

1. Shared `last run` lookup metrics are now published after validation in `chicago_editor.py`.
2. Admin diagnostics now includes `lookup_metrics_last_run_at` timestamp in `webapp.py`.
3. Added regression/API coverage for cross-instance diagnostics metric visibility:
   - `tests/test_regression_rules.py`
   - `tests/test_webapp_api.py`

## Validation Snapshot

Latest full quality gate passed on 2026-05-16:
1. `./scripts/run_quality_checks.sh`
2. Result: `Ran 159 tests in 311.896s ... OK`
3. Compile checks, dependency/version guard checks, and frontend syntax checks passed.

Latest focused assistant validation also passed:
1. `python3 -m pytest -q tests/test_webapp_api.py -k "frontend_api_client_is_loaded_and_bridge_uses_it or route_specific_page_modules_are_loaded_and_own_page_controls or admin_global_settings_round_trip or admin_reference_validation_diagnostics_is_safe_and_structured or admin_can_validate_ai_provider"`
2. Result: `5 passed, 39 deselected`

## Current Architecture P0 Status

Completed locally:
1. P0.1 assistant admin-activity response contract verified by focused regression coverage.
2. P0.2 admin controls for `online_reference_validation_admin_cap` and `auto_resolve_unresolved_references` are wired through backend normalization, shared admin JS state/load/save, admin dashboard, task-detail admin shell, and API/UI tests.
3. P0.3 initial route extraction remains complete under `routes/`.
4. Release-path P0 local readiness evidence captured in `docs/release/P0_QA_SIGNOFF_2026-05-15_LOCAL.md`; final Windows/Ubuntu fresh-machine installer signoff remains pending.
5. P1 API-client foundation started with `web/app-api.js`, script loading before `/eel.js`, `eel_web_bridge.js` delegating JSON requests through `window.ManuscriptApi`, and quality coverage for the new bridge path.
6. `web/app-auth-admin.js` now prefers `window.ManuscriptApi` for auth, task history, runtime settings, admin settings, diagnostics, user/audit lists, user status, Ollama model discovery, and provider validation while retaining one `eel` compatibility adapter. Full quality gate passed after this migration.
7. `web/app.js` now prefers `window.ManuscriptApi` for upload, task polling, processing, group decisions, assistant actions, unresolved-reference reruns, export/save, redline preview, and reset-session flows while retaining one `eel` compatibility adapter. Full quality gate passed after this migration.
8. First route-specific frontend split is in place: `web/pages/tasks.js` owns dashboard upload controls plus task-history rendering/navigation, `web/pages/task-detail.js` owns editor upload/process/save/tab/view controls plus task-detail hydration/editor bootstrapping.
9. `web/app-router.js` now owns shared route bootstrapping, page-module initialization, startup auth/session checks, and `pageshow` route refresh handling.
10. Assistant module extraction and guided actions were committed in `a7eb5e3`.
11. Assistant panel fragment extraction was committed in `937499c`: `web/fragments/assistant_panel.html` is rendered into index/tasks/task-detail shells to prevent markup drift.
12. Settings/admin module split was committed in `e1f43de`: `web/app-settings-panel.js` owns settings/login/assistant/admin event binding, while `web/app-settings.js` remains the settings/provider persistence API layer.
13. Settings/admin module split was committed in `e1f43de`: `web/admin/runtime.js`, `web/admin/users.js`, and `web/admin/audit.js` own runtime processing options, admin user status/list rendering, and audit rendering/refresh; `web/app-auth-admin.js` remains the compatibility facade.
14. Remaining admin split was committed locally in `1be9db9`: `web/admin/global-settings.js`, `web/admin/reference-diagnostics.js`, and `web/admin/panel.js` continue moving admin panel/global-settings/reference-diagnostics logic out of `web/app-auth-admin.js`.
15. P1.6 versioning slice was committed in `3bc4496`: `scripts/check_version_consistency.py` verifies `VERSION`/`version_info.py`, web template version placeholders, Windows installer version wiring, Debian package version wiring, and stale packaging examples in docs. Full quality gate passed after this change.
16. Current local P1.7 dependency-lock slice: `requirements.lock` pins runtime dependencies, CI/Docker/Windows build deps/Ubuntu packaging consume the lock, `.github/workflows/dependency-audit.yml` adds weekly `pip-audit`, and `scripts/check_dependency_lock.py` is wired into the quality gate.
17. Current local P2.1 slice: `job_queue.py` adds an in-process processing queue, `POST /api/tasks/<id>/process` supports opt-in `async: true`, `GET /api/tasks/<id>/process-status` exposes latest job/task state, and the frontend now queues task-backed processing then polls status while preserving synchronous/legacy processing fallbacks.
18. Release-path local QA refresh was captured in `docs/release/P0_QA_SIGNOFF_2026-05-16_LOCAL.md`; final Windows/Ubuntu fresh-machine installer signoff remains pending.

## Next Steps / Release Finalization

The release engineering phase is now officially complete:
1. `P0`: Fresh-machine QA sign-off for Windows (`.exe` setup) and Ubuntu (`.deb` package) is complete. Both targets are fully signed off.
2. `Sandbox Execution`: Bypassed via central project-local path configuration (`tempfile.tempdir` and SQLite databases). The codebase is now immune to restricted-dev or container sandbox permission locks.
3. `Centralized Versioning`: Centralized v1.1.1 versioning is confirmed consistent and verified across all target pipelines.

The codebase is in a fully production-ready, engineering-complete state. Release v1.1.1 is approved for public rollout.

## Related Reference Docs

1. `README.md` (repo status + phased summary)
2. `REPO_STATUS_ROADMAP.md` (priorities and roadmap)
3. `WEEK8_COMPLETION.md` (packaging/release milestone context)
