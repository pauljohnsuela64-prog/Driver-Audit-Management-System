# Phase 6E Android corruption safety gate

Status: **BLOCKED — preservation-design amendment required before continuing**.
Fictional development fixtures only. This is not publication clearance.

The current Phase 6E branch starts this review at
`c84e471c403cb5a745d39498e76dbd1409c22a99`. Existing commits and unfinished
Android backup work are preserved. No production, installed-user application,
GitHub publication, release or signing change is authorized by this review.

## Reproduced baseline

Pinned `sqflite_android 2.4.5` uses Android's three-argument writable
`SQLiteDatabase.openDatabase`, hence the platform default corruption handler.
Its read-only path already supplies a nondeleting handler. The upstream
`Database.java` SHA-256 is
`b89bf89e17cb8d2db16a948940714056d6e49c5559d943f72c0b124e214d7790`.

Actual API 36 instrumentation: **3 tests, 2 failures**.

| Case | Observed result |
|---|---|
| Writable corrupt-header startup | Original 4,096 bytes replaced by a 12,288-byte database; WAL and SHM removed; journal truncated |
| Writable runtime b-tree corruption | Damaged original database deleted |
| Read-only corrupt-header startup | Database and all three sentinel sidecars retained byte-for-byte |

The test stores paths, lengths and SHA-256 values before opening, and retains
independent original fixture copies. Full before/after manifests and original
copies were pulled off the disposable read-only emulator before shutdown:
`artifacts/phase6e/android-corruption-evidence-9efd38c3-131f-4002-ab7a-b67ae57fdce3/`.
The evidence archive SHA-256 is
`f53aab77d523dd27339177f4538c42b3d359eb8027710124fb86029a0f232d39`.
Compilation and successful instrumentation command transport are not test PASS.

This is consistent with the documented [Android default handler](https://developer.android.com/reference/android/database/DefaultDatabaseErrorHandler)
and [AOSP implementation](https://android.googlesource.com/platform/frameworks/base/%2B/master/core/java/android/database/DefaultDatabaseErrorHandler.java).
The actual test evidence, rather than current upstream source alone, establishes
the observed behavior on the tested image.

## Narrow correction under verification

- Keep version 2.4.5; vendor the reviewed official 61-file source with exact
  upstream hashes, original BSD-2-Clause license and an explicit patch notice.
  Do not edit the SDK cache. Only upstream `Database.java` changes.
- For `com.bhli.audit.offline` only, install a nondeleting throwing handler,
  latch corruption, omit create-on-open for an existing file, reject later SQL
  access and return a constant safe corruption error. Retain online behavior.
- In the repository, refuse preexisting zero-byte/uninitialized stores and
  orphan sidecars; distinguish true absent-store initialization. Map corruption
  to assisted recovery and block already-queued and subsequent operations.
- Preserve owner/worker, schema, migration and transaction boundaries.

Three focused Dart regressions were observed RED, then GREEN. Provenance and
licensing tests reported 19 passed; root also verified the complete source
inventory. Native correction compilation passed. None of these proves the
remaining physical-file preservation requirement.

## Independent review and remaining gate

Independent source review found a queued paged-cursor path that can bypass the
new latch; it requires a native failing regression and a focused correction.
The original runtime probe did not assert its post-close evidence. Expanded
tests now compare main-file and sidecar bytes after close, including real WAL,
and exercise the queued-cursor boundary.

Actual expanded API 36 result on the partial correction: **5 tests, 4 failures**.
Three failures are substantive; the fourth is a test-harness assertion issue:

| Case | Observed result |
|---|---|
| Writable rollback-journal runtime corruption | Main file and existing journal survive query and close; test passes |
| Writable WAL runtime corruption | Main/WAL/SHM byte-identical immediately after failed query; close changes main from 16,384 to 20,480 bytes and removes WAL/SHM |
| Writable corrupt-header startup | Main file unchanged, but all three preexisting sentinel sidecars removed |
| Queued paged cursor after corruption latch | Callback returns `success` instead of the safe corruption error |
| Read-only corrupt-header startup | All original bytes retained and open refused; overstrict getter assertion mistakes a never-assigned `null` connection for usable access |

The read-only assertion has been corrected to accept refusal or absence of a
usable connection while retaining all byte/open-failure checks. That assertion
edit has **not** been recompiled/re-executed natively. Do not retroactively turn
the raw 5/4 result into a passing test result.

Expanded evidence is retained in
`artifacts/phase6e/android-corruption-extended-9efd38c3-131f-4002-ab7a-b67ae57fdce3/`.
Its original-fixture/evidence archive SHA-256 is
`8721a43d4b469ba3b9f0263170036390a0d4043afaac56d1b74b23bd13f528ee`.
These observations distinguish default-handler deletion from later normal SQLite
file lifecycle changes. The WAL close result is not proof of additional logical
record loss, but does fail the required damaged-original preservation contract.

Ordinary SQLite rollback/WAL recovery and close/checkpoint can change files
independently of Android's destructive default handler. Do not equate disabling
that handler with proof that damaged originals and all sidecars are preserved.
The narrow correction does not satisfy the native preservation gate. Independent
review inspected both manifests and instrumentation output and agrees that a
recovery-design amendment must be reviewed before continuing storage changes.
Do not silently add plaintext snapshots, replace SQLite, suppress tests, weaken
integrity checks or claim completion.

## Operator decision: design amendment only

The current resume instruction explicitly requires stopping for approval if a
safe correction materially changes the approved recovery architecture. That
condition is now met. Neither option below is implemented or proven safe:

1. **Investigate a supported non-mutating native open/lifecycle boundary.**
   Establish how startup recovery, corruption detection, pending transactions,
   cursors, checkpointing, close/finalization and independent-process restart can
   preserve the complete damaged file set. Keep same-platform assisted recovery
   and owner/worker guarantees. Skipping `close()` or retaining a Java reference
   is not a demonstrated solution. Any engine/API change requires compatibility,
   licensing and security review; no silent dependency replacement.
2. **Design bounded confidential evidence preservation / immutable working set.**
   Specify complete main/WAL/SHM/journal inventory, coherent capture boundaries,
   durable atomic manifests and hashes, free-space/size limits, confidentiality,
   key lifecycle, failure handling and retention. No automatic activation,
   repair, deletion, replacement or movement of the damaged original. A snapshot
   alone does not keep original paths untouched; that contract change needs
   explicit approval or a reviewed immutable-original working-set design.

Recommendation: approve a **design-only safety amendment** to evaluate option 1
first and compare option 2 if no supported lifecycle solution is established.
Do not approve publication or weaken the preservation requirement on the basis
of the current partial patch. The queued-cursor fix remains independently scoped
but cannot resolve the file-preservation blocker.

## Verification and completion status

| Area | Actual evidence / remaining work |
|---|---|
| New corruption/repository/migration/restore host regressions | 42 passed, 0 failed, 0 skipped; `android-corruption-focused-final.txt` |
| Three new corruption host regressions | Observed all 3 RED, then all 3 GREEN; overlap the 42 above |
| Vendor provenance/licensing | Root rerun: 19 passed, 0 failed, 0 skipped; complete source hashes verified; no dependency version upgrade |
| Flutter static analysis / targeted Dart formatting | Full `flutter analyze --no-pub`: no issues; three changed Dart files formatted |
| Native compilation | Baseline, partial-correction app/test pair and extended test APK builds passed; compilation is not acceptance |
| Windows saved backup core | 81 passed, 1 skipped; historical, before this review |
| Windows saved native backup UI/lifecycle | 5 passed; historical, genuine owned-window capture only |
| Windows saved actual SQLite disk-full rollback | 2 passed in rollback/WAL modes; historical |
| Default Python / isolated MySQL | Historical 937 passed/67 skipped and 943 passed/63 skipped; not current-source final clearance |
| Encrypted codec / reporting | Earlier Python/Dart fixture, real SQLite, real Excel and reporting evidence retained; not rerun as a substitute for the failed native gate |
| Assisted recovery | Android damaged-original preservation not approved; fresh-target complete native workflow remains pending |
| Full final suites/builds | Deferred pending the preservation decision; no clean-source Windows installer, final online/offline APK or native full-suite completion claim |

No new source commit was created for the still-failing native correction. All
existing Phase 6E commits and uncommitted implementation work remain preserved.
The working tree is intentionally not clean; no files are staged. Both owned
read-only emulator runs exited after host evidence was retained. No original AVD,
installed application, employee database, production resource or release asset
was altered. The local Version 1.0 tag still resolves to
`d2b9ed9fca9ade40829b89e328d8681ef2d15bfc`.

The ten preceding Phase 6E commits remain preserved, in order:

```text
f315537c7212d4796aeb8242f4acf6db95b83fcd docs: design offline reports and encrypted backup recovery
ef097b7c6351ebfb59bbb1e231d884bd4cbd4f42 docs: plan local offline reporting and backup implementation
5ce9dc203fa06100f15706269955f6ed105c19b7 feat(offline): add authenticated full-state backup contracts
54847f18a057a913464c44efca98393354d34c1e feat(windows): export consistent offline Excel reports safely
995264593f22c6bc903c03e9295014a6274dd92e feat(android): add consistent offline summaries and safe text reports
849a47d910a402c51c86e389381d94dd45a74ab8 fix(windows): acknowledge report cleanup failures before shutdown
c6f9e4302b0fd9227da114f7e7aa129d0ca2adcb feat(windows): add owned encrypted backups and verified transactional restore
8704e8820d8c31cb2be06a410754c812c2af6918 feat(windows): integrate guarded backup and restore workflows
f875e5eda455dbf20d9b5a299829d4567c4fba10 test(windows): verify restore rollback on actual SQLite disk exhaustion
c84e471c403cb5a745d39498e76dbd1409c22a99 build(offline): isolate pinned backup crypto and retain native notices
```

**Publication recommendation: HOLD. Phase 6E is not complete.** No push, PR,
merge, release, production operation or next-phase work was performed.

Full regressions, native backup/SAF/process-restart acceptance, final clean-source
builds and publication readiness remain pending this safety decision. Historical
937/67 default and 943/63 isolated-MySQL results are not final clearance for the
changed source.
