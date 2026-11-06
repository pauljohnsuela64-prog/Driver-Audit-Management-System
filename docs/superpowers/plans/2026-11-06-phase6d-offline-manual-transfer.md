# Phase 6D Offline Manual Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans; independently scoped platform work may use superpowers:dispatching-parallel-agents. Track steps below.

**Goal:** Exchange validated append-only audit/history snapshots between Android and Windows without a server.

**Architecture:** Pure codecs enforce one wire contract. Real SQLite repositories own consistent export snapshots, import comparisons and atomic application; widgets own only interaction. System file adapters publish validated staged packages.

**Tech Stack:** Python 3.14, SQLite, Flutter/Dart, Android SAF, existing CustomTkinter. SHA-256 and STORE ZIP; dependencies remain pinned and reviewed.

**Spec:** `docs/superpowers/specs/2026-11-06-phase6d-offline-manual-transfer-design.md` (approved at `d8878cd`).

## Global Constraints

- Local commits only on `feat/dams-offline-manual-transfer`; no push/PR/release.
- Keep local singleton profile separate from original imported identities.
- Preserve every record/history UUID, snapshot, timestamp and revision.
- Format v1; SQLite v2. No backend/online behavior or production changes.
- Limits: 32 MiB file/expanded total, 64 KiB manifest, 256 KiB line, 2,000 audits, 10,000 events, JSON depth 6. Measure before acceptance.
- Reject conflicting event/package UUID reuse; never overwrite an audit.
- Fictional fixtures only; serialize heavy test/build/emulator operations.

## Review Focus

- Device clock moves backwards: revisions define order; valid old data still migrates.
- Name changes for one identity: preserve snapshots without registry name collision.
- Preview-to-commit race: changed classifications abort and demand fresh confirmation.
- Android picker background/process death: no false cancellation/success or persistent plaintext draft outside private staging.
- Destination race or failed final close: never overwrite an existing file or report partial success.

### Task 1: Versioned identity migrations

**Files:** `desktop/offline/repository.py`, new `desktop/offline/schema.py`; `mobile/lib/offline/sqlite_repository.dart`, new `mobile/lib/offline/schema.dart`; migration tests per platform.

**Interfaces:** Preserve all current repository methods. SQLite v2 adds `auditor_identities(id)` and `transfer_receipts(package_id,content_sha256,source_installation_id,imported_at,imported_count)`; record origin and event actor reference registry. Registry entries carry no mutable name.

- [ ] RED: real populated v1 fixture upgrades to user_version 2 with identical profile, audits, events and insertion sequence; invalid v1/FK/commit failures preserve original data.
- [ ] Implement owned-schema verification and transactional replacement-table migration with FKs enabled; fresh databases start empty at v2.
- [ ] GREEN: existing offline repository/model/failure tests plus migration tests pass; retain and update version-specific assertions rather than removing tests.
- [ ] Commit verified migrations.

### Task 2: Shared codecs and fixtures

**Files:** `desktop/offline/transfer.py`; `mobile/lib/offline/transfer.dart`; `tests/desktop/offline/test_transfer.py`; `mobile/test/offline/transfer_test.dart`; shared `mobile/test/fixtures/transfer/`.

**Interfaces:** Both expose canonical JSON, validated package data (manifest/audits/events/content digest), encode and decode package. Codec inputs use the spec's exact snake_case maps, not platform model serialization. No database/UI imports.

- [ ] RED: encode/decode valid fictional CREATE/UPDATE/ARCHIVE chain; reject altered identity, archived CREATE, broken before/after, UUID collision, duplicate keys, ZIP ambiguity, resource excess and invalid Unicode.
- [ ] Implement canonical ASCII JSON with LF, exact strict shapes and limits; SHA-256 streams; STORE ZIP validation with no extraction.
- [ ] GOLDEN: Python-generated package consumed by Dart and Dart-generated package consumed by Python; all three canonical entry bytes/hashes match fixed UUID/timestamp fixture.
- [ ] GREEN: focused codec suites, Dart format/analyze; measure near-limit memory/time; commit.

### Task 3: Repository transfer transactions

**Files:** new `desktop/offline/transfer_store.py`; new `mobile/lib/offline/transfer_store.dart`; repository adapters and real SQLite transfer tests.

**Interfaces:** `exportPackage(dateFrom,dateTo,cancel)` returns staged package; `previewImport(package)` returns frozen new/duplicate/conflict classifications; `applyImport(package,preview,cancel)` returns counts. Exact platform signatures recorded with their tested implementation. All methods execute on the existing owning queue/connection.

- [ ] RED: independent profiles exchange records/history in both directions; duplicates are no-ops, revision differences are conflicts, event/receipt collisions reject, local profile remains untouched.
- [ ] Implement one consistent export snapshot including archived audits and complete histories. Validate full chain before export.
- [ ] Implement preview and write-transaction revalidation; registry/audits/events/receipt commit together. Zero-new confirmation may record a receipt.
- [ ] Inject insertion/session-independent storage/final COMMIT failures; assert rollback of every inserted table. Test cancellation, clock correction, reimport after local edit and restart.
- [ ] GREEN: real SQLite suites and opposite-platform files pass; commit.

### Task 4: Windows workflow and publication safety

**Files:** new `desktop/offline/transfer_ui.py`, `desktop/offline/transfer_files.py`; existing offline app/views; desktop transfer UI/file/native tests.

- [ ] RED: save-dialog cancel, existing destination race, disk-full, failure cleanup, preview consent, double dispatch and pending-write shutdown.
- [ ] Add Export Audits / Import Audits to existing workspace; all/date-range, count/progress, staged export and explicit new-only preview confirmation.
- [ ] Use native dialogs only on Tk thread; database worker for snapshots/import; no-replace output publication; retain durable close acknowledgment.
- [ ] GREEN: native compact/dark/light/keyboard checks and original desktop regressions; commit.

### Task 5: Android SAF and workflow

**Files:** new `mobile/lib/offline/transfer_screen.dart`, `transfer_documents.dart`; offline app; Android transfer MethodChannel adapter; widget/native tests.

- [ ] RED: picker cancel, URI access denial, read limits, copy/close/hash failure, background/resume, duplicate dispatch and consent.
- [ ] Implement native create/open document channel with bounded executor I/O and local-only request; no broad storage permissions. Keep full package bytes off MethodChannel.
- [ ] Stage privately before destination selection; read-back hash before success; cleanup newly created document on failure and disclose failed cleanup.
- [ ] Reuse existing theme, scrolling, large-text and local profile/navigation; expose counts without raw UUIDs.
- [ ] GREEN: focused widget/native tests and actual emulator file exchange with network disabled; commit.

### Task 6: Final review and local acceptance

**Files:** `docs/OFFLINE_TRANSFER.md`, checkpoint evidence under ignored `artifacts/phase6d/`.

- [ ] Independent engineering/security and UX reviews; RED/GREEN fixes only for confirmed findings.
- [ ] Full Python default and isolated MySQL, Flutter, native Windows, syntax/format/analyze, licensing/dependency and original online regression checks.
- [ ] Build ordinary offline/online Android APKs and offline Windows candidate. No install replacing existing applications; no public artifacts.
- [ ] Record genuine native screenshots, provider/device gaps, ceilings measurement, exact test counts/skips and cross-platform package exchange results.
- [ ] Verify clean tree, preserved Version 1.0 release and no bundled DB/credentials; final local commit/report. Stop before publication.

## Execution

Operator explicitly authorized implementation after design approval without another routine checkpoint. Execute this plan directly; no additional plan approval is required. Use separate file ownership for independent platform tasks and integrate sequentially at shared-contract gates. Never run competing heavy toolchain/test processes.
