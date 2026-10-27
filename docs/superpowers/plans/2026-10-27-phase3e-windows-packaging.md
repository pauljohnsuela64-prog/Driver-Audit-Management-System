# Phase 3E Windows Packaging Implementation Plan

> Execute inline with superpowers:executing-plans and TDD; independent engineering/UI review before draft publication. User already approved full execution; no repeated design gate.

**Goal:** Deliver a self-contained Windows client and per-user installer with safe first-launch connection settings.
**Architecture:** Tk-independent version/resources/settings modules; signed-out connection dialog using existing worker queues; PyInstaller onedir plus Inno installer, no backend/database in the client.
**Tech stack:** CPython 3.14 x64, CustomTkinter, PyInstaller 6.22.3, Inno Setup 7.1.0.
**Spec:** docs/superpowers/specs/2026-10-27-phase3e-windows-packaging-design.md.

## Global constraints
- Work in requested branch/checkout; preserve previous commits and private config. No production access/migration/grants/server deployment.
- Preserve seven business fields, roles, audit CRUD/history and Excel export.
- Client-only bundle; no credentials, backend, migrations, tests/demo fixture or build environment.
- Unsigned artifacts remain test candidates. Clean Windows VM and production signing require actual evidence, never implied by a build.

## Review focus
- Frozen/no-console startup failures remain visible without raw exception or credential disclosure.
- Endpoint overrides, missing/corrupt settings and signed-out switching never redirect a live token.
- Tcl/Tk/themes/fonts/Pillow/SSL/export assets actually work from an installed path without Python/PATH.
- Installer/uninstaller never kill pending work, erase reports/settings or touch backend resources.
- CI artifacts have pinned toolchain, inventories/checksums and no privileged PR signing.

## Checkpoint 1: startup/settings/branding
Files: desktop/settings.py, desktop/resources.py, desktop/version.py, desktop/screens/connection.py; existing entry/app/login/API; tests/desktop/test_settings.py and test_connection_gui.py.
Interfaces: load_settings(path), save_settings(path, origin), resolve_settings(cli, environ, path, frozen); resource_path(name); signed-out app.open_connection().
- [x] RED tests for precedence, strict bounded JSON, atomic writes, URL rejection, frozen missing config, safe early errors.
- [x] Implement pure settings and resources, then RED/GREEN native connection tests for no-auth health, disabled login, save/test/cancel, endpoint switch and override policy.
- [x] Generate owned BHLI icon, verify affected regressions and commit.

## Checkpoint 2: frozen build
Files: packaging/windows/BHLIAudit.spec, entry.py, version_info.txt, assets; requirements-build.txt; scripts/build_windows.py.
- [x] Tests for entry/version/resources and forbidden bundle inputs.
- [x] Isolated pinned Windows build environment, PyInstaller onedir; inspect inventory and launch actual frozen executable.
- [x] Record source/runtime/tool/dependency versions and hashes; commit tested build milestone.

## Checkpoint 3: installer/packaged acceptance
Files: packaging/windows/installer.iss; tests/packaging native harness; docs/WINDOWS_INSTALLATION.md.
- [x] Inno per-user installer, Start Menu and optional desktop shortcut, app-in-use refusal, owned-files-only uninstall; preserve config/reports.
- [x] Install into isolated test destination, launch frozen client against disposable API, test actual login/audit/history/export, themes/resize and shutdown.
- [x] Uninstall/reinstall acceptance and filesystem/security inventory; commit verified work.

## Checkpoint 4: release verification/publication
Files: build CI, verification docs/screenshots.
- [x] Independent engineering/UI reviews; fix confirmed defects with regression tests.
- [x] Complete SQLite/native and isolated MySQL/native suites plus packaged acceptance. Record unavailable clean-VM/signing/DPI checks as limitations.
- [x] CI pinned build/artifact job with isolated fictional backend; verify local outputs and commit.
- Publication: push normally, exactly one draft PR, hosted Windows/SQLite/MySQL/build CI on final HEAD. Keep unmerged. Final publication/run results belong in the PR and completion report so a documentation-only commit does not change the tested SHA after CI.

## Ledger
- Approved design b250fb4; checkout clean at start. Build/test tool installs are within authorized packaging work, not production deployment.
- Evidence: docs/WINDOWS_DESKTOP_PHASE3E_VERIFICATION.md; local full default 562/4 skips, isolated MySQL 567/0 skips, subsequent build-only focused checks 8/0; actual EXE HTTPS CRUD/history/export and installer lifecycle verified. Clean VM, signing and other actual DPI configurations remain release gates.
