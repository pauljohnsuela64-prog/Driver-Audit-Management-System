# Phase 6E simplified completion scope

Operator direction supersedes the advanced Android recovery amendment. This is
an implementation scope record, not a request for another design approval.
Keep the existing single-user offline application and ordinary SQLite database.

## Keep and finish

- Recording, search/edit/archive/history and original auditor attribution.
- Manual Android/Windows transfers, Windows Excel and Android text reports.
- User-created encrypted full backups and explicitly confirmed full restoration.
- Existing queued database ownership, transaction rollback, safe file publication,
  backup validation and current-state recovery protection. Do not rebuild them.

No per-save encrypted generations, version chains, selector activation,
Keystore-managed storage, automatic multi-version recovery or new services.
The cancelled proposal and prior failing native evidence remain preserved.

## Practical corruption guarantee

1. The offline native adapter uses a nondeleting, throwing corruption handler;
   it does not call Android's destructive default handler. Existing files are
   not opened with create-if-missing semantics.
2. Existing zero/uninitialized stores, orphan sidecars and a corruption stop flag
   are not a fresh installation. Let the guarded writable open perform ordinary
   journal recovery, then check integrity/ownership/schema before admitting
   normal use. A read-only preflight must not block healthy hot-journal recovery;
   failed validation never initializes an empty replacement.
3. Corruption blocks normal current, queued and later operations, including cached
   cursor continuations. A fixed app-private stop flag also blocks new connections.
   Flag writes are best effort on failing storage; memory latching and startup
   integrity checks remain active. The flag is never automatically cleared.
4. Preserve the damaged main file where technically possible. Record native
   before/after hashes, but do **not** promise byte-identical WAL/SHM/journal or
   main bytes across normal checkpoint/close behavior. SQLite/storage can change
   these files independently of the handler. No automatic repair, deletion or reset.
5. Recovery uses a valid external same-platform encrypted backup. Changes after
   the last backup might be unrecoverable. If current storage cannot be safely
   read/protected, keep it intact and restore through the normal workflow on a
   fresh separate device/supported OS user; never clear/uninstall the damaged
   original or introduce a shipping path override.

Healthy restoration retains authenticated preview, explicit confirmation, a
verified current recovery backup and atomic record/history/profile/receipt
replacement. A failed or uncertain COMMIT is classified honestly, not called a
guaranteed rollback. No portable backup cryptography or business fields change.

## Verification order

1. Focused RED/GREEN host and native corruption tests: no main-file deletion or
   empty replacement, refusal/latch/restart, queued cursor, WAL/rollback modes,
   healthy startup and fresh install. Keep original stricter failures as evidence.
2. Actual Android encrypted backup/restore and document-provider failures; verify
   records, history, profile, identities, receipts, sequence and restart persistence.
3. Existing Windows backup/report native UI, followed by final default/isolated
   MySQL/Flutter/Windows regression checks once source stabilizes.
4. Clean-source offline and online build checks, licensing, installer/executable
   artifacts and isolated fictional-data acceptance. Report unexecuted installation
   or physical-device checks rather than inventing a PASS.

Meaningful local commits only; preserve Version 1.0 and all earlier work. No push,
PR, merge, release, production operations or next phase without authorization.
