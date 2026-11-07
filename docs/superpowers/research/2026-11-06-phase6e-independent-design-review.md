# Phase 6E — independent design review

Date: 2026-11-06. Baseline `d613dae935ddbb3607b828feccf48df1736241e4`.
Scope: proposed offline reporting/encrypted backup/restore design, not product
implementation or production approval. Two independent read-only reviewers
examined the design and relevant existing Python/Flutter/SQLite ownership code.

Documents reviewed:

- [Engineering design](../specs/2026-11-06-phase6e-offline-reporting-backup-design.md)
- [Backup format/security/restore](../specs/2026-11-06-phase6e-backup-security-restore.md)
- [Verification/checkpoints](../specs/2026-11-06-phase6e-verification-checkpoints.md)
- [Research](2026-11-06-phase6e-reporting-backup-research.md)

## Initial findings and resolution

| Finding | Resolution |
|---|---|
| Durability configuration appeared after BEGIN while saying it must run outside a transaction | Configuration/readback now precedes marker/write admission and BEGIN IMMEDIATE. |
| A corrupt/unopenable current store cannot yield the complete recovery snapshot required by the in-place protocol | Operator selected assisted recovery into a fresh same-platform instance. The original files/sidecars remain untouched; bootstrap instructions no longer imply automatic repair. Separate OS user/device is specified; no arbitrary path bypass or uninstall/clear-data procedure. |
| A COMMIT exception/lost acknowledgement was incorrectly described as guaranteed rollback | ORIGINAL/RESTORED/UNKNOWN digest classification, owner-aware rollback, reopen validation, no automatic retry/reverse restore, and a real-COMMIT/lost-result test are required. Unknown state blocks writes. |
| An optional marker could not support required restart classification | Bounded recovery marker is now mandatory before replacement. Startup processes it before cleaning stages; retained encrypted input/recovery paths are generated and constrained. Marker never authorizes replay/deletion and is not commit authority. |
| Lease lifetime was unclear and a restore-only lock would admit stale cooperating instances | Every Phase 6E instance acquires a process-wide per-data-directory lease before SQLite opens and retains it through drained close or process death. Activity/widget disposal cannot release a live store; older builds/external tools remain an explicit operator precondition. |

State digest framing, raw-history preservation, SQLite vs installer identity and
empty-instance behavior were also clarified. No implementation was written to
demonstrate these proposals; they must still be verified in the acceptance plan.

## Final security/data-loss review

**PASS for operator design-approval review.** All earlier material findings are
closed. No remaining material gap identified in the proposed fixed Argon2id/
AES-GCM suite, authenticated header, KDF bounds, complete state inventory,
platform binding, preview/revalidation, recovery proof, one-transaction restore,
no-overwrite publication or exact SAF deletion ownership.

The reviewer explicitly distinguishes supported SQLite/OS assumptions from
physical power-cut guarantees; same-platform recovery from cross-platform
transfer; locally declared identities from real employee authentication; and
design readiness from native/runtime verification.

## Final builder/architecture/mobile UX review

**PASS for operator design-approval review: nothing important left for planning.**
Corrupt-current handling, ambiguous completion and owner-lease lifetime are
sufficiently specified. Report/backup seams preserve current ownership and online
isolation. Windows literal-text XLSX and selected Android summary/text reporting
are feasible without a large reporting framework. Dangerous replacement is
distinct from transfer/export; explicit preview/default Cancel, accessible
acknowledgement, large-text/keyboard controls and phase-truthful errors are covered.

Detailed implementation planning can follow operator approval. Pure-Dart crypto
speed/memory, frozen Python native support, OS lock behavior, document providers,
restore process-death/power-loss behavior and device/installer acceptance are
**unverified gates**, not review passes or waived requirements.

## Operator choices and remaining approval

Confirmed during design: Android summary + readable UTF-8 report; assisted
corrupt-current recovery into a fresh same-platform target.

The full design still requires approval before code or dependency installation,
particularly the encrypted format/dependency candidates, replacement of profile/
installation identity, mandatory pre-restore recovery backup and proposed
capacity/durability gates. No application tests/builds/DB operations, push, PR,
merge or release were performed by this design assignment or its reviewers.
