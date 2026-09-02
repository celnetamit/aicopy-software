# AI Handoff: API Surface

Updated: 2026-05-14
Source of truth: `routes/*.py` and `webapp.py`

## Page Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Redirects to `/tasks` |
| GET | `/tasks` | Task dashboard shell |
| GET | `/tasks/` | Task dashboard shell |
| GET | `/tasks/<task_id>` | Task detail/editor shell |
| GET | `/tasks/<task_id>/` | Task detail/editor shell |
| GET | `/admin-dashboard` | Admin dashboard shell |
| GET | `/admin-dashboard/` | Admin dashboard shell |
| GET | `/eel.js` | Eel-compatible web bridge |
| GET | `/<asset_path:path>` | Static web asset fallback |

## Diagnostics And Runtime

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/version` | Version payload |
| GET | `/api/runtime-telemetry` | Runtime save/export telemetry |
| POST | `/api/runtime-telemetry/reset` | Reset runtime telemetry |
| POST | `/api/reset-session` | Reset in-memory/legacy session state |
| GET | `/api/settings/runtime` | Effective runtime settings |
| POST | `/api/client-errors` | Report an uncaught browser error into the server error log |

## Auth

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/auth/config` | Login/runtime auth configuration |
| POST | `/api/auth/google-login` | Google credential login |
| POST | `/api/auth/local-login` | Local/dev login when enabled |
| GET | `/api/auth/me` | Current authenticated user |
| POST | `/api/auth/logout` | Revoke current session |

## Tasks

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/tasks/upload-text` | Create task from plain text |
| POST | `/api/tasks/upload-docx` | Create task from DOCX base64 payload |
| GET | `/api/tasks` | List current user's tasks |
| GET | `/api/tasks/<task_id>` | Get task detail and generated file metadata |
| POST | `/api/tasks/<task_id>/process` | Process/reprocess task |
| POST | `/api/tasks/<task_id>/apply-correction-group-decisions` | Apply grouped accept/reject decisions |
| GET | `/api/tasks/<task_id>/download` | Download generated artifact |
| GET | `/api/tasks/<task_id>/download-file` | Download specific task file |

## Assistant

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/assistant` | Assistant Q&A/action endpoint |

## Admin

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/users` | List users |
| POST | `/api/admin/users/<user_id>/status` | Activate/deactivate user |
| GET | `/api/admin/audit-events` | List/filter audit events |
| GET | `/api/admin/error-events` | List/filter recorded errors, with a summary (no tracebacks) |
| GET | `/api/admin/error-events/<event_id>` | One error with its full traceback and context |
| POST | `/api/admin/error-events/purge` | Clear the stored error log, or rows older than `older_than_days` |
| GET | `/api/admin/global-settings` | Read admin global settings |
| POST | `/api/admin/global-settings` | Save admin global settings |
| GET | `/api/admin/reference-validation-diagnostics` | Reference validation diagnostics |
| POST | `/api/admin/reference-validation-diagnostics/reset` | Reset shared reference validation cache |
| POST | `/api/admin/validate-ai-provider` | Validate provider settings |

## Legacy/Eel-Compatible API

These routes preserve older desktop/browser bridge behavior.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/load-text` | Legacy load text |
| POST | `/api/load-docx` | Legacy load DOCX |
| POST | `/api/process-document` | Legacy process current document |
| POST | `/api/apply-correction-group-decisions` | Legacy correction decisions |
| GET | `/api/redline-preview` | Legacy redline preview |
| GET | `/api/ollama-models` | List Ollama models |
| POST | `/api/export-file` | Legacy export |
| POST | `/api/save-file` | Legacy save |

## API Design Notes For Enhancements

1. Prefer adding new API routes under `routes/` instead of growing `webapp.py`.
2. Require auth for user/task routes unless the route is explicitly public health/config.
3. Require admin role for operator controls, global settings, user management, and diagnostics mutation.
4. Keep task ownership checks centralized through existing dependency helpers.
5. Return structured JSON with `success` flags and stable error codes where possible.
6. Add or extend API tests in `tests/test_webapp_api.py` for every new route.

