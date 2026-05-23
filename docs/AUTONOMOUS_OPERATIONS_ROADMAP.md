# Autonomous Operations Roadmap

Updated: 2026-05-23

## Goal

Reduce human intervention by making the platform run in "autopilot by default" mode, while routing only uncertain or risky outcomes to manual review.

## Operating Model

1. `L1 Assisted`: AI suggests, human decides.
2. `L2 Guarded Autonomy`: low-risk paths auto-run, high-risk paths require approval.
3. `L3 Full Autonomy`: end-to-end automatic execution with audit and rollback.

## What Is Implemented Now

1. New endpoint: `POST /api/tasks/{task_id}/autopilot`
2. Background execution via existing job queue and task-run tracking.
3. Policy gate support:
   - `automation.auto_heal_bibliography` (default `true`)
   - `automation.heal_when_reference_issues_at_least` (default `1`)
4. Pipeline behavior:
   - Runs `process_task` with safe default options.
   - Counts reference issues from processing report.
   - Conditionally runs bibliography healing stage.
5. Full audit and status visibility through existing `process-status` and task-run telemetry.

## API Example

```http
POST /api/tasks/{task_id}/autopilot
Authorization: Bearer <token>
Content-Type: application/json

{
  "options": {
    "ai": { "enabled": true },
    "automation": {
      "auto_heal_bibliography": true,
      "heal_when_reference_issues_at_least": 1
    }
  }
}
```

Response:

```json
{
  "success": true,
  "queued": true,
  "task_id": "...",
  "job": { "...": "..." },
  "task_run": { "...": "..." }
}
```

## Next Phases

## Phase 1 (current hardening)

1. Add autopilot-specific diagnostics panel in task detail.
2. Persist autopilot decision traces in report payload (`why healed`, `why skipped`).
3. Add retry-once behavior for transient provider/network failures.
4. Add regression tests for:
   - heal gate triggered
   - heal gate skipped
   - downstream stage failure and audit correctness

## Phase 2 (confidence routing)

1. Add confidence scoring per stage:
   - language quality confidence
   - reference match confidence
   - citation integrity confidence
2. Add policy thresholds in admin global settings.
3. Auto-route low-confidence tasks into `REVIEW_REQUIRED` status.
4. Add one-click human approval/reject actions for exception queue.

## Phase 3 (full autonomous operations)

1. Scheduled ingestion connectors (email/API/drive).
2. End-to-end workflow templates per journal profile.
3. Automatic publish/export handoff with rollback safety.
4. Operational dashboard:
   - autonomous completion rate
   - intervention rate
   - failure reasons and MTTR

## Success Metrics

1. `% tasks completed without manual editing`
2. `% tasks routed to exception queue`
3. `autopilot success rate`
4. `median end-to-end processing time`
5. `reference integrity pass rate`
