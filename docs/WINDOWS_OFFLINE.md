# BHLI Audit Offline for Windows — Phase 6C

This is a development edition for fictional data only. There is no backup or restore yet. Losing the Windows profile, disk or database can permanently lose the only copy. Keep the original online application and its data intact.

## Launch and identity

From the existing desktop Python environment, run `python -m desktop.offline`. No API URL, backend, MySQL, Wi-Fi, internet, database credentials or server login is required. An unavailable Windows user-data location is an error; the app never falls back to storing live records beside installed binaries.

| Item | Offline edition |
| --- | --- |
| Window/product | BHLI Audit Offline |
| Entry | `desktop.offline` |
| Executable | `BHLIAuditOffline.exe` |
| AppUserModelID | `BHLI.Audit.Offline.Desktop` |
| Mutex | `Local\BHLI.Audit.Offline.Desktop.Running` |
| Installer GUID | `6C429C06-F81C-4C60-A5BC-C8A0E0987F5D` |
| Per-user installation | `%LOCALAPPDATA%\Programs\BHLI Audit Offline` |
| Database | `%LOCALAPPDATA%\BHLI Audit Offline\bhli_offline.db` |
| Development version | `1.0.0-offline-dev` |

The original `BHLIAudit.exe`, online entry, installer GUID, shortcuts, mutex and `%LOCALAPPDATA%\BHLI Audit` settings remain separate. Do not uninstall an existing edition to resolve an update problem. The offline installer never removes the separate database folder. Stable signed distribution and installation acceptance remain Phase 6F work; building a candidate is not proof of installation acceptance.

## Everyday workflows

First launch has zero profiles, audits and history events. Enter one local auditor name; it is self-declared, not verified employee identity or an ADMIN account. Local profile settings can rename it while preserving the profile UUID. New audits capture the current name; previous Audited By snapshots never change.

Dashboard, Driver Audits and Local profile reuse the existing navy/teal CustomTkinter shell, light/dark themes, collapsible navigation, 38-logical-pixel table, form layout, details, history and confirmation components. The offline entry constructs no API client, authentication session or HTTP worker. It does not load server `.env` files or online endpoint preferences.

Create/edit contains six editable fields; Audited By is the immutable seventh business field. Required driver/date/station/plate; optional helper/remarks. Lengths are driver/helper/name 200, station 150, plate 30, remarks 10,000 Unicode codepoints. Dates are exact calendar `YYYY-MM-DD`, years 1000–9999. Unicode and leading-zero plate strings are preserved. Shared Python/Dart fixture tests check the actual Android whitespace, NEL/BOM, null, date and length contract.

Search supports driver, plate and station with date bounds, sorting, pagination and optional archived records. Each creation retains one UUID and normalized payload while a save is uncertain; retry reuses both. It never automatically retries a write. After process death, inspect existing records before creating again. Edits refetch and check the expected revision. Stale edits require explicit comparison/reload; they do not overwrite a newer record silently. Archiving confirms, preserves history and makes the audit read-only; there is no physical delete or restore.

Confirmed saves remain distinct from a failed subsequent list refresh. Dirty unsent forms require confirmation before leaving. A dispatched save cannot be described as canceled or rolled back just because its UI closes.

## SQLite and shutdown

The built-in `sqlite3` repository owns schema version 1: `app_meta`, singleton `local_profile`, `audit_records` and `audit_events`. Record, profile, event and installation IDs are UUIDv4; timestamps are UTC; revisions increase with committed changes. Every audit mutation and history insert shares one `BEGIN IMMEDIATE` transaction. Read counts/items share a read snapshot. Foreign keys are enabled. A no-op edit does not add history. Original CREATE payloads remain available for safe same-UUID replay after later edits.

Initialization creates schema 1 only for an empty version-0 database. Unsupported/newer, foreign, corrupt or incomplete databases are refused without reset, deletion or downgrade. Invalid stored profile attribution is rejected before it can create more unusable records. Locks, full storage, read-only files and failed transactions are reported safely. SQL inputs are parameterized; sort identifiers are allowlisted.

One non-daemon worker creates, uses and closes its SQLite connection on its owning thread. GUI callbacks are delivered only by the GUI thread. Read invalidation cannot discard an admitted mutation. Close stops new admissions, drains submitted work and closes the connection before destroying Tk. Pending failures and close failures must be acknowledged; closing does not turn an unconfirmed save into a success.

Windows uses its own application identity in metadata. The logical columns, UUIDs, snapshots and normalization are compatible foundations for future transfer; copying raw Android/Windows database files is **not** a supported interchange format. Phase 6D must define import receipts, provenance, validation and a versioned migration instead of replacing databases.

## Reporting and later phases

The original Excel engine/source is preserved. Offline report controls are intentionally absent. Future reports can consume immutable `LocalAudit` pages through the local repository/worker seam; snapshot consistency and complete report generation must be implemented and tested in Phase 6E. There is no daily/weekly/monthly/custom offline reporting or backup hidden behind a placeholder.

Phase 6D: manual transfer. Phase 6E: reports and backup/restore. Phase 6F: signed distribution and installation/release acceptance. Phase 6G: employee-ready cleanup. None is implemented by Phase 6C.

## Local verification and candidates

Use fictional temporary test databases only. Native tests are opt-in with `DAMS_DESKTOP_GUI_TESTS=1`; serialize heavy test suites, GUI acceptance and builds. Do not disable the developer's host network or connect to production to prove offline operation; tests block socket creation in the offline process and use no running server.

The shared contract lives in `mobile/test/fixtures/offline_contract.json`, exercised by new Python tests and `mobile/test/offline/windows_contract_test.dart`; Android application code remains unchanged.

Build from committed, reviewed source using the retained hash-locked Windows build environment:

```text
.venv-build\Scripts\python.exe -m scripts.build_windows_offline --iscc local\inno710\ISCC.exe --output-root dist\phase6c-<fresh-checkpoint>
```

Outputs are a folder executable, portable ZIP and unsigned per-user installer. The builder refuses nonempty output directories and inspects modules, data exclusions, notices, identity and the retained SQLite DLL hash. It never installs, uninstalls, deploys or publishes a candidate. Exact source hashes, candidate checksums, executed tests and acceptance gaps are recorded in ignored `artifacts/phase6c/` evidence.

No application-level database encryption or independently verified local identity is provided. Windows restart, physical employee-device and installer roundtrip acceptance must not be claimed merely from unit tests or a successful build.
