# Offline Windows Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Steps below are verification checkpoints, not additional operator approval gates.

**Goal:** Implement approved Option A and stable offline sidebar behavior while retaining the compact-button commit.
**Architecture:** Reuse the existing offline app routing, ProfileView, file-job handlers and shared Shell. Scope new navigation/header/state/tooltip policy to the offline Shell; preserve online defaults. No new service, dependency or storage layer.
**Tech Stack:** Existing Python/CustomTkinter/Tk, pytest native GUI mode.
**Spec:** ../specs/2026-11-08-offline-navigation-approved.md (operator-approved assignment).

## Global constraints

- Base 844042defb44db8cdc8d80217df04d5a8b0a973e; retain compact-button commit44f9363.
- Offline Windows only; no Android/backend/storage/signing/build-candidate changes.
- Sidebar Driver Audits, Settings & Tools; post-welcome home Driver Audits; New Audit/Excel remain visible.
- No Reports screen, network requirement, authentication or database migration.
- Keep pre-profile backup access, busy-operation guards, draft safety and immutable history.
- Dedicated branch, focused checkpoints, draft PR only; no merge/release/new final builds.

## Review focus

Manual expansion must survive small same-band resizes. Rebuilt shells must retain state. Theme changes must retain dirty audit/profile text. Pending tooltips must not outlive widgets or appear over their controls. Missing-profile restore/back must remain accessible without inventing an identity.

### Task1: Sidebar stability and tooltip lifecycle

Files: desktop/screens/shell.py; desktop/components/common.py; tests/desktop/offline/test_navigation_gui.py.
Interfaces: Shell.set_collapsed(value) retains public interface; Shell remembers offline width band/manual state via its app; Tip(widget,text,...) keeps online defaults and offers optional delayed/outside/enabled behavior, hide() cancels owned work.

- [x] Add native RED cases: 800->801 resize after explicit expansion; collapsed theme rebuild; Audit History parent selection; expanded no tooltip, collapsed delayed outside placement, pending cancellation and destroy.
- [x] Observe actual failures before product edits.
- [x] Implement offline-only size-band transitions, in-memory shell state, correct parent selection and lifecycle-safe tooltip policy. Keep native collapsed-logo clear and normal hand pointer.
- [x] GREEN targeted tests; commit coherent sidebar correction.

### Task2: Option A navigation and Settings & Tools

Files: desktop/offline/app.py, views.py, backup_ui.py; desktop/screens/audits.py; existing offline GUI/welcome tests; new navigation tests.
Interfaces: OfflineApplication.destinations=('Driver Audits','Settings & Tools'); existing Local profile route becomes compatibility alias to Settings & Tools, pre-shell return restores welcome. Settings uses existing profile save, open_backup, open_transfer and set_theme handlers.

- [x] RED tests assert two destinations/home, no header account/theme duplication, settings name/tools/appearance controls, welcome backup/back without profile, busy/dirty safety, transfer return and child highlighting.
- [x] Reuse ProfileView for grouped settings. Move transfer entry out of ordinary audit toolbar; keep Excel/New Audit. Preserve profile input during theme rebuild and confirmation before discarding edited name; retain audit draft/query/job behavior.
- [x] Update only intentional changed destination expectations in existing offline tests, retaining their data assertions.
- [x] GREEN focused GUI/profile/report/backup/transfer regressions; commit navigation checkpoint.

### Task3: Review and publication

- [ ] Run all affected native desktop regressions and relevant pure Python tests; diff check, source/candidate preservation, no secrets/generated payloads staged.
- [ ] Capture light/dark, compact/wide, collapsed/expanded and settings screenshots using fictional data. Widget multipliers1/1.5/2 are not actual OS DPI or physical-pointer acceptance.
- [ ] Fresh independent review of full cumulative diff, correct confirmed defects and retest affected paths. Preserve screenshots/docs and exact evidence.
- [ ] Push branch, create exactly one draft PR including44f9363, inspect hosted SQLite/MySQL/Windows jobs; Android untouched. No merge/release/build candidates.

## Ledger

Ruling: Use the user-requested repository/feature-branch isolation in place; existing local environments and ignored evidence stay available, and no parallel implementer changes this checkout.
Ruling: Keep the shared online Shell/Tip defaults; use offline-only options rather than global navigation redesign.
Ruling: Retire offline Dashboard routing as a home; its create/details/count capabilities already exist on Driver Audits. The online Dashboard remains intact.

Ruling: Once the operator explicitly toggles the offline sidebar, that choice wins over automatic resizing for the rest of the process (including theme/profile rebuilds). Automatic initial/size-band collapse applies only before an explicit choice. This avoids scaling-induced geometry changes being mistaken for operator intent; no persistent setting is added.

Verification: Task1 RED6failed/1passed, GREEN7passed. Task2 RED5failed, final combined navigation/tools GREEN14passed. Existing affected workflow checkpoint10passed. Additional confirmed footer/focus defects were reproduced RED and corrected before final GREEN. Full native desktop regression and final review/publication remain pending.
