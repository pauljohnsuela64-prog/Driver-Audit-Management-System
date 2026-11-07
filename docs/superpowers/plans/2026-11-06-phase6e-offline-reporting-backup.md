# Phase 6E Offline Reporting and Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete offline XLSX/text reports, authenticated full backups and same-platform recovery locally.

**Architecture:** Keep SQLite on its existing owner/queue. Snapshot known complete state into an authenticated platform-bound envelope; restore only after independently preserved recovery proof, in one transaction with verified outcome. Reporting reads one local snapshot and uses purpose-limited file adapters.

**Tech Stack:** Python3.14, XlsxWriter3.3.0, cryptography50.0.2; Flutter3.47.8/Dart3.13.7, sqflite2.4.5, cryptography2.9.0; existing Windows/Android native adapters.

**Spec:** `docs/superpowers/specs/2026-11-06-phase6e-offline-reporting-backup-design.md`, companion `backup-security-restore.md` and `verification-checkpoints.md`, approved at f315537.

## Global Constraints

- Work only on feat/dams-offline-reporting-backup; preserve all history and original release.
- Fictional temporary databases only; no installed-app replacement, production access, push, PR, release or Phase6F/G.
- No SQLite schema change. Same-platform full restore replaces all owned state/profile/install identity; cross-platform copying remains Phase6D.
- Fixed96-byte header, Argon2id19,456KiB/2/1, AES256GCM12-byte nonce/16-byte tag;64MiB payload,1MiB line,depth6; no unauthenticated parsing.
- Complete backup includes all6 owned tables and nullable audit sequence; no filtered/partial success.
- Windows20,000-row/100MiB/256MiB workspace/600s XLSX; Android same row/text/time cap for readable UTF8, not CSV.
- Recovery backup and bounded marker must be verified before replacement; unknown COMMIT blocks writes.
- All heavy native/build operations serialized. Focused tests per milestone, complete regressions after stabilization. Preserve interrupted work/artifacts.

## Review Focus

1. A successful COMMIT with lost acknowledgement must classify RESTORED, not auto-retry.
2. An old callback/draft after restore must not repopulate protected old data.
3. Same record count with changed history/profile/sequence must invalidate preview.
4. Provider readback/cleanup refusal must not advertise a complete backup or delete source.
5. Raw legacy history strings/offset timestamps must survive backup unchanged.

## File map and seams

- Python: `desktop/offline/backup_state.py` complete strict state codec/snapshot/scratch validation; `backup_crypto.py` fixed envelope; `backup_store.py` restore transaction/outcome; `store_lease.py` lifetime OS ownership; `backup_jobs.py`, `backup_ui.py` orchestration and UI.
- Windows reports: `reporting.py`, `report_ui.py`; narrow hooks in offline app/shared offline audit actions only.
- Dart: `backup_state.dart`, `backup_crypto.dart`, `backup_store.dart`, `backup_screen.dart`; owner adapter methods in sqlite_repository; `reporting.dart`, `report_screen.dart` and list/profile hooks.
- Android native: purpose-limited `OfflineDocuments.kt`, owner lease bridge; do not weaken `TransferDocuments` path/size policies.
- Tests adjacent to existing offline Python/Dart suites; shared fictional backup golden vectors under mobile/test/fixtures/backup. No user database fixture.
- Security dependency overlay, pinned hashes/notices and offline builders/tests updated only as needed; online functionality unchanged.

### Task 1: Complete-state and security contracts

**Interfaces:** `capture_state(repo)->StateSnapshot`; `encode_state(snapshot)->bytes`; `decode_state(raw,platform)->StateSnapshot`; `seal_backup(payload,password,platform)->bytes`; `open_backup(raw,password,platform)->bytes`. Snapshot includes exact rows/sequence and stable state digest.

- [ ] Write real-SQLite tests for empty/populated/archive/history/receipts/sequence, raw JSON preservation, bounds, unknown tables and platform mismatches. Run RED before modules exist.
- [ ] Implement known-column fixed-schema validation; parameterized scratch inserts and semantic/history/FK checks; canonical outer JSON without rewriting raw history strings.
- [ ] Write crypto tests for fixed framing, correct Unicode password, random nonces, wrong password/tamper/truncation/hostile KDF fields. Run RED; implement established library calls, never log secrets.
- [ ] Run focused Python and Dart contracts, actual Python↔Dart vectors, formatting/analyze; review and commit coherent contracts.

### Task 2: Windows local Excel reports

**Interfaces:** `report_snapshot(repo,filter)->ReportSnapshot`; `export_report(repo,filter,path,cancel,progress)->ReportResult`. Never import online reports/API modules.

- [ ] Write RED tests: all matching rows, snapshot race, applied filters/order/archive/zero rows, literal text/formula/URL/Unicode/zeros, cancellation/no-overwrite/full failures.
- [ ] Implement owner read snapshot and offline XlsxWriter adapter with existing vetted formatting policies; two sheets,9 columns, bounded staging and Windows-safe new-only publication.
- [ ] Add offline UI entry using durable job admission and generation-safe completion. Test controller/native UI when coordinated.
- [ ] Run focused report tests and offline regression; review and checkpoint commit.

### Task 3: Android summaries and text report

**Interfaces:** owner `reportSnapshot(AuditFilter)` returning immutable `OfflineReportSnapshot`; `encodeTextReport(snapshot)->Uint8List`. Existing repository fakes remain compatible through a separate reporting interface.

- [ ] Write RED real-SQLite/widget tests for counts, exact filters, station Other total, all rows, UTF8/optional/zeros/multiline labels and limits.
- [ ] Implement snapshot summary/text writer; scrollable screen and purpose-limited SAF save action. Preserve existing filters/CRUD/history.
- [ ] Run focused Flutter tests then analyze/format; review and checkpoint commit. No emulator concurrent with builds.

### Task 4: Durable owner and encrypted generation/file publication

**Interfaces:** lifetime `StoreLease.acquire/release`; `BackupJobs.create/inspect` returning frozen artifact/preview; purpose-limited documents methods for backup/report only.

- [ ] RED competing owner/process-death, fresh private stage, all-state regardless filters, failed encrypt/write/readback/cleanup and cancellation tests.
- [ ] Implement OS lease before SQLite open, retained until drained close; private generated stages, header cap before KDF, password-only-memory and phase-truthful result.
- [ ] Implement native SAF bounds/readback/new-output deletion and Windows no-replace; no broad storage/Internet or arbitrary path capability.
- [ ] Verify local crypto support, dependency pins/notices, ordinary builds and native fault-provider cases; review and checkpoint commit.

### Task 5: Restore, markers and assisted recovery

**Interfaces:** `inspect_restore` binds candidate and original state digest; `apply_restore` consumes verified recovery proof and returns ORIGINAL/RESTORED/UNKNOWN; startup examines required marker before cleanup/UI writes.

- [ ] RED actual-SQLite tests for all owned rows/identity replacement, race with equal counts, failed mandatory recovery, partial table/FULL/IO/COMMIT failures and actual COMMIT then lost result.
- [ ] Configure/check durability before BEGIN; save/authenticate/readback current recovery independently; required4KiB constrained marker; single dependency-ordered parameterized replacement with FK/semantic/digest verification.
- [ ] Reopen/classify outcomes; never auto-retry/empty-reset. Retain encrypted evidence; old callbacks/drafts invalidated. Add separate-process kill tests around every stage in both journal modes.
- [ ] Implement recovery instructions at unreadable bootstrap: preserve damaged files/sidecars and restore verified backup only in fresh same-platform OS user/device target.
- [ ] Run focused restore/process tests, independent safety review, checkpoint commit.

### Task 6: Backup/restore UI and accessibility

**Interfaces:** UI consumes job phases/preview/outcome only; no raw SQL/native path manipulation.

- [ ] RED tests for password confirmation, explicit replacement acknowledgement, default Cancel, mandatory recovery destination, dirty drafts, cancellation after commit, background/restart/unknown-state blocking.
- [ ] Implement Local profile subordinate Backup & restore screens (including empty setup), startup recovery guidance, readable errors/progress and safe window-close semantics.
- [ ] Native Windows and Android fictional acceptance: compact/maximized/themes/keyboard/200% text/SAF/cold restart; preserve installed apps/AVDs. Review and checkpoint commit.

### Task 7: Full verification and local completion

- [ ] Run full Python default and guarded isolated MySQL, native Windows, full Flutter, formatting/analyze; record separate totals/skips.
- [ ] Build offline+online Android and Windows candidates from clean checkpoint; notices/hashes/exclusions; run ordinary isolated startup/report/backup/restore acceptance and resource probes.
- [ ] Independent engineering/security and UX review of cumulative implementation; RED/GREEN confirmed fixes, rerun affected suites/candidates only.
- [ ] Update operator docs with actual outcomes, assisted recovery/identity/password-loss warnings, unverified physical/API24/power-cut/installer limitations; commit verified changes and confirm clean branch.
- [ ] Report results locally and stop. No publication, merge or next phase.
