# Phase 6E Android recovery amendment — research and independent review

**Historical review of a CANCELLED proposal.** The operator superseded this
architecture with ordinary SQLite and simple user-created backups. Retained for
evidence; this document does not authorize generation-system implementation.

Date: 2026-11-07, Asia/Manila. **Design only; operator approval pending.**

Proposed specification:
[Android recovery-safety amendment](../specs/2026-11-07-phase6e-android-recovery-safety-amendment.md).
Input HEAD: `4f7b6dc8d7c43c1ffe218da559baf467c2559187` on
`feat/dams-offline-reporting-backup`.

## Work preserved and evidence verified

At entry no files were staged. The intentionally dirty implementation was
inventoried: 104 existing changed/untracked files, including the partial vendor
correction, Android backup work and unfinished earlier documentation. Their
SHA-256 values were recorded locally for a final unchanged-input check. Existing
agents were completed; newly requested independent reviewers were read-only.
No application/plugin edits, tests, builds, emulator runs, dependency installs,
database operations, GitHub actions or production operations were performed.

The retained native archives were read without extracting over any workspace:

| Evidence | Reverified archive SHA-256 | Original fixture copies checked |
|---|---|---|
| `artifacts/phase6e/android-corruption-evidence-9efd38c3-131f-4002-ab7a-b67ae57fdce3/fictional-cache-evidence.tar` | `f53aab77d523dd27339177f4538c42b3d359eb8027710124fb86029a0f232d39` | 10, each matching its recorded original size/hash |
| `artifacts/phase6e/android-corruption-extended-9efd38c3-131f-4002-ab7a-b67ae57fdce3/fictional-cache-evidence.tar` | `8721a43d4b469ba3b9f0263170036390a0d4043afaac56d1b74b23bd13f528ee` | 13, each matching its recorded original size/hash |

These are archive/file-integrity checks, not newly executed native tests. The
historical native results remain 3 tests/2 failures and 5 tests/4 failures,
including the documented read-only harness assertion issue. Historical 42 host
and 19 provenance passes do not override them. Original source and failure
evidence remain available; no failing scenario has been removed or reclassified
as an implementation PASS.

## Research conclusion

Option A—supported native lifecycle controls—could be smaller but has no complete
proven interface in the current pinned wrapper. A throwing handler does not
control every SQLite recovery/checkpoint/close path. No claim of fundamental
impossibility or undocumented Android hook is made.

Option B—immutable originals and separately published generations—is recommended
only with an explicit contract change. A startup-only snapshot cannot preserve
acknowledged session changes. A late corruption capture cannot promise exact
pre-detection bytes. Publishing an authenticated generation for every admitted
mutation provides a clear acknowledged-state preservation point; SQLite sees
only working copies. This adds considerable storage/key/publication complexity,
which the proposed checkpoints and acceptance gates must prove worthwhile.

Primary references were consulted directly, alongside the actual code and native
manifests. Technical conclusions beyond those sources are recommendations, not
claims that Android already implements this architecture:

- [SQLite corruption guidance](https://www.sqlite.org/howtocorrupt.html): active-copy, journal-pairing and file-descriptor locking hazards.
- [SQLite WAL lifecycle](https://www.sqlite.org/wal.html): persistent WAL state, read-only conditions, checkpoint/close cleanup.
- [SQLite connection configuration](https://sqlite.org/c3ref/c_dbconfig_defensive.html): C-level close-checkpoint control; no inferred Android wrapper support.
- [SQLite URI semantics](https://www.sqlite.org/uri.html): `immutable` assertions are not a safe label for a changing store.
- [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html): durability relies on stated filesystem/sync assumptions; it does not make a separate multi-file catalogue protocol atomic.
- [Android OpenParams](https://developer.android.com/reference/android/database/sqlite/SQLiteDatabase.OpenParams.html): API 28+ availability is insufficient by itself for minimum API 24 coverage.
- [Android AtomicFile](https://developer.android.com/reference/android/util/AtomicFile): single-file writing support without process locking semantics.
- [Android private storage](https://developer.android.com/training/data-storage/app-specific), [no-backup files](https://developer.android.com/reference/android/content/Context#getNoBackupFilesDir()) and [Keystore](https://developer.android.com/privacy-and-security/keystore): platform storage/key facilities, not a guarantee of device-independent recovery or measured provider memory usage.

## Independent review disposition

Two independent reviewers examined both original options, relevant source,
approved Phase 6E guarantees, native evidence and the complete amendment. The
implementation reviewer also performed the Superpowers builder check: questions
that would require consequential guesses before implementation planning.

| Finding | Severity / reviewer | Resolution in the proposed design |
|---|---|---|
| Handler/read-only checks cannot protect originals through all native lifecycle paths | High, both | SQLite never opens protected originals/seals; distinct working-copy and published-state guarantees require explicit approval |
| Copying runtime files while SQLite holds handles risks inconsistent capture/lock effects | High, both/root | No raw-copy descriptors on a SQLite-held file; diagnostics only after confirmed close/process death, labelled post-close/incomplete |
| Visible selector after failed sync is not durable publication proof | High, security | Re-establish checked durability and readback or remain UNKNOWN/recovery-only; no false save success |
| Failed corruption-marker write followed by process death could bypass a latch | High, security; implementation | Durable admission before every read/proof/write workspace open; unclean records block automatic Ready |
| Pre-close validation does not prove the sealed physical state | Medium, both | Every sealed candidate requires a separate decrypted proof copy, full validation/digest comparison and checked close before publication |
| Old restore markers/SQL COMMIT conflict with new storage authority | Material builder gap | Old pending markers block automatic enrollment; new restore markers bind generation/operation/parent; selector publication determines ORIGINAL/RESTORED |
| Automatic backup might replay legacy files without managed authority/key | Medium invariant, security | Source check confirmed existing exclusions; preserve and verify merged offline cloud/D2D rules. OEM/manual/root replay remains a limitation |
| Routine Android process death needs a safe availability path | Material design clarification | Explicit operator-acknowledged same-generation verification; retain evidence, no abandoned candidate promotion, older fallback or SQL retry; invalid authority requires assisted recovery |
| Unknown related SQLite artifacts or provider buffering can defeat bounds | Additional safety clarification | Unknown artifacts block enrollment; 64 KiB is I/O-only, provider memory is a measured admission gate with no custom chunk/fallback crypto |

All material design findings were addressed before this handoff. Independent
security verdict: **ready for explicit operator design approval only**.
Independent implementation/builder verdict: **nothing important left before
implementation planning; ready for operator consideration**. Neither verdict is
an implementation, native preservation, cryptography, crash-durability or release
approval. Reviewers made no application changes and ran no tests/builds.

## Decisions explicitly requiring operator approval

1. Protected-original/last-acknowledged-state guarantee versus exact changing
   runtime bytes, which this architecture does not provide.
2. Internal managed paths and generation-selector activation before save success.
3. Separate device-bound Keystore key, encrypted physical artifacts and key-loss
   limitations; portable Argon2id/AES-GCM backups remain unchanged.
4. Explicit same-generation verification/resumption after a workspace-only
   failure; no in-place restoration of corrupt authoritative state.
5. Proposed 128 MiB physical-set and 1 GiB managed-storage ceilings, per-save
   copying, retention and refusal on exhausted resources.

The recommended approval is for the complete amended specification, followed by
separately authorized implementation. If exact active-runtime-file preservation
is non-negotiable, keep HOLD and return to native-engine research instead of
silently accepting weaker guarantees.

## Remaining implementation gates

API 24/36 filesystem/Keystore/provider behavior, mandatory file-set hashes after
close/restart, queued cursor/error settlement, crash-stage publication tests,
fresh-install/migration/restore identities, retained failure evidence, I/O/memory
cost, online/Windows compatibility, package notices and full final regressions
remain unverified implementation gates. Physical-device/power-loss acceptance
must be reported separately. No new test totals or native/build PASS is claimed.

**Stop here for operator design approval. Phase 6E publication remains HOLD.**
