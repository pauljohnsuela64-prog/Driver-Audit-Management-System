# BHLI Audit Offline for Windows — Phase 6C

This is a development edition for fictional data only. Complete encrypted backup and same-platform restore are described in [Offline reports and backups](OFFLINE_REPORTS_AND_BACKUPS.md). Keep a verified copy off this computer: losing the Windows profile, disk or database can still lose unprotected records. Keep the original online application and its data intact.

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

The built-in `sqlite3` repository owns schema version 2: `app_meta`, singleton `local_profile`, `audit_records`, `audit_events`, `auditor_identities` and `transfer_receipts`. Record, profile, event and installation IDs are UUIDv4; timestamps are UTC; revisions increase with committed changes. Every audit mutation and history insert shares one `BEGIN IMMEDIATE` transaction. Read counts/items share a read snapshot. Foreign keys are enabled. A no-op edit does not add history. Original CREATE payloads remain available for safe same-UUID replay after later edits.

Initialization creates schema 2 for an empty database or transactionally migrates a validated owned version-1 database, preserving records, events, sequence and current profile. Unsupported/newer, foreign, corrupt or incomplete databases are refused without reset, deletion or downgrade. Invalid stored profile attribution is rejected before it can create more unusable records. Locks, full storage, read-only files and failed transactions are reported safely. SQL inputs are parameterized; sort identifiers are allowlisted.

One non-daemon worker creates, uses and closes its SQLite connection on its owning thread. GUI callbacks are delivered only by the GUI thread. Read invalidation cannot discard an admitted mutation. Close stops new admissions, drains submitted work and closes the connection before destroying Tk. Pending failures and close failures must be acknowledged; closing does not turn an unconfirmed save into a success.

Windows retains its own application identity in metadata. [Manual transfer](OFFLINE_TRANSFER.md) uses a shared validated `.bhlitransfer` package with preview, new-only import, exact duplicate detection, conflict skips and atomic receipts. Imported origins/history actors remain independent of the current local profile. Copying raw Android/Windows database files is **not** a supported interchange format.

## Reporting and later phases

The original online Excel engine remains separate. Phase 6E adds snapshot-consistent local Excel reporting and complete encrypted backup/restore. See [workflows, limits and recovery guidance](OFFLINE_REPORTS_AND_BACKUPS.md).

Phase 6D adds manual transfer locally; publication requires approval. Phase 6E reporting/backup is implemented locally; Phase 6F signed distribution and Phase 6G employee-ready cleanup remain deferred.

## Local verification and candidates

Use fictional temporary test databases only. Native tests are opt-in with `DAMS_DESKTOP_GUI_TESTS=1`; serialize heavy test suites, GUI acceptance and builds. Do not disable the developer's host network or connect to production to prove offline operation; tests block socket creation in the offline process and use no running server.

The shared contract lives in `mobile/test/fixtures/offline_contract.json`, exercised by new Python tests and `mobile/test/offline/windows_contract_test.dart`; Android application code remains unchanged.

Build from committed, reviewed source using the separate hash-locked offline
build environment. Preserve the original online `.venv-build` environment:

```text
.venv\Scripts\python.exe -m venv .venv-offline-build
.venv-offline-build\Scripts\python.exe -m pip install --only-binary=:all: --require-hashes -r requirements-offline-build.lock
.venv-offline-build\Scripts\python.exe -m pip check
.venv-offline-build\Scripts\python.exe -m scripts.build_windows_offline --iscc local\inno710\ISCC.exe --output-root dist\phase6e-<fresh-checkpoint>
```

Outputs are a folder executable, portable ZIP and unsigned per-user installer. The builder refuses nonempty output directories and inspects modules, data exclusions, notices, identity and the retained SQLite DLL hash. It never installs, uninstalls, deploys or publishes a candidate. Exact source hashes, candidate checksums, executed tests and acceptance gaps are recorded in ignored `artifacts/phase6c/` evidence.

No application-level database encryption or independently verified local identity is provided. Windows restart, physical employee-device and installer roundtrip acceptance must not be claimed merely from unit tests or a successful build.
