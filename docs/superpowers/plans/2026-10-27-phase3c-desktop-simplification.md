# Phase 3C Desktop Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Execute task-by-task with TDD and verified commits; approval already authorizes implementation and publication.

**Goal:** A compact desktop for individually authenticated HR administrators.
**Architecture:** Preserve the existing API, worker, session and Tk lifecycle seams. Add a small account-operation module and My Account forms; reuse the shared audit table.
**Tech Stack:** Python 3.14, CustomTkinter 6, existing FastAPI REST endpoints, pytest and native Windows Tk.
**Spec:** `docs/superpowers/specs/2026-10-27-phase3c-desktop-simplification-design.md`, approved at `5ad73e5`.

## Global Constraints

- Exactly Dashboard, Driver Audits, My Account as primary destinations; desktop admission ADMIN only, backend roles unchanged.
- Row height starts at 38 logical px, heading padding 8; retain 14 px Segoe UI and readable columns in both shared tables.
- Existing seven business fields, ownership, immutable attribution, idempotency and ETag safeguards remain intact.
- HTTP only on bounded workers; memory-only credentials; preserve session generations, revocation, timer and UI-thread GC safeguards.
- No production DB, migrations, grants, legacy-account conversion, role picker, activation endpoint, Phase 3D or unrelated features.
- Preserve history, commit on the assigned branch, publish one draft PR and verify CI; do not merge.

## Review Focus

- Rejected non-ADMIN token revocation failure must be explicit and never admit a workspace (Task 1).
- Administrators beyond a page of legacy users must not disappear from the list (Task 3).
- Theme/navigation during pending password mutation must clear secrets and safely deliver outcomes (Task 3).
- Ambiguous non-idempotent account operations must never auto-replay or claim rollback (Task 3).
- Compact/high-DPI tables must keep keyboard focus, headers, selection and scrollbars readable (Tasks 2/4).

## Task 1: Desktop admission and navigation

Files: `desktop/account_operations.py` (new), `desktop/app.py`, `desktop/session.py`, shell/login/dashboard; new `tests/desktop/test_accounts.py`; update desktop-only native role tests.
Interfaces: `desktop_sign_in(client,username,password) -> Login` rejects/revokes non-ADMIN; `SessionState.destinations` exposes only three choices for ADMIN, none otherwise. Generic ApiClient sign-in remains backend-role compatible.

- [x] Add failing tests for admission/revocation failures and three destinations; observe RED.
- [x] Implement worker-side policy plus defensive UI admission; remove placeholders/phase labels.
- [x] Run focused state/auth/native tests; preserve backend AUDITOR tests and commit verified changes.

## Task 2: Compact audit workspace

Files: shared table/theme, dashboard/audits; native tests and captures.
Interfaces: shared `AuditTable` uses 38 logical px rows, 8 px headings; starting widths 110/180/150/150/120/170, only Driver/Audited By stretch; alternating theme tokens.

- [x] Add failing metric/column/row-tag and dashboard quick-create tests.
- [x] Implement shared density, quick New Audit including empty/error dashboard; preserve active audit query context and scroll/key behavior.
- [x] Run native checks at available DPI and both themes/window sizes; commit.

## Task 3: Essential administrator account actions

Files: client/models, account operations, `desktop/screens/account.py`, focused account form module, new account/API/native/integration tests.
Interfaces: safe `Account`/`AccountPage`; client `list_users`, `get_user`, `create_admin`, `reset_admin_password`, `disable_admin`, `change_password`; `list_admins(client,token,cancelled)` filters all pages before UI delivery. Screen contains expandable list and Add/Reset/Disable/own-change forms, no role input.

- [x] Add failing contract tests for payload allowlists, field bounds, safe responses, paginated filtering and cancellation.
- [x] Implement typed API wrappers and pure validation; test RED→GREEN.
- [x] Add failing native/real API tests for creation/duplicates, reset reauth, disabled target, self/last-admin protection, own change/logout, session revocation, forbidden/unavailable states, pending actions and ambiguous outcomes.
- [x] Implement My Account actions via session-scoped workers and mutation delivery; clear password inputs on submission/navigation/theme/logout; never retain them in drafts.
- [x] Run focused default and isolated MySQL regressions, including existing backend account concurrency/rollback tests; commit stable milestones.

## Task 4: Two-admin demo and acceptance

Files: disposable demo, test transports, capture helpers, desktop docs/screenshots.

- [x] Test two independent ADMIN accounts and distinct historical attribution; retain separate legacy AUDITOR for rejection/compatibility checks.
- [x] Extend real disposable demo and actual native capture for account actions plus Create/Edit/Delete/History, both themes, compact/maximized and 150% actual DPI.
- [x] Run full default/native and isolated MySQL suites; preserve explicit skips. Verify syntax, dependencies, clean shutdown, no production access; commit evidence.

## Task 5: Independent review and publication

- [x] Fresh engineering/spec and UI/maintainability reviews against the approved design; reproduce and fix confirmed issues test-first, run affected/full verification as warranted, commit.
- [ ] Inspect cumulative diff, credentials and ignored config; normal push, create one draft PR targeting main and verify hosted Windows/SQLite/MySQL CI on final HEAD.
- [ ] Record results in PR/final report; verify clean synchronized branch, unchanged main, draft/unmerged status. Stop at Phase 3C.

## Execution evidence

- `c6a8cba`: ADMIN-only admission, safe API contracts and three destinations; 74 contract/state/generic-auth tests and 31 existing native audit/session checks passed.
- `e6cc7e2`: compact shared tables and persistent Dashboard New Audit; 17 native checks passed.
- `91fba92`: essential administrator forms and session-safe actions; 27 focused tests passed; two actual account/API tests also passed in isolated MySQL.
- `370b8b6`: engineering-review recovery fixes; serialized/cancelled scans, 403 cleanup, obsolete-result status recovery. The obsolete-view test deliberately uses forced internal navigation; ordinary navigation remains blocked during pending writes.
- `bf2dc2b`: two-admin disposable demo and real-API native acceptance tooling; five demo tests passed.
- `a027e47`: visual-review spacing/keyboard corrections and first-use Tk focus initialization; 29 native account/audit tests passed.
- Final acceptance: 17 screenshots, zero Python/Tcl callback errors, actual DPI 144, measured 57 device px rows, simulated widget factors 1.0/1.25/1.5.
- Final default/native suite: 478 passed, four explicit live-MySQL skips. Final isolated MySQL/native: 482 passed, no skips. Hosted results are recorded in the verification document/PR/completion report.
