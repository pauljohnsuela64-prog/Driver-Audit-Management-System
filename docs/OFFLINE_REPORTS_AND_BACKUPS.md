# Offline reports, encrypted backup and recovery

Development edition: use fictional data only. These functions need no API,
server, online account or MySQL connection. The original online applications
remain separate. Native and release acceptance must be assessed from the Phase
6E verification report; these instructions are not an employee-deployment claim.

## Choose the correct operation

| Operation | Purpose | Important distinction |
|---|---|---|
| Report | Readable copy of the applied audit query | Unencrypted; cannot restore the application |
| Transfer `.bhlitransfer` | Merge compatible audit histories between devices | Unencrypted and unauthenticated; does not replace the local profile |
| Backup `.bhlibackup` | Encrypted complete state of one installation | Includes profile and installation identity; same-platform restore only |
| Restore Backup | Replace the entire current state from a verified backup | Requires a separately saved and verified current recovery backup first |

## Reports

On Windows, open **Driver Audits**, apply the desired driver, plate, station,
inclusive date range, archive and ordering filters, then choose **Export to
Excel**. The genuine XLSX includes every match, not just the visible page: the
seven business fields, Record ID and Active/Archived status. Identifiers and
user text remain literal strings, including leading zeros and formula-like
values. A report-information sheet describes its point-in-time query.

On Android, apply filters before choosing **View report summary**. Counts
distinguish all-status matches, active, archived and displayed records. The
station breakdown includes an Other total when needed. **Save text report**
takes a fresh snapshot, updates the displayed counts and saves readable UTF-8
text through Android Files. Share it using Files afterward if required.

Both readers use consistent local SQLite transactions. This does not promise
nonblocking concurrent writers. Reports fail as a whole beyond 20,000 rows,
100 MiB of text or ten minutes of active work; narrow the filters instead of
assuming a truncated file is complete. Choose a new filename. Cancellation
does not undo an already completed file save. Protect unencrypted reports.

## Create a complete encrypted backup

1. Open **Local profile → Backup & restore**, also available during empty setup.
2. Choose **Create Backup** and enter/confirm a unique 15–128 character
   passphrase. Spaces matter; passwords are not trimmed or normalized.
3. Select a new `.bhlibackup` destination and wait for verified completion.
4. Keep an additional protected copy off the device and store the passphrase
   separately. A backup on the same failing disk is not disaster recovery.

No list filter limits a backup. It includes all records, archived records,
complete history, original auditor identities, import receipts, local profile,
installation identity and sequence metadata. It does not include API settings,
online accounts, software installations or unrelated user files.

The versioned envelope uses Argon2id (19,456 KiB, two passes, one lane) and
AES-256-GCM, fresh random salt/nonce and authenticated framing. A complete
logical payload may not exceed 64 MiB. Unsupported platforms/schemas, excessive
work factors, modified files and wrong passwords are refused. Windows backups
restore only to Windows; Android backups only to Android. Use Transfer for
cross-platform audit merging.

Passphrases and keys are memory-only, never settings or logs. Immutable strings,
garbage collection and OS paging prevent a secure-erasure guarantee. Lost
passphrases cannot be reset. Live SQLite and reports remain unencrypted. Backup
encryption does not authenticate an employee or prove the file is the newest
valid backup; an unlocked compromised device remains outside this protection.

## Restore safely

1. Close other app copies and older versions. Finish or discard unsent drafts.
2. Select the backup, enter its passphrase and review its authenticated profile,
   installation identity and counts against the current device.
3. Re-enter that passphrase to save an encrypted **current recovery backup** to
   a new destination. The application verifies actual destination readback and
   a retained private encrypted copy before enabling final confirmation.
4. Read the complete replacement warning. Cancel is the default. Explicitly
   acknowledge replacement before confirming.
5. Wait for the verified outcome. Retire duplicate active copies of a restored
   installation identity; restoring an old backup deliberately returns to old
   data. Transfer conflicts must not be used to simulate restore.

Restore replaces all six owned tables and the audit sequence in one SQLite
transaction, preserving the existing schema and native platform metadata. A
required durable marker and independent encrypted evidence precede replacement.
It never swaps a live database file or executes schema supplied by a backup.

- **ORIGINAL:** the complete previous state is verified; a fresh explicitly
  confirmed attempt is needed if replacement is still desired.
- **RESTORED:** the intended complete state is verified, including after a lost
  COMMIT acknowledgement. No automatic reversal or retry occurs.
- **UNKNOWN:** neither state can be established or evidence is untrustworthy.
  Local changes are blocked. Preserve the database, sidecars and encrypted
  evidence; follow assisted recovery guidance.

Failed marker cleanup can also block changes despite a known complete outcome.
Retained encrypted evidence is not automatically deleted. Private recovery
storage is bounded; if it fills, new work is refused. Seek assisted review
instead of deleting a pending marker or recovery files to bypass protection.

## Unreadable current database

Android keeps ordinary SQLite storage. A small offline-only native correction
refuses corruption instead of calling Android's deleting handler or silently
initializing an empty replacement. A `.bhli-corrupt` stop flag blocks later
opens; it is not a backup or a repair tool. Do not delete it to bypass the warning.
When storage itself is failing, writing the flag is best effort; current-process
blocking and startup integrity validation remain in force.

This does not promise byte-identical preservation of a live database and its
WAL/SHM/journal files. Normal SQLite recovery/checkpoint/close may change these
files. Keep whatever remains for inspection. There are no encrypted generations,
automatic version chains or automatic repair. **Changes made after your last
backup might be unrecoverable.** Create and retain external backups regularly.

Do not clear app data, uninstall, overwrite, move or delete the damaged database
or its SQLite sidecars. Retry only after closing other copies or correcting
storage access. If it remains unreadable, preserve the original installation
and use a verified backup in a **fresh same-platform instance**: another Windows
OS user/PC, or another Android device/supported OS user. Use that instance's
normal private storage, protect its initial state and complete normal restore
there. There is no shipping arbitrary database-path switch or automatic
destructive recovery. Keep the damaged original for assisted inspection.

File flush/readback and transactional checks rely on the storage provider and
OS honoring durability requests. They do not establish survival of physical
power loss or defective hardware. Android requests local document providers;
provider-specific/cloud/removable-media behavior needs separate acceptance.
Physical-device/API24, clean-machine installation and installer roundtrip
acceptance must not be inferred from host tests or an API36 emulator.
