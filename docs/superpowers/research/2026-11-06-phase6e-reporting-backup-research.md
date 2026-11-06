# Phase 6E — research and architecture findings

Date: 2026-11-06. Baseline `d613dae935ddbb3607b828feccf48df1736241e4`.
Research/design only: no library installation, implementation, encryption probe,
database operation, native acceptance or performance benchmark was performed.

## Repository evidence

| Existing source | Design implication |
|---|---|
| `desktop/reports.py`, `tests/desktop/test_reports.py` | XlsxWriter 3.3.0 already writes literal text, disables automatic formula/URL/number interpretation and tests actual workbook XML. Reuse these policies/test cases, not REST fetching/token deadlines. |
| `scripts/build_windows_offline.py` | Explicitly excludes `desktop.reports`, `desktop.export_ui` and online/server modules. An offline writer must remain network-independent; importing the online exporter is not safe reuse. |
| `desktop/offline/repository.py`, `worker.py` | Existing connection/thread ownership, explicit read/write transactions and admitted-operation drain must be preserved. |
| `mobile/lib/offline/sqlite_repository.dart` | Queue/transaction ownership already exists; one local snapshot can cover all tables without copying live files or passing native transactions to an isolate. |
| `desktop/offline/schema.py`, `mobile/lib/offline/schema.dart` | v2 state includes metadata, profile, registry, records, events, receipts and audit sequence; Android native metadata differs. Backups must preserve raw history JSON/offset timestamp spellings while validating their semantics. |
| Phase 6D transfer stores/codecs/native bridge | Strict parsing/history/file tests can inform backup internals. Transfer payloads/permissions/32MiB limits are purpose-specific and cannot simply become full backups. |
| Current offline bootstrap/profile screens | Empty storage is a supported state; unreadable storage fails before profile UI. Corrupt-current automatic restoration cannot be implied by adding a profile button. |

Current offline filter contracts contain driver, plate, station, inclusive dates,
include-archived, sort and pagination. There is no existing local-auditor filter.
No new business fields or schema version are proposed.

## Primary-source findings and engineering inferences

1. SQLite documents transactional atomic commit and the storage synchronization
   assumptions behind it. WAL committed data may live outside the main database
   file. **Inference:** use logical reads through one transaction, never a live
   main-file copy; restore known rows in one transaction and qualify durability
   claims by actual journal/OS testing. [Atomic commit](https://www.sqlite.org/atomiccommit.html),
   [WAL](https://www.sqlite.org/wal.html).
2. SQLite's online backup API can produce a consistent copy; it is a real
   alternative to manual copying. **Inference:** it is useful in Python but does
   not remove the need to design matching sqflite/native ownership and restore
   activation. A platform-bound logical snapshot is the proposed common path.
   [SQLite backup API](https://www.sqlite.org/backup.html).
3. The synchronous pragma differentiates FULL and EXTRA durability behavior and
   journal modes; unknown pragmas may be silently ignored. **Inference:** configure
   and read back durability before the restore transaction; require native tests,
   not a guarantee inferred from issuing a statement.
   [SQLite pragmas](https://www.sqlite.org/pragma.html#pragma_synchronous).
4. OWASP prefers Argon2id and lists the 19MiB/2-pass/1-lane configuration; it also
   documents PBKDF2-HMAC-SHA256 at 600,000 iterations. This is password-storage
   guidance, not a certification of this backup product. **Proposal:** use the
   memory-hard configuration with strong passphrases and actual target benchmarks.
   [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
5. PyCA exposes Argon2id derivation and AEAD primitives. Nonce reuse with a key
   is unsafe; AAD is authenticated but not encrypted. **Proposal:** fixed allowlisted
   work factors, independent fresh salts/nonces and the complete fixed header as
   AAD. Do not infer identity authentication from successful decryption.
   [PyCA KDFs](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/),
   [AEAD](https://cryptography.io/en/latest/hazmat/primitives/aead/).
6. Published PyPI metadata identifies stable `cryptography 50.0.2`, Windows
   stable-ABI distributions and Apache-2.0 OR BSD-3-Clause licensing. `/latest/`
   API documentation currently points to 51.0.0-dev1, so it is not a version pin.
   **Unverified:** execution under retained CPython3.14/PyInstaller, wheel/native
   closure, runtime Argon2 support and current vulnerability audit. These are
   implementation gates; no package was downloaded or installed here.
   [PyPI project/distributions](https://pypi.org/project/cryptography/),
   [installation guidance](https://cryptography.io/en/latest/installation/).
7. Dart `cryptography 2.9.0` documents pure-Dart Argon2id and AES-GCM support and
   Apache-2.0 licensing. Acceleration is optional; native speed is not automatic.
   **Proposal:** start with that exact candidate, isolates, known-answer and
   cross-library tests; benchmark before considering another plugin.
   [Package](https://pub.dev/packages/cryptography),
   [Argon2id](https://pub.dev/documentation/cryptography/latest/cryptography/Argon2id-class.html),
   [AES-GCM](https://pub.dev/documentation/cryptography/latest/cryptography/AesGcm-class.html),
   [license](https://pub.dev/packages/cryptography/license).
8. Android SAF provides user-mediated access without broad storage permissions.
   Create-document workflows use a new output; providers still have their own
   behavior/failure semantics. **Inference:** retain the exact URI ownership and
   readback/cleanup discipline from native Phase 6D acceptance, without treating a
   provider as an atomic local filesystem.
   [Android document access](https://developer.android.com/training/data-storage/shared/documents-files).

## UX guidance actually used

UI UX Pro Max targeted query `destructive confirmation recovery password`
(`--domain ux`) returned Confirmation Dialogs, Password Visibility and Error
Recovery guidance. Applied narrowly: default Cancel, explicit replacement
acknowledgement, show/hide controls, and actionable failure/recovery states.
Existing navy/teal themes, sidebar and touch/large-text conventions remain.
No new design system or GUI was generated.

Superpowers brainstorming established the design-first gate and builder review;
Codebase Design informed snapshot/codec/publication seams and small interfaces.
No implementation-planning/TDD execution is claimed for this design assignment.

## Decisions and non-claims

The operator selected Android summary + UTF-8 readable report and assisted
corrupt-current recovery into a fresh same-platform instance; CSV/XLSX on Android
and automatic corrupt-store repair are not proposed. Other choices—including
crypto suite, resource ceilings, same-platform identity replacement and mandatory
pre-restore recovery—remain subject to final operator design approval.

The 64MiB backup limit is a proposed safety ceiling, not a measured capability.
Do not reuse Phase 6D's 597MiB Android memory measurement as a Phase 6E benchmark.
Source-authenticated/encrypted transfer, backup password recovery, database
encryption and production/employee rollout remain separate security decisions.
