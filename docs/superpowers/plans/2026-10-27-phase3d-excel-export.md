# Phase 3D Excel Export Implementation Plan

> Execute inline using superpowers:executing-plans, with TDD and a fresh independent whole-branch review before publication.

**Goal:** Export all matching audits safely to a genuine Excel workbook from Driver Audits.
**Architecture:** A Tk-independent report module owns validated pagination, streaming XLSX writing and atomic publication. An application-owned job bridges progress/completion to existing UI polling; screens only render safe job state.
**Tech stack:** Existing Python/CustomTkinter/REST client; XlsxWriter==3.3.0 desktop-only.
**Spec:** docs/superpowers/specs/2026-10-27-phase3d-audit-reports-design.md (approved).

## Global constraints

- Work in requested `C:\BHLI-Audit` / `feat/dams-audit-reports`; preserve all prior commits. No separate worktree needed for this explicitly assigned checkout.
- No backend/schema/grants/production changes, PDF, packaging or new sidebar destination.
- Seven business fields plus Record ID/Status, 38-logical-pixel table unchanged.
- 20,000 rows / 200 pages / 100 MiB text / 256 MiB workspace / 10 minutes; fail rather than truncate.
- Passwords/tokens never logged or persisted. One export, memory-only session, no automatic retry.

## Review focus

- Destination replacement races and cancellation at publication: preserve old file; test explicit publication gate.
- Offset pagination drift including duplicate IDs and same-date ordering: abort detected drift and disclose undetectable drift.
- Unicode/control characters and formula-like strings: explicit XLSX text cells with complete supported values.
- Session/theme/navigation/close changes: no worker Tk access or stale widget callbacks.
- Disk failure at workbook close or cleanup: no misleading success, preserve destination and report cleanup failure.

## Task 1: Export module

Files: create `desktop/reports.py`, `tests/desktop/test_reports.py`; modify `requirements-desktop.txt`.
Interface: `export_audits(client, token, query, destination, control, progress, limits=Limits()) -> ExportResult`; `Destination.capture(path)` records initial file identity; `ExportControl.cancel()` signals without blocking the UI. The final cancellation check defines the publication decision.
- [x] Write contract tests for workbook ZIP/XML, all fields/text safety, multipage filters, ordering, cancellation, drift, limits and file failures; observe RED.
- [x] Implement streaming writer, page validation, cancellation and safe publication; verify focused tests GREEN.
- [x] Verify dependency integrity, commit meaningful export milestone.

## Task 2: Desktop job and controls

Files: create `desktop/export_ui.py`, `tests/desktop/test_export_gui.py`; modify `desktop/app.py`, `desktop/screens/audits.py`.
Interface: application-owned `ExportJob` state and `start` / `poll` / `cancel` / `close`; no widget references in worker closures. Screen exposes applied-filter fingerprint and export status.
- [x] Add RED native tests for off-thread generation, unapplied filters, save cancellation, navigation/theme persistence and session invalidation; inspect close cancellation wiring.
- [x] Implement confirm/save/progress/cancel/success/open-folder, clear failures and focus restoration; verify GREEN plus affected desktop regressions.
- [x] Commit UI milestone.

## Task 3: Acceptance, review and publication

Files: extend demo data and native capture, update desktop docs and verification evidence.
- [x] Exercise actual disposable REST API with two ADMIN accounts; generate fictional workbook and inspect in installed Microsoft Excel 16.
- [x] Native screenshots light/dark, compact/maximized, keyboard/progress/error; independent engineering/UI review and regression fixes.
- [x] Full default + native and isolated MySQL + native suites; no production access. Record actual skip counts.
- [ ] Commit evidence, push normally, one draft PR, verify hosted Windows/SQLite/MySQL CI; keep unmerged.

## Execution ledger

- Baseline verified from approved design. Plan approval already covered by user's complete implementation authorization; no repeated routine approval gate.
- Ruling: require a new destination filename rather than overwrite existing workbooks. Independent review reproduced a fingerprint/replace race; no ordinary filesystem compare-and-swap supports safe cross-process overwrite. Atomic no-clobber hard-link publication preserves every existing workbook, at the cost of requiring a new filename. UI and documentation disclose this deliberate safety restriction.
- Review correction: preserve an active 401 status if temporary-file cleanup also fails, and show the cleanup warning at login.
- Independent engineering review: reproduced and corrected workspace-finalization headroom, elapsed deadline after fsync, and cancellation blocking during slow publication. Final reviewer source check found no unresolved findings.
- Independent UI review: reproduced and corrected internal filter labels and keyboard-inaccessible overflowing disclosure; final reviewer confirmed both corrections.
- Resume recovery: isolated MySQL/native log completed successfully with 542 passed; default/native full run repeated because its earlier 537-pass log preceded the final nonblocking cancellation regression.
- Final default/native result: 538 passed, 4 explicit live-MySQL skips. Separate native close-during-export check passed with prompt return, worker completion, no files and no callback errors. Full evidence: `docs/WINDOWS_DESKTOP_PHASE3D_VERIFICATION.md`.
- Publication checkbox intentionally awaits external push/PR/hosted results, which are recorded on the draft PR and final report; avoid a documentation-only CI rerun merely to change this pre-publication ledger.
