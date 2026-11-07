# BHLI Audit Offline Android - Phase 6B

Development build only: use fictional records. [Manual transfer](OFFLINE_TRANSFER.md) and [reports, encrypted backup and same-platform restore](OFFLINE_REPORTS_AND_BACKUPS.md) are available. Keep a verified backup off the device: uninstalling/clearing app data or losing it can still lose unprotected records. This is not employee-ready software.

## Separate editions

- Online: package `com.bhli.audit.mobile`, entry `lib/main.dart`, flavor `online`; existing Version 1.0 release stays intact.
- Offline: package `com.bhli.audit.offline`, label `BHLI Audit Offline`, entry `lib/main_offline.dart`, flavor `offline`, version `1.0.0-offline-dev` (code2).
- Never install the offline build under the online package identity. Never uninstall an existing app to resolve a signer mismatch. The offline merged manifest must not request INTERNET.
- Retain the existing Flutter3.47.8 / Dart3.13.7 / AndroidSDK36 toolchain. New database dependencies are pinned in pubspec.yaml/pubspec.lock; no toolchain reinstall is needed.

## Behavior and attribution

First launch opens local profile setup and an empty SQLite database: zero audits and zero history. There are no seeded stations/drivers, accounts, default credentials, API settings or server startup.

Enter a locally declared auditor name. It is not authenticated or independently verified. Every new audit captures that name and profile UUID; later profile-name changes affect subsequent creations and the actor of later changes, never original Audited By snapshots. The operator can edit any active local record. Archiving preserves the record/history; archived records cannot be edited, restored or physically deleted by this phase.

The six editable fields retain current limits: driver/helper200, station150, plate30, remarks10000 Unicode code points. Driver/date/station/plate are required; helper/remarks may be null. Calendar dates are YYYY-MM-DD, years1000..9999. Audited By is the seventh business field and read-only in forms.

Unsent drafts and retry attempts are not persisted. After process death, inspect the saved list before starting another creation. The database preserves committed records/history; a lost UI callback does not mean rollback.

## Persistence and migrations

Native Android uses sqflite2.4.5. Host tests use sqflite_common_ffi2.4.5 against real temporary SQLite databases; FFI is a dev dependency, not the Android storage implementation. Its pinned sqlite3 3.5.2 build hook nevertheless bundles a native SQLite asset; wrapper license, core provenance and pinned binary-hash evidence are retained. No database encryption is enabled.

One admitted-operation queue owns each repository connection. A transaction includes the audit mutation, expected-revision check and history insertion. Closing rejects new work, waits for admitted work and then closes the handle. UI disposal cannot reverse a committed transaction. Creation reuses one lower-case UUIDv4 and compares the original CREATE payload on retry, including after later edits; mismatched UUID reuse conflicts.

Database path is the private app database directory plus `bhli_offline.db` (not a bundled database). Empty databases create schema 2 atomically; owned populated version-1 databases migrate transactionally without replacing their data. Unsupported/newer or foreign/incomplete schemas are refused without destructive downgrade/reset. Foreign keys are enabled on every connection. Android's reserved `android_metadata` table remains platform-owned. No Alembic/MySQL migration runs.

Schema1 has app_meta (application/installation identity), singleton local_profile (stable UUID/name), audit_records (internal sequence, UUID, exactly seven business values, profile UUID, UTC timestamps, revision, archive timestamp) and audit_events (UUID, audit FK, revision/action, actor UUID/name, immutable before/after snapshots). No account/session tables are imported. No history deletion method exists.

Phase 6D adds `auditor_identities` and `transfer_receipts`. Record origins and history actors reference the identity registry independently of the singleton current local profile. Original UUID/name snapshots remain unchanged on import and subsequent edits. Transfer uses the validated version-1 `.bhlitransfer` contract; raw database files are not an interchange format.

## Local verification commands

Use a fresh process with the existing project-local PUB_CACHE, GRADLE_USER_HOME, JAVA_HOME and ANDROID_HOME as documented in ANDROID_TOOLCHAIN.md. Do not change system execution policy.

From mobile:

```text
flutter pub get --enforce-lockfile
dart format --output=none --set-exit-if-changed lib test integration_test test_driver
flutter analyze --fatal-infos
flutter test --reporter expanded
flutter build apk --debug --flavor offline --target lib/main_offline.dart
```

The offline debug app intentionally has no INTERNET permission, including Flutter VM-service access. Use native Android instrumentation for real plugin acceptance instead of granting network access to support flutter drive. Only an owned emulator with no existing offline data is authorized here. See the final verification evidence for the exact commands/results; do not substitute an employee phone.

Online build/run commands now explicitly select `--flavor online`. `scripts/android_candidate.py` does so automatically and retains the ordinary online identity, target and candidate filename contract.

## Protection and limitations

The app-private database is not separately application-encrypted. Relying on an unlocked device or locally entered name does not establish verified identity or tamper-proof history. Native screenshot protection stays enabled in the ordinary app. Android cloud backup/device transfer rules exclude the offline database; use complete encrypted manual backups and keep this development build fictional-data-only.

There is no server, internet requirement, local server installer, local-login PIN/password scheme or cloud synchronization. Phase 6E adds readable UTF-8 reports and passphrase-encrypted complete backups, not authenticated employee accounts. The Windows offline peer and manual file transfer operate without a server. No production data/grants/migrations are accessed. Updates must preserve the same package, compatible signer, version progression and database migrations; a signature mismatch is an error, never permission to uninstall. Stable employee distribution signing remains a separately approved activity.

## Deferred phases

- 6C: Windows SQLite/offline workflows.
- 6D: shared transfer format, preview/import, duplicates and explicit conflict handling (implemented locally; publication requires approval).
- 6E: reports, backup and restoration implemented locally; see the verification report for actual acceptance and limits.
- 6F: comprehensive offline artifact/release acceptance.
- 6G: employee-ready cleanup and final zero-demo-data packaging.

No push, PR, release or later phase is authorized by Phase6B completion.

## Phase 6B verification evidence

The local host regression gate passed 265 Flutter tests, including 48 offline tests using real SQLite where persistence is involved. Formatting and full static analysis passed. Focused Python packaging/licensing contracts passed 43 tests. These overlapping suites are not a combined unique-test total.

The native test target is `integration_test/offline_test.dart` with a fresh UUID in `DAMS_OFFLINE_ACCEPTANCE_RUN`. It uses uniquely named fictional fixture databases, never `bhli_offline.db`, and rejects HTTP client construction. Build `app:assembleOfflineDebug` and `app:assembleOfflineDebugAndroidTest` with that target and `-Ptarget-platform=android-x64`, then invoke the installed `com.bhli.audit.offline.test/androidx.test.runner.AndroidJUnitRunner` twice in separate processes. The first invocation leaves one explicitly owned restart fixture; the second verifies its profile, revision, values and history before cleaning only that fixture. Never publish this test-target APK.

API36 native acceptance passed two scenarios in each of two separate app processes with airplane mode on and Wi-Fi/mobile data off. FIRST/SECOND markers verify persisted values, profile, revision and history; the original online APK checksum remained unchanged. Debug VM-service binding is denied by the intentionally absent INTERNET permission; native instrumentation does not require it. Native acceptance and ordinary candidate outcomes, exact artifact hashes and installed-package preservation are recorded under ignored `artifacts/phase6b/`. A host test pass alone does not establish Android acceptance. Physical-device, API24, TalkBack and final employee-release acceptance are not established by this phase.
