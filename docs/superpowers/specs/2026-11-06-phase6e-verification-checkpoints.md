# Phase 6E — verification and proposed checkpoints

Status: design proposal only. Detailed implementation planning follows approval.
Use only fictional temporary databases, test-owned data directories and the
separate offline package. Never inspect employee databases, change installed
applications, uninstall an existing app, deploy or publish release binaries.

## Checkpoint outcomes

| Checkpoint | Coherent deliverable / verification gate |
|---|---|
| A — full-state/report seams | Define immutable applied filters, complete snapshot stream/state digest, same-platform compatibility and maintenance admission; real SQLite snapshot/race/empty-state tests first |
| B — Windows reporting | Offline XLSX and safe publication; XML/type/formula/link validation, all rows/filters, Unicode/long remarks, cancellation/full disk; native compact/light-dark/keyboard checks |
| C — Android reporting | Summary and UTF-8 text; exact counts/top-station reconciliation and all matching rows, safe multiline text; widget 320dp/200%/keyboard/theme and native SAF acceptance |
| D — encrypted full backup | Exact envelope/payload, library known-answer and cross-library vectors, all owned-state roundtrip, resource/security/notice gates; no restore UI until authenticated candidate validation passes |
| E — restore core | Recovery proof + prestate revalidation + one transaction + reopen, tested with real SQLite faults/process death; review safety before exposing destructive action |
| F — restore UI/native | Explicit replacement preview, accessible confirmations and phase-truthful cancellation; real Windows/Android failure/restart drills and ordinary frozen/offline APK acceptance |
| G — consolidated review | Full default/isolated-MySQL/Flutter/Windows regressions, both online/offline builds and notices, independent engineering/security/UX review; publication remains separately authorized |

Create meaningful local commits at coherent verified milestones; no artificial
commit count. A material crypto/restore/scope change returns for approval. Keep
all existing tests and builds; do not weaken or skip tests to meet this design.

## Reporting test matrix

- Actual SQLite transactions: a concurrent second connection changes rows between
  reads; the export still has a coherent original/new snapshot, never a mixture.
  Count and rows match. Do not treat separately paged queries as a snapshot.
- Applied vs edited filters, all/date range inclusive boundaries, search escaping,
  station, stable sorts/ties, archive choices, zero matches, original audited-by
  name after profile changes, more than one result page.
- Nine exact Windows columns, two sheets, text types for identifiers, Unicode,
  optional blanks, long/multiline remarks and control characters. Values starting
  `= + - @` or URLs must not create formulas/hyperlinks/external relationships;
  no VBA/macro payload. Open an actual workbook in Excel/compatible software if
  available; disclose when not executed.
- Android summary active+archived totals, displayed-scope count, top-ten plus
  Other reconciliation; text report matches all rows, preserves leading zeros,
  Unicode and safe multiline labels. No CSV/Excel roundtrip claim for `.txt`.
- Cap boundaries, one row past cap, oversized text, near-limit memory/temp disk,
  finalization growth, disk-full/read-only/path races, unsupported volume/no-link
  behavior, existing destination refusal and completed-output checks.
- Cancellation before/after snapshot/publication, UI disposal/window close,
  stale callbacks, retry and retained filters. A completed save is not undone.

## Backup and crypto test matrix

- Empty owned v2 database with no profile; populated database including archives,
  imported origin identities, unused registry entries, profile/installation UUID,
  complete events/raw JSON strings/offset timestamps, receipts, sequence gaps and
  high-water mark. Compare all owned rows exactly after snapshot/restore.
- Schema ownership, malformed rows/profile/receipt/sequence, extra tables/triggers,
  orphan references, duplicate event UUIDs/revisions, bad CREATE/origin/history,
  no-op updates, invalid Unicode, duplicate inner/outer JSON keys and depth.
- Deterministic **test-only** Argon2id RFC9106 and AES-GCM published vectors,
  cross-Python/Dart envelope vectors, empty and maximum supported payload, exact
  AAD bytes/endianness/password UTF-8. Test randomness injection cannot enter
  ordinary builds. Different encryptions of same state differ in salt/nonce.
- Wrong password and every tag/header/ciphertext tamper; truncation, appended
  bytes, unsupported suite/version/schema/platform, hostile sizes/iteration/memory
  fields rejected before expensive allocation. No parsed plaintext before tag.
- Backup is all-state regardless of UI filters, including archived/older records.
  Cap failure must not produce a partial advertised backup. No bundled database,
  password, key, fixture or recovery file in ordinary artifacts/notices.
- Private staging permissions, orphan cleanup path/symlink containment, locked
  destination, full disk, cancellation, timeout, retained encrypted recovery and
  failed deletion warning. Imported SAF URIs are never deleted.

## Restore and recovery matrix (must use real SQLite)

For each failure, assert every original owned row, sequence, schema and install
identity remain intact **or** the entire explicitly committed restored state is
present—never independent partial table states:

1. Wrong password/unsupported candidate; preview cancellation; no confirmation.
2. Recovery creation/encryption/fsync/close/publication/readback failure or user
   cancellation; source and current database never modified.
3. Another admitted write before maintenance; second connection changes state
   after preview/recovery; old preview rejected with no restore writes.
4. Busy lock, injected IO/FULL on each dependent table/receipt/sequence write,
   failed validation, failed COMMIT and post-COMMIT reopen failure. Also inject
   a real successful COMMIT followed by an exception/lost result: classify
   ORIGINAL/RESTORED/UNKNOWN by validated digests, never promise rollback or
   automatically retry a completed replacement.
5. Terminate a separate app/helper process at: plaintext stage, recovery publish,
   before BEGIN, after deletes, mid-insert, before COMMIT, immediately after
   COMMIT and before marker/UI cleanup. Reopen through the real application;
   check FK/integrity/state digest. Cover WAL and rollback journals.
6. Empty restore, archived histories, imported identities, profile replacement,
   installation UUID restoration, receipt/sequence preservation, second restore
   and fresh creation after restoration; no accidental identity regeneration.
7. Same-platform replacement-device simulation allowed; opposite platform app ID,
   arbitrary raw SQLite and future schemas refused. Transfer import still keeps
   recipient profile and cannot replace existing records.
8. Multiple cooperating app instances acquire the per-data-directory lease before
   opening SQLite and retain it through drained shutdown; old
   builds/external tools are an explicit operator precondition, not a claimed
   lock guarantee. Native OS lock/process-death behavior verified separately.
9. Required marker written before replacement; missing/corrupt/stale marker,
   inaccessible current database, damaged scratch, missing recovery file and
   lost-password instructions all fail closed without empty reinitialization
   or automatic retry. Startup reads recovery evidence before cleaning stages.
   Corrupt-current assisted-recovery instructions preserve original files and
   direct a valid backup only to a separately established fresh same-platform
   target; do not claim automatic corrupt-database repair was tested.

Mock-only rollback tests are insufficient. Process-kill tests are not physical
power-cut tests; report that distinction and the actual journal/synchronous
settings/platform versions.

## Native and packaging acceptance

- Windows: ordinary frozen offline executable on fresh isolated data path;
  create/edit/archive/history, Excel export, backup, restore, close/restart;
  compact/maximized, 100/150/200% DPI where supported, both themes, keyboard focus,
  cancelled dialogs, open/locked/full destination and no-overwrite behavior.
- Android: ordinary separate offline APK and instrumented test variant on a
  test-owned read-only API36 AVD; genuine SAF new/save/open/cancel and fault
  providers; 320dp/landscape/200% text, background privacy, rotation, force-stop,
  no Internet permission or broad storage grant, restored profile/list refresh.
- Benchmark fixed KDF/encrypt/decrypt/validate/backup/restore separately: time,
  peak RSS and disk, UI responsiveness and cancellation latency. Reuse 2 GiB API36
  configuration for comparison, but measure Phase 6E independently. API24 and
  physical-device tests are gates to claims for those devices, not assumed passes.
- Clean-machine/installer roundtrip only in disposable Windows infrastructure,
  preserving online/offline product IDs/data directories. Do not alter the
  developer's actual installation. Android identities must coexist without
  replacing online APKs or existing devices.
- Review pinned Python wheel hashes and Argon2/OpenSSL support in the actual
  frozen artifact; Dart licenses, native/transitive notices and existing online
  candidate notices. Both apps must work without installed developer tools or
  API configuration. No real data or signing secrets may enter artifacts.
- Run full SQLite, isolated MySQL, Flutter and native Windows regressions once
  after relevant implementation stabilizes. Preserve all five existing hosted
  jobs; add meaningful offline crypto/package coverage as required without
  silently skipping missing-dependency tests. No automatic CI/release publication
  is authorized by this design assignment.

## Acceptance record

Implementation must record exact source commit, commands, counts/skips, device/
OS/SDK/library versions, memory/time/disk measurements, checksums, native evidence
and unexecuted cases. Do not add overlapping test totals or present preserved
Phase 6D results as executed Phase 6E verification.

No Phase 6E application, crypto, backup, restore or report test has been executed
in this design-only assignment. Design review and document checks are distinct
from implementation/native acceptance. Stop for operator design approval.
