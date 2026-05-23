# Changelog

All notable changes to this project are documented in this file.

The format is inspired by Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]

### Added

- (none yet)

## [1.1.1] - 2026-05-23

### Added

- Sandbox-friendly path overrides for temporary file directories (`tempfile.tempdir`) and SQLite databases to prevent environment/nsjail execution and cleanup blocks.
- Fully verified installer pipelines and packaging targets for both Windows and Ubuntu platforms.
- Completed multi-platform QA Sign-Off evidence for fresh-machine releases of Manuscript Editor.

### Fixed

- Resolved automated quality check execution blockers in restricted container/dev sandbox environments.

## [1.1.0] - 2026-05-11

### Added

- Assistant Phase 1 rollout with read-only diagnostics, safe task reprocess action, and in-app assistant chat widget.
- Assistant resiliency upgrades: explicit unavailable banners, dashboard/task context hints, request logs, fallback insights, retry controls, and run-stage indicators.
- New rerun action for unresolved references with safe mode defaults and visible execution-path telemetry.
- Reference quality hardening:
  - stricter author-initial formatting behavior
  - stronger book-entry validation and indicators
  - DOI match thresholds and reason chips
  - DOI insertion override for verified high-confidence matches
  - verified DOI auto-complete with fill-only-missing safety mode
  - autofill outcome states (`Full`, `Partial`, `None`) and unresolved-only review filter
- CMOS Expansion Layer Phase 2 foundations (settings, diagnostics, first rule pack).
- Version governance improvements:
  - centralized `VERSION` source (`1.1.0`)
  - `/api/version` endpoint
  - UI-visible version badge and footer version binding
  - package defaults wired to shared version source

## [1.0.0] - 2026-04-17

### Added

- Week 1 quality baseline and regression test harness.
- Week 2 save/export hardening with telemetry and stable error codes.
- Week 3 section-wise chunk quality scoring and safe fallback selection.
- Week 4 global consistency pass scoring and audit summary in UI.
- Week 5 journal profile system with stronger profile-aware reference formatting.
- Week 6 citation/reference validator with corrections-tab warnings.
- Week 7 pro editing UX:
  - compare mode (Original, Corrected, Redline)
  - accept/reject correction groups
  - deterministic export from accepted decisions
- Week 8 packaging and deployment foundations:
  - first-run setup wizard
  - Windows portable and installer pipeline
  - Ubuntu `.deb` package pipeline

### Fixed

- Save fallback behavior for environments without `tkinter`.
- Wizard popup close behavior and first-run state handling.
