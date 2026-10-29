# Phase 4B — Android audit management design

Status: proposed for operator approval; design/research only. No application implementation authorized yet.

Baseline: `54c1f2e1b91d12f570d0bb67b54b25a10f9090d3`, merged PR #10. Both post-merge workflows are successful: [Android](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40678061008) and [SQLite/MySQL/Windows/installer](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40678061043).

## Goal and boundaries

Extend the existing Flutter client with authorized Create, Edit, Soft Delete and History through the existing authenticated FastAPI API. Preserve the seven business fields, original auditor snapshot, stable owner ID, navy/teal Material 3 interface, themes, memory-only sessions, HTTPS rules and lifecycle safeguards.

No backend/schema/grant changes, production access, restore/permanent deletion, account administration, photos, GPS, new fields, offline synchronization, packaging or signed distribution. Windows behavior and all five CI jobs remain intact. This document proposes choices for approval; it does not authorize coding, pushing or a PR.

## Approaches considered

1. **Recommended: full-screen forms and dedicated history route.** Reuse the existing navigation and session controller; add focused mutation/form state modules. Supports long remarks, keyboard scrolling, explicit conflicts and accessibility with minimal dependencies.
2. Bottom-sheet editor: less navigation, but six fields and a 10,000-character remarks limit make keyboard/large-text interactions cramped; not recommended.
3. New state-management/reporting framework or backend orchestration endpoints: disproportionate scope and dependency impact; not recommended.

The recommendation is proposed, not previously selected by the operator. Approval of this document selects approach 1. No new third-party dependency is expected: generate UUIDv4 using Dart `Random.secure`, set RFC version/variant bits, and test exact formatting. Preserve the current pinned toolchain and lockfile.

## Existing contract findings

Authoritative sources: `backend/api/audits.py`, `backend/schemas/audit_api.py`, `backend/services/audits.py`, `backend/api/dependencies.py`; current client in `mobile/lib/core/network/`, `features/auth/session_controller.dart`, `features/audits/`.

| Operation | Contract |
| --- | --- |
| Create | `POST /audits`, six-field JSON, UUID `Idempotency-Key`; 201 new, 200 replay; record plus quoted-version ETag |
| Read | `GET /audits/{id}`; record/version and ETag such as `"3"` |
| Edit | `PATCH /audits/{id}`, nonempty changed-field JSON, exact `If-Match`; 200 record/new ETag |
| Soft delete | `DELETE /audits/{id}`, exact `If-Match`; 204, no response record |
| History | `GET /audits/{id}/history?page=1&page_size=10`; oldest event ID first, page/size/total |
| Archive access | ADMIN may explicitly use `include_deleted=true` on list, detail and history; listing includes active AND archived |

ETag is a quoted positive version, not an audit-ID encoding. Missing If-Match is 428; malformed is 422; stale version is 412. Backend locks updates, checks ownership and version, and commits record/history in one transaction. Even a no-op accepted PATCH advances version and writes history, so the mobile form should avoid sending unchanged patches.

Create keys are globally unique. Replay requires the same owner ID, normalized original CREATE payload and an active record. It compares original CREATE history, not current fields; a replay can return a later edited current record. Reusing a key for another account, changed payload or archived record yields 409. Duplicate plate numbers are valid.

History exposes `id`, `audit_id`, `actor_user_id`, `action`, `before_data`, `after_data`, `created_at`. **No actor-name field exists.** Display `User #<actor_user_id>` (optionally `You · User #id` when IDs match); never fetch an ADMIN-only user directory or infer actor from Audited By. Original Audited By is a separate immutable record snapshot.

## Permissions

| Control | ADMIN | AUDITOR |
| --- | --- | --- |
| Create | Yes | Yes |
| Shared active list/details/history | Yes | Yes |
| Edit active record | Any | Only `record.auditedByUserId == session.user.id` |
| Soft delete active record | Yes | Never |
| Include archived/details/history | Yes | Never |

Use a small pure permission policy for UI visibility, backed by server authorization on every request. Never compare names. Refetch detail/ETag before opening Edit or Delete confirmation; check current session/record permissions again before dispatch. Handle changed roles, deactivation and ownership/visibility failures even when a control was previously visible. Do not change backend roles or Windows admission rules.

## Screens and interactions

Keep Audits as the primary destination and existing Settings behavior. No separate management module.

```text
Audits ── New audit ── six-field form ── Save / safe retry ── saved detail
   └── Detail ── Edit ── prefilled form ── Save / conflict resolution
          ├── History ── event cards ── changed fields
          └── Archive audit (ADMIN, active only) ── confirm ── refreshed list
```

**Audits:** add a labeled New audit action that does not obscure list/paging controls. ADMIN gets an off-by-default Include archived switch with help “Show active and archived audits”; when enabled mark archived rows with text and icon. AUDITOR never sees or submits the option. Preserve search/date/sort and page-25 behavior; successful mutation refreshes affected detail and marks prior list data stale, returning to page 1 with applied filters. If saved data no longer matches filters, explain that rather than inserting a misleading row. List refresh failure must not reverse a confirmed save. After archiving with inclusion enabled, say the archived read-only row may remain visible.

**Create/Edit:** full-screen scrollable form, single column on phones, maximum readable content width on tablets. Logical order: Driver Name, Helper Name (optional), Audit Date, Station, Plate Number, Remarks (optional). Use visible labels, helper text and field-specific errors. Date picker plus accessible YYYY-MM-DD entry; initial create date uses local calendar today, not a UTC-truncated instant. Preserve identifiers as entered after server-equivalent trimming. Multiline remarks expands within the page and shows a character counter near its limit. Audit identity is read-only: Create says the server assigns Audited By; Edit shows the original snapshot. Never submit identity or internal metadata.

Use an accessible Save action and Cancel/Back; avoid keyboard-covering sticky controls by respecting IME/safe-area insets and scroll-to-first-error. No autosave. Back with dirty, unsent fields asks Discard changes / Keep editing. Saving disables duplicate submission. Back while pending asks whether to stop waiting, with explicit notice that the server may still save; it must not promise rollback. Drafts exist only in RAM and are erased on logout, session replacement or process death.

**Conflict:** retain the draft and original baseline in RAM while the same authenticated session is active. For 412 or relevant 409, show “This audit changed. Review the latest version before saving.” Fetch latest server detail. For each locally changed field, stack Your proposed value / Latest saved value vertically; identify fields changed by another request since editing began. Default untouched fields to latest values, preserving unrelated concurrent changes. Require an explicit latest/proposed choice for each differing locally changed field before enabling Save reviewed changes. Continue reviewing stays in the comparison; Discard my changes and use latest requires confirmation. A failed latest fetch keeps the draft, offers Retry and leaves Save disabled. Never attach a fresh ETag and resend automatically. Deliberate resubmission sends only the reviewed diff against the newly fetched baseline; another conflict repeats review. If archived, absent or no longer authorized, remove edit/delete controls and stop saving.

**Delete:** use **Archive audit** consistently in user-facing controls, with ADMIN-only destructive styling and confirmation naming Record ID, driver and plate. Say “Archive this audit? It will leave the active list. Its history is retained.” Actions: Cancel / Archive audit. Freeze the fetched ETag for that confirmation; a changed version requires a fresh review and confirmation. No restore or permanent delete. On success say Audit archived, clear detail and refresh list. Archived details show persistent Archived · Read-only, with History available only under authorized include-deleted access.

**History:** paginated event cards, **10 per page**, oldest first (match server ordering). UPDATE events contain full before/after snapshots: 25 worst-case escaped remarks can exceed 2 MiB. Ten events fit the current JSONResponse `ensure_ascii=False` worst-case six-byte escaping per code point, retaining the transport cap; test the real serializer at maximum field sizes and escaped controls. Oversized unexpected responses fail safely without truncating events. Show CREATE/UPDATE/DELETE as Created/Updated/Archived, actor ID, local display time plus timezone, and expandable field differences. Label actors Changed by User #17, or Changed by you · User #17 only for exact ID equality; help explains “Account IDs identify action authors. Audited By is the original audit attribution.” Offer UTC detail for clarity. Show only allowlisted seven business fields and lifecycle status relevant to deletion; never render arbitrary snapshot keys, raw JSON, hashes or other metadata. Null uses “Not provided,” empty/long/Unicode values wrap, and before/after direction is labeled. History remains read-only; missing/forbidden records stop history access. Offset pagination can shift while events are appended: Refresh restarts page 1; do not claim a consistent snapshot or newest-first endpoint.

## Validation and serialization

| JSON field | Rule after backend-equivalent normalization |
| --- | --- |
| `driver_name` | Required string, trimmed, 1–200 Unicode code points |
| `helper_name` | Optional/null, trimmed blank → null, at most 200 code points |
| `audit_date` | Real calendar date, exact YYYY-MM-DD, year 1000–9999; no invented future-date restriction |
| `station` | Required trimmed string, 1–150 code points |
| `plate_number` | Required trimmed string, 1–30 code points; no uppercase coercion or uniqueness rule |
| `remarks` | Optional/null, trimmed blank → null, at most 10,000 code points |

Match **field-specific backend trimming**, not a single generic Dart/Python trim. Required Name/Station/Plate fields use Pydantic StringConstraints: trim Unicode White_Space (U+0009–000D, U+0020, U+0085, U+00A0, U+1680, U+2000–200A, U+2028–2029, U+202F, U+205F, U+3000). Optional Helper/Remarks first use Python `str.strip`, which additionally trims U+001C–001F. Both preserve U+FEFF. A local AuditCreate probe confirms U+001C is retained for driver_name but stripped for helper_name, NBSP/NEL are trimmed for both and BOM retained for both. Use explicit sets and backend golden vectors rather than assuming Dart `trim` matches either. Count Dart runes, not UTF-16 code units or grapheme clusters, for Python-compatible limits. Do not add NFC/case normalization. Client validation improves feedback; the server remains authoritative. Avoid restrictive input formatters that silently truncate paste or break composing input; show errors and prevent submission instead.

Create serializes only these six keys with explicit nullable optional values. PATCH sends only normalized changed keys; clearing optional fields sends JSON null, whereas omission means unchanged. Reject an empty normalized patch locally. Do not reuse the existing `Map<String,String>` transport body signature for nullable mutation JSON: use a narrow typed payload serializer returning `Map<String,Object?>`.

## Mutation state and uncertain outcomes

Create owns one immutable normalized payload plus UUID key per submitted attempt. Generate the key immediately before first dispatch, disable double-tap, and keep the exact key/payload for all retries of that attempt. Never generate a fresh key just because a timeout occurred. While outcome is unknown, show “Save not confirmed. This audit may already exist.” Lock that attempt's submitted values and offer Retry same save or Leave this screen. Leaving retains the single attempt in the authenticated session's RAM and shows an Audits banner “Unconfirmed audit save · Review”; Review reopens the frozen attempt. New audit offers Resume unconfirmed save or explicitly Abandon retry information, with acknowledgment that creating again may duplicate a saved audit. No automatic mutation retries or unbounded pending-attempt collection.

Successful create accepts only 200/201, validates record/ETag, and displays the returned current record. A replay may differ from submitted values due to subsequent edits; do not misclassify this as protocol failure or overwrite it. A 409 does not mean a new key is safe: stop and offer review of the audit list, because original creation may already exist or have been archived. There is no lookup-by-key API. Process death/logout loses the RAM-only attempt/key; the client cannot detect a prior interrupted attempt after restart. On every new-create entry show a short reminder: “If a previous save was interrupted, check Audits before creating again.” Do not claim durable exactly-once behavior without a separate persistence/backend design.

PATCH and DELETE have no idempotency key. On timeout, canceled wait, malformed success or uncertain network/5xx outcome, say the result is unconfirmed and refetch before further mutation. Retrying an identical PATCH with its original ETag can yield 412 if it already succeeded; never retry with a refreshed version automatically. Refetched matching values help explain state but do not prove which request/actor caused the change. For ambiguous DELETE, ADMIN can refetch with `include_deleted=true`: archived confirms present archived state, active allows a newly reviewed action, 404 remains unknown/unavailable rather than proof of successful deletion.

Transport cancellation stops waiting/receiving; it cannot undo a server transaction. This limitation applies to logout, backgrounding and connection loss. Do not show “Canceled without saving” after dispatch.

## Architecture and session safety

Reuse `ApiClient`, `SessionController`, existing per-screen controllers and native privacy adapter. Add typed write/history contracts, a pure permission policy and focused form/mutation/history state modules. Keep network code out of widgets, bearer access inside the session module, and API calls asynchronous. Preserve 20-second full-request deadline, 2 MiB response cap, redirect rejection, strict HTTPS and sanitized errors. No networking/database access from a desktop dependency or direct MySQL connection.

Proposed typed interfaces (names finalized by the implementation plan): `AuditDraft.normalized/validate/toCreateJson/diff`, `PendingAuditCreate(key,payload)`, `AuditHistoryPage/Event`, `AuditPermissions.canEdit/canDelete/canIncludeArchived`, and token-free session methods `createAudit(attempt)`, `updateAudit(id,etag,patch)`, `deleteAudit(id,etag)`, `fetchAuditHistory(id,page,includeDeleted)`.

Use a separate mutation request scope, never the list/detail cancellation scopes. Permit one in-flight audit mutation and one retained uncertain create attempt per authenticated session; do not queue writes in the background. **Use a separate session-owned mutation latch, not existing authentication/resume `_busy`.** Logout must remain callable during writes, and pending writes must not bypass shared/awaited resume identity verification. Capture origin, session generation, identity ID, payload and ETag at dispatch. Session changes cancel all owned transports, erase drafts/keys/history and suppress late results, including old 401s that must not terminate a newer session. A mutation response arriving after logout may reflect a committed server operation but must never reopen routes or restore data. Backgrounded UI stays concealed. No automatic resend on resume.

On logout during an in-flight operation, local session clearing is immediate; show the uncertainty warning before the user's explicit choice where possible, then erase sensitive draft state. No token, draft, key, snapshot or retry journal is written to preferences, saved state, logs or disk. New account/new origin must never inherit a pending attempt.

Archived support requires explicit access mode in current models/API reads: Phase 4A's unconditional archived-record rejection must remain the default, relaxing only for an authenticated ADMIN request that explicitly includes deleted records. Unexpected archived responses to active-only or AUDITOR requests remain protocol/authorization failures. Never make the parser generally permissive merely to support archive browsing.

## Error contract

| Condition | User behavior |
| --- | --- |
| Local invalid / server 422 | Keep draft, explain field constraints; server currently supplies a safe general error, so do not invent a field-error JSON format |
| 401 / expired session | Clear protected state and return to login; mutation may be unconfirmed |
| 403 | Keep no unauthorized record/edit state; explain permission changed; revalidate identity and refresh visibility |
| 404 | Record unavailable; do not imply permanently deleted; exit unsafe editor/history |
| 409 | Contextual conflict; create key is not rotated automatically; mutation refetch/review |
| 412 | Stale baseline; retain same-session draft, require explicit conflict review |
| 428 / malformed ETag | Fail closed; refetch proper detail, no unconditioned retry |
| 429 | Respect bounded Retry-After feedback; no automatic write retry |
| Timeout/offline/5xx/canceled wait | Safe message; distinguish definite pre-dispatch failure from unknown post-dispatch result |
| Malformed/oversized/redirected response | Sanitized failure; a mutation's outcome may still be unknown |

Never display raw exception text, database messages, HTTP bodies or bearer values. Preserve server status/code internally for deterministic UI behavior.

## Accessibility and visual acceptance

Reuse navy/teal semantic tokens and Material icons, light/dark surfaces, 48dp touch targets, readable typography and bounded content width. Use visible labels and text feedback rather than color alone. Keep inline errors and saving announcements accessible through semantics/live regions; focus the first invalid field. Password managers/login accessibility and privacy behavior remain untouched.

Test phones at 320/360 logical pixels, landscape, tablet width, 200% and largest supported system text, keyboard open, system Back and discard/confirmation dialogs. Android Back first dismisses an open keyboard; subsequent route Back follows dirty/uncertain draft rules. App-bar Back and Cancel apply the same draft rules. Single-line inputs use Next; Remarks uses newline, never implicit submission. Narrow/large-text action groups wrap or stack; dialogs and comparisons scroll with every action reachable. Provide buttons for gestures, labeled history expansion and Previous/Next. Preserve normal platform focus/ripple behavior and reduced-animation settings. Long remarks/history comparisons must scroll without hiding actions or overflowing. Actual TalkBack and physical-device checks must be reported as verified or unverified, not inferred from widget tests.

## Verification and delivery gates after approval

1. Contract/unit TDD: exact Unicode normalization/limits, null versus omission, UUID format/key reuse, permissions by ID, response statuses/ETag matching, strict history/snapshot allowlists and archived modes.
2. State/widget tests: form errors, double-tap, dirty Back, pending cancel warnings, same-key retry, replay after later edit, conflict review, logout/new login/old responses, role change, error/empty/loading, both themes/large text and keyboard-safe layouts.
3. Disposable real-API tests: two roles plus a second AUDITOR; create, shared read, owner edit and non-owner denial, ADMIN edit/delete, history order/before-after, immutable attribution, archived ADMIN access and AUDITOR denial. Exercise duplicate plates, same-key concurrent creates, stale ETags and concurrent edit/delete using existing backend guarantees; no backend business changes.
4. Fault injection: dropped create response after server commit, dropped PATCH/DELETE response, cancellation/logout during write, session expiry and malformed success. Verify exactly one CREATE event for same-key retries and no false rollback claim.
5. Native Android acceptance: fictional fixture only, actual touch/keyboard forms, two roles/ownership, conflicts/history, themes/rotation/background/process death/Back, scroll and preview privacy. Serialize builds/emulator/large suites. Reuse the retained API36 emulator with the verified host-GPU workaround; API24/physical/TLS/TalkBack gaps remain explicit until tested.
6. Full Flutter analysis/format/tests, full default/isolated MySQL and applicable Windows/native regressions; preserve all five hosted jobs. Meaningful checkpoint commits and independent engineering/security/UX review before eventual draft publication, which requires separate implementation authorization.

## Approval requested

Approve the full-screen form/history approach, ADMIN-only Include archived option, actor-ID history labels, explicit uncertain-write/retry workflow and implementation checkpoints. No implementation, push or PR is permitted until approval.
