# Offline audit transfer — fictional development testing

BHLI Audit Offline can copy selected audits and their complete available history
between the Windows and Android offline applications. Neither application needs
an API, server, Internet connection or MySQL. Copy `.bhlitransfer` files between
devices using a method you control, such as USB or Bluetooth.

**Use fictional records only.** Files are plaintext and are not authenticated or
encrypted. Names are locally declared identities, not verified employee accounts.
The checksums detect damage; they do not prove who created a file.

## Before testing

Use transfer-capable development builds on both devices. Their local SQLite
schema is version 2. The first open validates and transactionally upgrades an
owned version-1 database without resetting its profile, audits or history. An
incompatible/corrupt database is refused, not repaired or replaced. Older builds
cannot open a version-2 database. Do not test against real employee databases.

Keep each device's existing local auditor profile. Importing a file never changes
that profile. Original audit identities/names and each history actor's identity/
name travel with the audit. A later local edit records the current local actor
without changing the original Audited By snapshot.

## Export

1. On Windows, open Driver Audits → **Transfer audits** → **Prepare export**.
   On Android, select **Export Audits** from the offline audit list.
2. Choose all records, or an inclusive audit-date range. Archived records are
   included. Preparing the snapshot does not modify any audit.
3. Review the prepared record count, then select a new destination filename.
4. Wait for confirmed completion before copying the file to another device.

Windows uses its native save dialog. An existing destination is never replaced,
including a file appearing after the dialog closes; select a different name.
Android uses its system document picker. Choose local storage when offline;
cloud providers may require connectivity and are not needed or assumed to work.
A new document is created; completion requires a successful copy, close and
read-back checksum. If cleanup after a failed save is unavailable, an explicit
warning identifies the possibility of an incomplete file. Do not distribute it.

Canceling selection saves nothing. Canceling active work requests a stop; wait
for the final result. A completion already committed is not reversed by a late
cancel. Empty exports are valid and contain zero audits/history events.

## Import

1. On Windows, open Driver Audits → **Transfer audits** → **Open transfer file**.
   On Android, select **Import Audits**. Choose the copied `.bhlitransfer` file.
2. Wait for validation and review the counts:
   - **New:** a previously unseen audit identity with a valid complete history.
   - **Already here:** exactly the same audit and complete history; skipped.
   - **Different version:** the identity exists but content/history differs;
     skipped without changes.
3. Explicitly confirm **Import new records only**, acknowledging any conflicts,
   or cancel. No preview automatically imports records.
4. Wait for confirmed results, then review the refreshed audit list/history.

Selected eligible records, identities, histories and the package receipt commit
together or roll back together. If local data changed after preview, review a
fresh preview before proceeding. Reimporting the same file cannot duplicate its
records or events. Reusing a history/package identity for different content is
an error, not an opportunity to overwrite data.

**Later edits to an already imported audit do not propagate by reimport.** Higher
revisions or newer timestamps do not authorize replacement. There is no automatic
reconciliation, restore, permanent deletion, network synchronization or merging.

## Limits and failures

Format version 1 is a STORE-only ZIP with exactly `manifest.json`, `audits.ndjson`
and `events.ndjson`. It carries versioned metadata, UUIDs, UTC timestamps, selected
date range and SHA-256 content hashes. The documented wire rules and golden
fixtures establish Python/Dart compatibility; never exchange raw database files.

Initial ceilings: 32 MiB package/expanded data, 2,000 audits, 10,000 history events,
64 KiB manifest, 256 KiB per JSON line and nesting depth 6. Excess fails the whole
operation; narrow the date range. A single audit whose history exceeds a limit
cannot be partially transferred. No silently truncated success is possible.

Damaged/unsupported files, invalid history, storage errors or conflicting history
identities do not authorize partial insertion. Correct the stated issue and
retry the same file. If the app was interrupted during final completion, inspect
records or reimport that file; do not assume cancellation undid a committed write.
Keep Windows open until admitted writes drain and any failure is acknowledged.

Transfer files are **not full backups**: they exclude application configuration,
the receiving profile and unrelated records, and cannot overwrite an existing
audit to restore an old version. Backup/restore, reporting and employee-release
preparation are later phases. No real data transfer or release is authorized.

## Developer verification

Focused Python contracts: `python -m pytest tests/desktop/offline -q` (native tests
are opt-in). Flutter offline contracts: `flutter test test/offline`. Shared
fictional fixtures are under `mobile/test/fixtures/transfer/`; entry bytes have
host-independent Git attributes. Never add a user's database or secrets as a
fixture. See the Phase 6D approved design and implementation plan for full
regression, migration failure, cross-platform, resource and native acceptance gates.
