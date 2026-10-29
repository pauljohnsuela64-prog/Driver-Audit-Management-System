# Phase 4B Android Audit Management Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. Operator approved the design at `5fdbd0d`; Checkpoints 1–2 are authorized and completed. Tasks 3–6 require further authorization.

**Goal:** Authorized Android creation, editing, soft deletion and history without changing backend rules.

**Architecture:** Extend the existing typed API/session modules and focused view controllers. Mutation state owns immutable request attempts and uncertain-outcome handling; widgets never receive bearer tokens. Reuse existing themes, native privacy and route/session lifetime.

**Tech Stack:** Existing pinned Flutter/Dart, Material 3, http/shared_preferences and FastAPI REST contracts. No additional dependency expected.

**Spec:** `docs/superpowers/specs/2026-10-28-phase4b-android-audit-management-design.md` — approved at `5fdbd0d`; stop after the local Checkpoint 2 commit.

## Global constraints

- Baseline `54c1f2e1b91d12f570d0bb67b54b25a10f9090d3`; feature branch `feat/dams-android-audit-management`.
- Six editable fields; immutable server-assigned seventh field Audited By. Ownership uses user ID.
- ADMIN create/read/edit/soft-delete; AUDITOR create/shared read/own edit, no delete. Archived access ADMIN-only and explicit.
- UUIDv4 create key; exact quoted ETag/If-Match for PATCH/DELETE. No automatic write replay after conflict.
- Memory-only tokens/drafts/attempts, trusted remote HTTPS, existing debug-only loopback and lifecycle safeguards.
- Preserve backend, schema, migrations, grants, Windows behavior and all five CI checks. Fictional isolated data only.
- No implementation, push or PR before design approval; no production modification or next-phase feature.

## Review focus

1. A create commits but its response is lost: retry uses the same UUID and frozen normalized payload (Task 2).
2. Retry returns an already edited current record: do not reject it for differing from original payload or overwrite it (Tasks 1–2).
3. Logout/account switch races a write: late completion never restores protected UI; cancellation never promises rollback (Task 2).
4. Stale ETag or uncertain edit/delete: require latest-state review and explicit action, never silent last-writer-wins (Task 4).
5. History actor IDs and arbitrary snapshot metadata: display only the safe allowlist; never infer actor names or call the user directory (Task 5).

## Task 1 — Typed payload, permissions, mutation and history contracts

**Modify:** `mobile/lib/core/network/api_client.dart`, `api_failure.dart`, `features/audits/models.dart`.
**Create:** `mobile/lib/features/audits/audit_draft.dart`, `audit_permissions.dart`, `audit_history_models.dart`; focused tests in `mobile/test/`.

**Interfaces:** `AuditDraft` validates/normalizes and emits six-key `Map<String,Object?>` create JSON or changed-only patch JSON. `PendingAuditCreate` holds immutable payload/key. `AuditMutationResult` holds record and replay flag. Pure permissions consume current `AuthenticatedUser` and `AuditRecord`, compare stable IDs. History models validate page echo, event action/IDs/timestamps and allowlisted before/after values.

- [x] RED tests: Unicode code-point limits and field-specific backend stripping (required Unicode White_Space versus optional Python strip including U+001C–001F; preserve BOM), optional null versus omission, valid calendar boundaries, duplicate plates allowed, empty patch, mass-assignment rejection, UUID version/variant and role/owner-ID matrix. Compare normalization against actual AuditCreate golden vectors.
- [x] RED transport tests: POST201/200 replay, nullable JSON, correct key header, PATCH200/DELETE204 with exact If-Match, response version/ETag agreement, 409/412/428, safe body-limit/timeout/redirect failures and explicit archived mode.
- [x] Implement typed `ApiClient.createAudit`, `updateAudit`, `deleteAudit`, `auditHistory` with existing token-taking transport seam. Keep bearer access inside session callers; avoid arbitrary endpoint/header escape hatches.
- [x] GREEN focused contracts and analyzer; checkpoint commit with reviewed tests.

## Task 2 — Session-owned mutation coordination and safe retries

**Completed under the operator's Checkpoint 2 authorization.**

**Modify:** `mobile/lib/features/auth/session_controller.dart`.
**Create:** `mobile/lib/features/audits/audit_mutation_controller.dart`; mutation/session regression tests.

**Consumes:** typed payload/result/history contracts from Task 1.
**Produces:** token-free `SessionController.createAudit(attempt)`, `updateAudit(id,etag,patch)`, `deleteAudit(id,etag)`, `fetchAuditHistory(id,page,includeDeleted)` plus bounded cancellation/generation checks. Controller states distinguish idle, validating, sending, confirmed, unknown outcome, conflict and forbidden; retain field errors separately.

- [x] RED: double Save dispatches once; timeout after commit reuses key/payload; edited payload cannot replace unknown attempt; 409 never rotates key; replay after later edit displays returned current state.
- [x] RED: logout/new account/new origin clears attempts and ignores late success/401; cancellation and invalid success retain truthful unknown-outcome semantics; pending mutation does not block logout or awaited resume validation. Leaving an unknown create retains exactly one RAM-only session attempt and its Audits review banner; abandonment requires acknowledgment, restart gets only a general new-create reminder.
- [x] Implement one in-flight mutation per session with a separate transport scope AND mutation latch, not authentication/resume `_busy`. Generation-invalidating session changes cancel that scope; ordinary list/detail cancellation cannot abort it. No automatic background resend or durable retry journal.
- [x] GREEN state/transport races, affected existing auth/lifecycle tests; checkpoint commit.

## Task 3 — Accessible Create/Edit form and list entry points

**Create:** `mobile/lib/features/audits/audit_form_controller.dart`, `audit_form_screen.dart` and reusable local form controls only where shared.
**Modify:** `audit_list_screen.dart`, `audit_details_screen.dart`, existing list controller only for explicit invalidation/refresh.

**Consumes:** permissions, draft validation, token-free mutation methods and state from Tasks 1–2.
**Produces:** create/edit routes returning a typed confirmed mutation result or no change, without leaking credentials or treating list refresh as part of the committed write.

- [x] RED widget tests: six fields/immutable attribution, required/optional limits, Unicode/paste/IME, date picker/manual date, changed-only patch, duplicate submission, dirty Back, uncertainty warning and same-key Retry. Keyboard Back dismisses IME before route navigation; Next moves single-line focus and Remarks keeps newline behavior. Verify stacked/wrapped actions at largest supported text size.
- [x] Implement full-screen scrollable phone form and readable tablet width; safe-area/IME-aware Save/Cancel, first-error focus, semantics and 48dp targets. No autosave or silent truncation.
- [x] After confirmed save refresh detail and list page1 with applied filters; show saved-but-not-in-filter and refresh-failed feedback separately.
- [x] GREEN both themes, 320dp/200% text and keyboard layouts, existing read-only regressions; checkpoint commit.

## Task 4 — Conflict review and ADMIN soft deletion

**Create:** `mobile/lib/features/audits/audit_conflict_screen.dart`; delete confirmation/controller logic local to details unless shared state warrants a focused file.
**Modify:** detail route and form mutation handling.

**Consumes:** current detail/ETag, draft diff and mutation state.
**Produces:** explicit reload/review/resubmit choices with a newly reviewed baseline; delete returns confirmed/unconfirmed result, never a fabricated restored record.

- [x] RED tests: AUDITOR non-owner cannot open/submit edit; no AUDITOR delete; role change between display/dispatch handled by server failure; 412 and409 retain same-session draft but never replace If-Match automatically. Per-field latest/proposed choices preserve unrelated latest changes, latest-fetch failure disables Save and repeated conflict restarts review.
- [x] RED: lost PATCH response requires refetch; lost DELETE response checks ADMIN include-deleted state; 404 is unavailable, not proof of deletion. New confirmation required after a changed version.
- [x] Implement comparison, discard confirmation, read-only archived state and Record-ID/driver/plate delete dialog with accurate soft-delete copy.
- [x] GREEN conflict/deletion/controller/widget tests, existing session tests; checkpoint commit.

## Task 5 — Authorized history and explicit archive browsing

**Create:** `mobile/lib/features/audits/audit_history_controller.dart`, `audit_history_screen.dart`.
**Modify:** list/query/detail/session archived-mode interfaces; keep default active-only parsing strict.

**Consumes:** history models and permissions. History uses page10, oldest event first; ADMIN archive flag propagates only to authorized list/detail/history requests. Audit-list pages remain25.
**Produces:** event cards with actor ID, timestamp/timezone and allowlisted field changes; no user lookup dependency.

- [x] RED: shared active history both roles, archived history ADMIN-only, hidden archive control for AUDITOR, unexpected archived response rejected in active-only mode.
- [x] RED: actor ID is distinct from Audited By; unknown/private snapshot keys never rendered; null/Unicode/long values, absent before-data for CREATE and DELETE lifecycle state, page bounds and superseded results. Serialize ten maximum-size before/after events using the actual backend JSONResponse, including six-byte-escaped controls; assert body below2MiB. Reject unexpectedly oversized responses without truncation.
- [x] Implement explicit Include archived switch, read-only archived details, history paging/refresh/loading/error states and expandable labeled comparisons.
- [x] GREEN history/archive widgets and transport regressions; checkpoint commit.

## Task 6 — Real API, fault injection, native acceptance and publication gate

**Extend:** `scripts/mobile_demo.py`, `tests/test_mobile_demo.py`, `mobile/integration_test/`, `test_driver/` and Android verification/development documentation. Use a second fictional AUDITOR to test stable-ID ownership; keep production isolation hard-coded.

- [ ] RED/GREEN disposable API cases: create/replay, shared reads, owner/non-owner edits, ADMIN edits/deletes, exact history and immutable attribution, archive restrictions, duplicate plates and concurrent same-key/edit/delete requests.
- [ ] Test-only fault adapter drops mutation responses after backend commit; assert exactly one CREATE event on retry, stale PATCH protection and honest uncertain DELETE handling. No shipping auth bypass.
- [ ] Run `dart format --output=none --set-exit-if-changed lib test integration_test test_driver`, `flutter analyze --fatal-infos`, full `flutter test`, real-API native acceptance and serial default/isolated-MySQL regressions. Preserve existing Windows and installer checks.
- [ ] Native fictional walkthrough: both roles, second AUDITOR denial, touch/keyboard/Back/dirty discard, conflict/history, themes, compact/landscape/large text, background/logout/process death and safe shutdown. Capture genuine screenshots; explicitly report unavailable API24/physical/TalkBack/TLS checks.
- [ ] Independent engineering/security and mobile-UX reviews; reproduce and fix confirmed issues with focused regression coverage; coherent verified commits.
- [ ] Only after implementation authorization and verification: inspect complete diff/secrets, publish the same branch, create exactly one draft PR and verify all five hosted jobs. Never merge automatically.

## Current design handoff

Checkpoint 1 is implemented and verified: 26 new contract tests and all 60 existing
Flutter tests pass (86 total, zero failures/skips); analysis and formatting pass.
Independent engineering/security review found no blocking defect. Review-driven
coverage now includes distinct same-plate creation attempts and archived-list
transport/parsing. A reproduced BOM-only response parsing mismatch was corrected
without changing authentication parsing. Shared request timeout/cancellation
regressions also pass. No backend, session/UI, Windows, schema or dependency change.

Checkpoint 2: baseline 86 tests reverified before changes; 33 new mutation/session
tests pass, full Flutter suite **119 passed, zero failures/skips**. Formatting and
static analysis pass. Separate mutation scope/latch preserves logout and read
cancellation isolation. One frozen create attempt remains session-RAM-only for
explicit retry/review/acknowledged abandonment; no background write retry.
PATCH/DELETE uncertainty requires fresh review and explicit acknowledgment.
No banner or visual form was built; the retained state supports those future UI
checkpoints. History access is token-free and archived access remains ADMIN-only.

Independent engineering/security review corrections were reproduced with RED
tests: unsupported/redirected HTTP results stay unconfirmed; post-notification
logout suppresses returned records; immediate save/resume scheduling is rechecked
before dispatch. Further regression fixes prevent create-abandonment bypass of
unresolved PATCH state, stale/superseded reviews, canceled queued dispatch and
publication before concurrent resume validation. Final review found no remaining
confirmed blocker.

Runtime/server fault injection, visual screens and native Android acceptance are
deferred to their assigned later checkpoints. Cancellation cannot undo a server
transaction, and process death/logout deliberately erases retry information.
Tasks 3–6 remain unchecked and unimplemented. No push or PR is authorized.
Stop after the local Checkpoint 2 commit and await operator review.


Checkpoint 3 completed (2026-10-29): accessible six-field create/edit forms,
server-owned attribution, fresh ETag entry, changed-only PATCH, permission-aware
entry points, session-memory frozen retries, explicit abandonment/discard, and
filter-preserving page-1 refresh with separate save/refresh feedback. Minimal
reload/discard gates unresolved edits; per-field conflict review remains Task 4.

Verification: original 119 tests reverified before implementation; final full
Flutter suite **160 passed, zero failures/skips** (27 form/controller, 12 navigation,
2 rejected-create regressions plus the original 119). `flutter analyze --fatal-infos`
reports no issues; formatting checks all 44 Dart files with no changes.
Local ignored evidence: `artifacts/phase4b-cp3-full-final.txt`,
`phase4b-cp3-analyze-final.txt`, and focused RED/GREEN logs.

Independent engineering/security and mobile-UX reviews found and verified fixes
for definite first-422 draft freezing (without releasing previously uncertain
attempts), interruption guidance, keyboard/exit-dialog behavior, nested-navigator
save completion, and terminal 403/404 draft clearing/identity revalidation plus
visibility refresh (including failed refresh). Both themes, portrait/landscape at
200% text, compact320dp, first-error focus and keyboard Back pass widget checks.
No residual confirmed review blockers. No broad `dart fix` changes are included;
final lint corrections were targeted braces in changed files only.

Native Android/emulator, physical-device/TalkBack, real-server mutation integration
and eventual full backend/hosted verification remain Task 6. No such acceptance is
claimed here. Tasks 4?6 remain unimplemented and require further authorization.
No backend, Windows, schema, migration, grant, dependency or production changes.


Checkpoint 4 completed (2026-10-29): same-session original/proposed/latest
comparison, explicit per-field choices, latest-only concurrent changes preserved,
changed-only reviewed PATCH, no-op avoidance and repeated-conflict review.
Back/discard confirms draft loss; canceled waits never imply server rollback.
ADMIN Archive audit uses fresh detail/ETag and identity confirmation; 204 is
confirmed separately from list refresh failure. Unknown DELETE uses narrow
ADMIN-only include-deleted verification; 404 remains unavailable/unconfirmed.
No broad archive browsing, history, restore or permanent deletion UI was added.

Verification: baseline160 reverified; 25 new conflict/archive tests and one
session role-after-resume dispatch regression bring the full Flutter suite to
**186 passed, zero failures/skips**. Focused form/navigation/conflict suite64
passed. Final formatting checks46 Dart files without changes and
`flutter analyze --fatal-infos` reports no issues. Local ignored evidence is
`artifacts/phase4b-cp4-{baseline,focused-final,full-final,analyze-final,format-final}.txt`.

Independent engineering/security and mobile-UX review corrections: all-latest
no-op handling, display of unrelated concurrent changes, reviewed-PATCH pending
exit cancellation/gate preservation, retry access-loss exit, same-generation
role downgrade erasure and dialog dismissal, root discard-dialog logout safety,
confirmed archive versus actual-list refresh failure, and an ADMIN guard after
awaited resume before DELETE transport dispatch. Targeted RED/GREEN regressions
cover the reproduced defects. Re-reviews found no residual confirmed blockers.
Both themes, portrait/landscape compact320dp at200% text, long Unicode/null
comparisons, selectable values, padded choice targets and dialog lifecycle pass
widget checks. Native Android/TalkBack/physical-device and real-server mutation
acceptance remain unverified and assigned to Task6.

Task4 only is complete. Task5 history/full archive browsing and Task6 acceptance
remain deferred pending authorization. Backend, Windows, schema, migrations,
grants, dependencies and production data are unchanged. Local commit only;
no push, pull request or merge is authorized for this checkpoint.


Checkpoint 5 completed (2026-10-29): dedicated read-only history with ten events
per page in backend oldest-first order, Created/Updated/Archived actions, actor
account IDs (never inferred names), local timestamp/timezone and expandable UTC
and allowlisted previous/updated values. Seven business fields and archive status
are projected; arbitrary metadata never becomes displayable history. ADMIN-only
Include archived defaults off and means active plus archived, preserving list25,
search/filter/sort/pagination. Explicit permission-checked mode propagates to
read-only archived details/history; active-only parsing remains strict.

Verification: baseline186 reverified; full Flutter suite **213 passed, zero
failures/skips** (27 new history/archive regressions). Focused32 passed including
5 existing list-controller tests. `flutter analyze --fatal-infos` reports no
issues; formatting checks50 Dart files without changes. Three pure Python
serialization tests pass without API/database fixtures. Actual JSONResponse:
ten maximum escaped-control before/after events =1,302,356 bytes; ten maximum
Unicode events =871,156 bytes;25 worst-case events =3,255,821 bytes. Thus history10
fits the unchanged2MiB cap, while list page size25 must not be reused for history.
Oversized streamed history is rejected safely without partial/truncated events.
Local ignored evidence: `artifacts/phase4b-cp5-{baseline,focused-final,full-final,
analyze-final,format-final,serialization-final}.txt` and targeted RED/GREEN logs.

Independent engineering/security and mobile-UX review found no residual confirmed
blockers after corrections: late archived response suppression across same-session
role downgrade, initial unauthorized-history unavailable feedback, unexpected
resume account-ID mismatch invalidation, and archive-control visibility updates
when role changes with the switch off. Same-account role changes remain supported.
Existing test doubles were adapted only for the optional explicit read-mode
argument; their assertions remain intact. Only reported brace lints were fixed.
Both themes320dp200%,300%landscape/tablet,10,000-codepoint Unicode/null comparisons,
archived read-only detail/history/Back and measured History-action48dp pass widget
checks. Material semantics are source-supported; comprehensive focus/target audits,
actual TalkBack, physical/native Android and real-server mutation acceptance remain
unverified for Task6.

Task5 only is complete. Task6 remains deferred pending authorization. No backend
business logic, Windows, schema, migration, grant, dependency or production change.
The added backend-schema serialization test exercises existing behavior only.
Local commit only; no push, PR or merge.
