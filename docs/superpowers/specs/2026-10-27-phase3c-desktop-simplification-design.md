# Revised Phase 3C — A small HR administrator workspace

Status: proposed, awaiting approval. This design supersedes the previous full
Employee Accounts / Administrator Activity desktop direction. No product code
changes are included in this checkpoint.

## Readiness and intent

PR #6 is merged at the supplied baseline `90d00c56ecd0b33472d0a23ed764ef59ead12b24`.
Its [post-merge CI](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40466356074)
passed Windows, SQLite and disposable MySQL jobs. Local main was fast-forwarded;
the clean design branch is `feat/dams-desktop-simplification`. No old Phase 3C
plan or implementation was found in tracked files or the working tree. Existing
branches and Phase 3B commits are preserved.

Optimize for one or two HR people, each signing in with their own ADMIN account.
Do not impose an account-count limit. Preserve the existing navy/teal sidebar,
Segoe UI, light/dark themes, responsive behavior, audit CRUD and safety controls.

**Proposed approach:** one compact Manage Admin Accounts section inside My Account,
with short inline forms and native confirmations. Dedicated account/activity
screens would conflict with the revised navigation. A multi-step wizard adds
unnecessary steps for these small tasks. These are design recommendations, not
an additional user-approved architecture change.

## 1. Sidebar, dashboard and audit workflow

```text
BHLI / AUDIT
  Dashboard       Active-audit count · New Audit · Open Driver Audits
                  Recent audits (shared compact table)
  Driver Audits   New Audit · Search · Refresh · Filters (collapsed)
                  Compact audit table · Existing paging and details
  My Account      My identity · Change My Password
                  Manage Admin Accounts (small expandable section)
```

Use exactly these three primary destinations. Remove the two desktop placeholders,
their dashboard teaser, unused navigation icons and development-phase footer text.
Keep collapse/expand, clear icon labels/tooltips, keyboard focus and responsive
navigation. No role selector is introduced.

Dashboard gets an immediately visible New Audit action beside Open Driver Audits,
including in empty/error states where creating remains possible. Driver Audits
keeps New Audit and Search easy to locate, Refresh adjacent to table actions, and
advanced filters collapsed initially. Preserve filter/sort/page/selection context
and all existing idempotency, ETag comparison, soft-delete and history behavior.

## 2. Compact shared audit table: before / proposed after

Apply through `AuditTable` so Dashboard and Driver Audits remain consistent.

| Property | Current | Proposed starting value |
|---|---|---|
| Row height | 44 logical px | 38 logical px (about 14% reduction) |
| At 150% widget/display scale | Nominally 66 device px | Nominally 57 device px; verify actual metrics |
| Heading padding | 12 logical px | 8 logical px |
| Body typography | Segoe UI, 14 logical px | Retain 14; do not shrink text to create density |
| Columns | 970 logical px total; every column stretches | 880 logical px starting total; only Driver/Audited By stretch |
| Row backgrounds | Single surface | Subtle surface/raised alternating rows in both themes |

Starting column widths: Date 110, Driver 180, Helper 150, Station 150, Plate 120,
Audited By 170 logical px. Suggested readable minima respectively: 100, 130, 110,
110, 100, 140. Preserve manual width adjustment and horizontal/vertical scrollbars;
use horizontal scrolling when compact windows cannot fit readable columns.
Long values remain fully readable in Details. Remarks stays in Details, preserving
the current six-column overview and exactly seven business fields overall.

Selection teal and text contrast override row banding. Retain text-based Deleted
status, focus indicators, Home/End, arrows, Enter/double-click and the existing
binding that stops events after navigation destroys a row widget. Treat these
numbers as initial visual targets, refined only if native checks show clipping.
The local UI UX dataset did not supply a verified Tk-specific density rule;
38 px comes from the user's request, not a claimed accessibility standard.

## 3. My Account and minimal administrator management

Show current full name, username and session expiry without a permissions editor.
Change My Password is a small form; Manage Admin Accounts is an expandable section
with Refresh, Add Administrator, and a short list of administrator account cards.
Each card shows full name, username, Active/Disabled status and a You indicator.
No employee directory, role picker, broad search interface or organizational data.

| Action | Form / confirmation | Existing backend contract |
|---|---|---|
| View administrators | Admin-only cards; show disabled admins too | `GET /users?page=…&page_size=100`, retain only `role=ADMIN` |
| Add administrator | Full name, username, password, confirmation | `POST /users`, fixed `role: ADMIN` |
| Reset another admin | Selected identity, acting admin's current password, new password, confirmation | `POST /users/{id}/reset-password`, `admin_password`, `new_password`; 204 |
| Disable another admin | Fresh target identity/status; explicit default-Cancel confirmation | `PATCH /users/{id}/access`, only `is_active: false` |
| Change my password | Current password, new password, confirmation | `POST /auth/change-password`, `current_password`, `new_password`; 204 |

The listing endpoint has no server-side role filter. Scan its pages in a background
read, filter before UI delivery, and deduplicate by stable user ID. Do not assume
all admins are on page one. Show loading/progress or incomplete-load feedback;
check cancellation/session generation between pages and permit only one scan at
a time. Do not display or retain unrelated legacy account details in view state.
Backend page bounds apply; incomplete scans are never presented as a complete list
or used to decide the last-active-admin invariant. Offset changes may require Refresh.

Username: trimmed, nonblank, at most 100 characters. Full name: trimmed, nonblank,
at most 200. New passwords: nonblank, 15–128 characters; preserve password text
exactly rather than trimming it. Confirm locally and never send confirmation fields.
Current-password fields use existing bounded backend rules. Password inputs are
masked, never logged/persisted, excluded from repr, and cleared after submission
and on navigation/logout; theme changes do not retain a hidden password draft.

Do not offer Reset or Disable on the acting account: use Change My Password instead.
Re-read another target before showing a sensitive form/confirmation; use its stable
ID and require that it is still an ADMIN in that read. Disabled targets remain
disabled after reset; reset does not activate them. No activation, role/profile
editing, deletion or additional account endpoints are included in this scope.
Existing operator recovery procedures remain available outside this desktop flow.

Backend protections remain authoritative: reauthentication on reset, current actor
authorization, self-deactivation denial, concurrent last-active-admin protection,
atomic password/session changes and activity logging. Do not replace these with
client-side counts. Send no role field in disable requests. An external role change
can race a client pre-read; the desktop focus on admins is a presentation policy,
not a new transaction-level restriction on the backend's existing ADMIN powers.

Disable/reset revoke the target's sessions according to the existing API. Own
password change revokes every own session, clears local state, and returns to login
with a success message. Existing auditor-name snapshots and user ownership IDs do
not change when an account is disabled or a password is replaced.

## 4. Desktop admission and legacy AUDITOR compatibility

The Windows application admits ADMIN identities only. Normal login still obtains
a token and `/auth/me`; perform the role admission check on a worker before setting
Application session state or creating the workspace. A non-ADMIN identity receives
clear feedback: this Windows application is for HR administrators. Revoke its
newly issued token on the worker, clear credentials/token references, and stay at
login. If revocation fails, state that server sign-out was not confirmed and the
session may remain until expiry; never claim revocation succeeded.

Defensively guard workspace admission and later identity refreshes too. A 401 or
revoked/disabled session clears all private state. A refreshed non-ADMIN identity
cannot retain desktop access. Keep the generic REST client able to represent both
existing backend roles; place the Windows-only admission policy in a focused
desktop account module, reusing the client's current login/me/logout interface.

This is **desktop access policy**, not removal of backend AUDITOR authorization.
Legacy accounts, roles, records, immutable name snapshots and backend AUDITOR
permission tests remain intact. No user conversion, deletion, migration or data
rewrite occurs. Existing backend administration APIs retain their documented powers.

## 5. Async behavior and safe failure handling

Reuse bounded workers, UI-only callbacks, session generations, independent session
revocation, main-thread cyclic collection, owned timer cleanup and the mutation
channel. Do not place Tk objects in worker captures or make HTTP calls on the UI
thread. Duplicate submissions are disabled; confirmations keep focus contained and
default to Cancel. Use inline field errors plus focusable summaries.

Account operations do not have an idempotency-key contract. Never replay them
automatically or invent one. After ambiguous creation, refresh administrators and
inspect the intended username; finding a matching account does not prove its
password or who created it. Do not generate a different username and retry silently.
After ambiguous disable, re-read status; if still active, require fresh confirmation.
After ambiguous password reset/change, do not claim rollback or test credentials
by logging in as another user. Clear password inputs, explain the unknown outcome
and require an explicit new attempt or login. For own change, return to login and
explain that the replacement password may already be in effect.

Map 401/403/404/409/422/429 and network/service failures to sanitized, action-specific
feedback. Duplicate usernames, self-operation and last-admin conflicts show clear
messages without raw server bodies. Losing permission removes sensitive account
content/actions. Do not expose hashes, tokens, sessions or connection strings.

## 6. Proposed file changes

- `desktop/session.py`, `desktop/app.py`, `desktop/screens/login.py`: three destinations,
  ADMIN-only admission, own-password-change logout and session-safe account delivery.
- `desktop/account_operations.py` (new): small account interface hiding admission,
  admin-only presentation, payload validation and action outcomes from widgets.
- `desktop/api.py`, `desktop/models.py`: typed safe account responses and wrappers
  for existing endpoints; preserve the generic audit/auth contracts.
- `desktop/screens/account.py` and focused account form/dialog module if needed:
  My Account sections and the four short action forms/confirmations.
- `desktop/screens/shell.py`, `desktop/screens/dashboard.py`, `desktop/theme.py`:
  remove placeholder navigation/phase labels, add quick creation, shared row-band tokens.
- `desktop/components/table.py`, small layout adjustments in `desktop/screens/audits.py`:
  shared density/column changes; preserve CRUD, filtering and paging behavior.
- `scripts/desktop_demo.py`, desktop test transports/capture helpers and tests:
  two individually authenticated fictional ADMIN accounts with separate attribution;
  retain a legacy AUDITOR solely for rejected-desktop-login/backend-compatibility tests.
- Current README/desktop/demo documentation: replace obsolete future-module promises
  with this minimal policy; keep earlier specifications and acceptance records as
  clearly historical evidence. No backend, migration, grant or external-service changes.

Names and precise internal decomposition may be refined by the builder, following
existing seams; do not introduce an account-management framework or duplicate
backend business rules.

## 7. Testing, demo and implementation checkpoints after approval

1. **Simplify admission/navigation:** test ADMIN success, non-ADMIN denial and token
   revocation/failure, three destinations, expiry/401, refresh, late completions and
   unchanged backend AUDITOR authorization. Implement test-first; checkpoint commit.
2. **Compact tables and dashboard:** test both shared tables' row/header metrics,
   columns, alternating colors, selected/deleted rows, keyboard actions, filters and
   quick New Audit. Native before/after images at actual 150% scaling, compact and
   maximized, light/dark; checkpoint commit after readable visual verification.
3. **Minimal account flows:** test paginated ADMIN discovery beyond legacy AUDITOR
   pages, add/duplicate/invalid input, current-password reset checks, self/last-admin
   denial including concurrent requests, target-session revocation, own-password
   re-login, disabled targets, rollback, ambiguous outcomes and credential privacy.
   Reuse existing isolated backend security regressions; commit coherent milestones.
4. **Demo and acceptance:** two ADMIN logins with separately attributed fictional
   audits; exercise Create/Edit/Delete/History and account flows through the real
   disposable API. Verify pending actions, logout/close, timer/font cleanup and
   password clearing. Document actual OS DPI versus simulated widget scaling;
   do not claim mixed-monitor/screen-reader checks without performing them.
5. **Review/publication:** full default SQLite, isolated MySQL, desktop/native suites;
   independent engineering and visual review; test-first verified corrections;
   credential/diff check; normal push and one draft Phase 3C PR, then verify hosted
   Windows/SQLite/MySQL CI. Preserve history, keep unmerged and stop at this scope.

Use only isolated test/demo data. Production MySQL, migration revision, grants and
real records are strictly out of scope. The detailed executable plan follows design
approval; no implementation or draft PR is part of this first deliverable.
