# Phase 3B — Full Driver Audit Management

Status: proposed; awaiting design approval. No application implementation authorized by this document alone.

## Readiness and scope

PR #5 is merged. Local main was fast-forwarded to `2757d68811468e8961b77ed64193a0030f8950e1`; `feat/dams-audit-management` was created from that commit with a clean working tree. The post-merge [CI run](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40442133079) passed Windows desktop, SQLite, and disposable MySQL jobs.

Extend the existing Python/CustomTkinter sidebar workspace through the existing FastAPI REST API only. Preserve Phase 3A authentication, themes, keyboard behavior, background workers, teardown fixes, and read-only workflows. No backend business-rule changes, migrations, grants, production database operations, or Phase 3C features are planned.

## 1. Screens and workflows

**Recommended approach:** full-page Create/Edit, History, and conflict-comparison screens within the existing sidebar workspace. Keep modal dialogs for discard and destructive confirmation. An all-modal editor would constrain long remarks and high-DPI layouts; inline table editing would obscure validation and concurrency decisions. Neither is recommended.

### Audit list and details

- Add **New audit** for both roles. Retain current search, filters, sort, paging, selection, and dashboard navigation.
- Details provide **Edit**, **History**, and ADMIN-only **Delete**. Enable Edit only for ADMIN or the original owning AUDITOR, comparing stable user IDs. Server authorization remains authoritative.
- ADMIN can explicitly enable **Include deleted** in list filters. Deleted rows have a text status and details banner; they are read-only and retain History access. AUDITOR never receives this control or sends this option.
- After mutation, refresh affected list/dashboard data while preserving query context. Select the saved record when present; otherwise explain that current filters exclude it and offer View record. After deletion, move back a page if the current page becomes empty. Clear stale detail contents on missing/forbidden responses.

### Create and Edit

Use a scrollable, two-column form at wide widths, one column at compact widths. Header shows mode and record identity; footer contains primary Save and secondary Cancel. Keep errors and operation status visible without covering fields.

| Field | Rule |
|---|---|
| Driver name | Required, trimmed, maximum 200 characters |
| Helper name | Optional, maximum 200; blank clears to null |
| Audit date | Required real calendar date, `YYYY-MM-DD`, years 1000–9999 |
| Station | Required, trimmed, maximum 150 |
| Plate number | Required, trimmed, maximum 30; duplicates allowed |
| Remarks | Optional multiline, maximum 10,000; blank clears to null |
| Audited by | Read-only seventh business field; never submitted |

Create shows the signed-in name as a preview only; the backend supplies the authoritative name snapshot and owner ID. Edit preserves the original snapshot regardless of later employee-name changes. No scores, checklists, attachments, or additional business fields.

Normalize according to the backend schemas; preserve raw draft text while correcting errors. Validate before submission, use inline messages plus a keyboard-focusable error summary, and retain all entered values on recoverable failure. A normalized no-change edit does not issue PATCH.

Tab/Shift+Tab follow visual order; labels and optional-field hints remain visible. Enter in remarks inserts a newline. Saving requires the Save action, avoiding accidental submission from multiline input. Escape/Cancel or navigation with unsaved changes asks whether to discard. Restore focus to the initiating control after dialogs. Delete confirmation defaults to Cancel and names record ID, driver, plate, and date.

### History

Use a full-page chronological event list, with action, UTC timestamp, and `User #<actor_user_id>`. The endpoint supplies actor IDs, not actor names; do not invent names or call ADMIN-only employee endpoints for AUDITOR views.

Selecting an event shows readable before/after values and highlights changed business fields. CREATE has no before snapshot; DELETE retains the server's after snapshot, including deletion metadata. Long remarks wrap and scroll; metadata (version, stable owner ID, deletion time) appears separately from the seven business fields. Preserve original audited-by attribution distinctly from the actor who edited/deleted.

Use history pages of 25 events with Previous/Next and total count; preserve selected event while refreshing when possible. This bounds responses with two maximum-size snapshots per event within the existing finite 16 MiB transport limit. Validate that bound with escaped Unicode regression data rather than increasing limits without evidence.

## 2. Architecture and API contracts

Reuse `desktop/api.py` and its injectable transport as the network seam, immutable typed models in `desktop/models.py`, existing themed controls, session generation checks, and worker queues. Shipping desktop code must not import backend/database code. Keep private data and bearer tokens in memory only.

Proposed modules:

- `desktop/audit_operations.py`: UI-independent draft/operation state, normalized payloads, creation intents, baseline/latest comparisons, and mutation-result transitions. Test through its small interface; avoid repeating retry rules across screens.
- `desktop/screens/audit_form.py`: reusable Create/Edit presentation.
- `desktop/screens/audit_history.py`: event pagination and before/after presentation.
- `desktop/components/audit_dialogs.py`: focused discard/delete confirmations and conflict-resolution controls, using existing timer/widget cleanup conventions.
- Existing app/list/details modules: navigation, action availability, dirty-data refresh, and operation delivery integration.

| Operation | Contract |
|---|---|
| Create | `POST /audits`; six-field body; UUID `Idempotency-Key`; new 201 or matching replay 200 |
| Edit | `PATCH /audits/{id}`; only changed permitted fields; exact `If-Match` from GET ETag |
| Delete | `DELETE /audits/{id}`; exact `If-Match`; 204 soft deletion |
| History | `GET /audits/{id}/history?page=…&page_size=25`; typed items/total/page/page_size |
| Deleted access | ADMIN-only `include_deleted=true` on list, detail, and history GETs |

Extend API methods with typed mutation/history results and explicitly allowed headers. Preserve exact ETag strings; never synthesize them from body versions. Missing/invalid ETag blocks mutation and prompts reload. Extend deleted-record parsing deliberately for authorized reads; ordinary active-only parsing remains strict. Parse history snapshots and envelopes defensively, including IDs, timestamps, actions, and nullable before data.

All networking runs on workers; only the UI thread reads/writes Tk objects. Workers capture immutable payloads, tokens, and IDs, never widgets. Keep bounded queues and reject excess work visibly.

Unlike supersedable reads, a submitted mutation cannot be treated as cancelled merely because a view disappears. Keep operation state outside widgets until its result settles. Block ordinary form navigation during submission; logout/window close remain available and explain that a sent request may already commit. Theme changes rebuild presentation from retained draft/intent state without resubmitting. Late results must match the originating account/session generation before affecting the current UI. Logout/401 clears private drafts and tokens; no retry or replay under a later session. Preserve main-thread font collection and owned-timer cleanup on close.

## 3. Permissions and session handling

Both authenticated roles may create and view active records/history. ADMIN may edit any active record and soft-delete; AUDITOR may edit only records whose immutable owner ID matches their own. UI visibility is convenience, never authorization. Re-check server results even if the cached role previously allowed an action.

401 clears the session and private screen state, returning to login. 403 explains loss of permission without exposing stale content; refresh identity/action availability where the session remains valid. No tokens, passwords, record contents, or connection strings in logs or exception messages.

## 4. Creation intents and ambiguous retries

On the first valid Save, freeze a normalized six-field payload and generate one UUID for that creation intent. Disable repeat submissions while pending. The same intent always sends the same key and payload; never generate a fresh key merely because a timeout, disconnect, 5xx, or response-parsing failure occurred.

An ambiguous result locks the submitted payload and offers **Retry same creation**. That explicit retry uses the original key/body, so a committed request returns the existing record rather than creating another. No automatic retry loop. A matching replay can return a record edited since creation: show the returned current state, without overwriting it with the original draft. A 409 may mean conflicting key use or a deleted original; explain safely and do not silently mint another key.

Before submission, drafts are freely editable. After a definitive validation rejection, correct the draft and start a new intent; the rejected request did not create a record. After an unresolved ambiguous result, editing/restarting is blocked until reconciliation or explicit abandonment with a possible-duplicate warning. Navigation, logout, or application exit may abandon memory-only intent data after warning; there is no disk persistence or guarantee of recovery after exit. A later fresh creation must not be presented as a safe retry of the lost intent.

## 5. Edit and delete concurrency

**Edit:** fetch the latest detail and ETag when opening. Retain baseline, local draft, and ETag. On 412 or optimistic 409, fetch latest and show baseline/local/server comparison. Offer discard/reload or explicit review-and-reapply against the newly fetched version; preserve the local draft until the decision. No silent overwrite or automatic merge, including disjoint changes. If the record became deleted/inaccessible, disable Save and explain.

For ambiguous PATCH failure, fetch current state before another Save. Matching values confirm current state, not which actor caused it; offer history. Otherwise compare explicitly. Any subsequent submission uses a reviewed current baseline and exact ETag, with a new conflict handled again.

**Delete:** fetch current active details before opening identity confirmation. Submit once with that version's exact ETag. A 412/409 reloads the record and requires a new confirmation; it never automatically repeats deletion. Following an ambiguous response, an ADMIN-only include-deleted GET can establish the current deletion state. If still active, require fresh confirmation; if deleted, show the confirmed state without claiming which request/actor performed it. A 404 alone does not prove successful deletion. No physical delete or restore.

## 6. Error and visual system

Retain navy navigation, teal primary actions, Segoe UI, light/dark semantic tokens, and the accepted responsive sidebar. Use a distinct accessible destructive style with text labels; never communicate status solely by color. Use visible focus, adequate contrast, wrapping text, scrollable long content, and modal focus containment. Adapt UI UX Pro Max's error-summary guidance to native Tk focus controls; web ARIA attributes are not a Tk accessibility implementation. Screen-reader support must be reported as tested or limited, not assumed.

| Condition | Presentation and recovery |
|---|---|
| 401 / 403 / 404 | Re-login / permission explanation / unavailable record; remove stale private detail |
| 409 / 412 | Creation-key explanation or explicit edit/delete conflict resolution |
| 422 | Safe client field errors where known; generic server validation notice otherwise; retain draft |
| 428 | Missing precondition: reload, never invent an ETag |
| 429 | Honor bounded Retry-After; visible countdown, no automatic mutation replay |
| Service/network/invalid response | Sanitized message; operation-specific reconciliation above |

Loading shows a visible status and disables duplicate actions. Empty history/list states explain the next available action. No arbitrary server response text or submitted values are echoed into error logs.

## 7. Verification strategy

Use TDD for new operation/client behavior and confirmed fixes. Extend existing tests rather than repeat backend coverage without reason.

- Client/state tests: exact headers, strict payloads, all field/date limits, optional clearing, duplicate plates, malformed responses, 16 MiB history bounds, 200 replay vs 201 creation, ambiguous intent retention, changed payload/key conflict, and no credential leakage.
- Real API integration using isolated SQLite and disposable MySQL: both roles, owner-ID enforcement despite renamed employees, original attribution, record/event atomicity, lost create response followed by same-key retry producing one record/CREATE event, stale edits/deletes, history and ADMIN deleted access.
- Worker/session tests: logout/401 while mutation is pending, stale callbacks after another login, queue saturation, no UI calls off-thread, theme rebuild without duplicate submission, close with pending requests and no orphan timers/Tk font destruction on workers.
- Native Windows tests: complete create/edit/delete/history workflows; compact/maximized and both themes; long/Unicode remarks; keyboard/error focus; unsaved-change dialogs; stale conflict comparison; loading/offline/empty states. Record actual DPI and distinguish simulated widget scaling from OS/mixed-monitor testing.
- Extend `scripts.desktop_demo` and its documentation using fictional records and temporary accounts through the existing real API. No shipping bypass or production data.
- Run affected tests per checkpoint. Before publication run desktop/native tests, full default and isolated MySQL suites, independent review, and hosted Windows/SQLite/MySQL CI on the published HEAD. Report skips and untested configurations explicitly.

## 8. Implementation checkpoints after approval

1. **Typed mutation/history contracts and operation state:** API/model extensions, normalization, UUID intent lifecycle, exact ETag rules, and focused failing-then-passing tests; commit verified work.
2. **Create workflow:** reusable form, validation, pending/ambiguous retry UX, navigation/theme retention, real API tests; commit.
3. **Edit and conflict workflow:** ownership controls, partial changes, three-way comparison, explicit reapply, lifecycle/concurrency tests; commit.
4. **Soft deletion and history:** ADMIN confirmations/deleted access, event visualization/pagination, permission and stale-delete tests; commit.
5. **Acceptance and publication:** demo/docs, native screenshots/resizing/themes, full SQLite/MySQL verification, independent review and corrections in meaningful commits; push normally and create one draft Phase 3B PR targeting main. Verify hosted CI; do not merge.

The detailed executable plan will be written after this design is approved. No production changes or Phase 3C work are included.
