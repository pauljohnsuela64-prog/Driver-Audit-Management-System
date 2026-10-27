# Revised Phase 3C — Desktop simplification verification

Baseline: `90d00c56ecd0b33472d0a23ed764ef59ead12b24` (merged Phase 3B).
Approved design: `5ad73e5`. Branch: `feat/dams-desktop-simplification`.

## Delivered scope

- Exactly Dashboard, Driver Audits and My Account in the primary sidebar; removed
  employee/activity placeholders, teaser text and development labels.
- Prominent Dashboard New Audit, available during loading/empty/offline states.
- Shared compact tables with 38 logical px rows, 8 px heading padding, unchanged
  14 px Segoe UI, balanced column widths and subtle alternating theme surfaces.
- ADMIN-only Windows admission; non-ADMIN tokens are revoked before any workspace
  is installed. Revocation failure is disclosed. Generic API/backend roles remain
  compatible and legacy AUDITOR records/accounts are not converted or deleted.
- My Account: safe administrator list, fixed-ADMIN creation, reset another admin
  with reauthentication, disable another with confirmation, and change own password.
  No role picker, account cap, employee directory, activation or account deletion.
- Existing seven audit fields, immutable attribution, stable ownership, idempotent
  creation, ETag conflicts, soft deletion and history remain intact.

## Before/after native table evidence

| Metric | Before | After |
|---|---|---|
| Logical row height | 44 | 38 |
| Row height at actual 150% scaling | 66 device px | **57 device px measured** |
| Logical heading padding | 12 | 8 (12 device px measured) |
| Starting column-width total | 970 | 880 logical px |
| Extra-width distribution | All columns | Driver and Audited By only |

[Before: historical Phase 3A audit table](images/desktop-acceptance/audits-expanded.png)
and [after: current compact table](images/desktop-phase3c/audits-light.png).
The historical image intentionally retains the former navigation as reference;
it is not the current desktop policy.

Actual native display DPI was **144 (150%)**. The real disposable-API acceptance
helper completed 17 screenshots with **zero Python/Tcl callback errors**. It verified
two separate ADMIN logins, legacy rejection, a third admin being added/reset/disabled,
own password change/re-login, separate audit attribution, Create/Edit/Delete/History,
both themes, compact/maximized windows and widget-scale factors 1.0/1.25/1.5.
Actual other OS scaling settings, mixed-monitor transitions and screen-reader
acceptance remain unverified; simulated widget factors are not OS DPI tests.

Selected fictional screenshots:

- [Dashboard and quick creation](images/desktop-phase3c/dashboard-light.png)
- [Compact window/navigation](images/desktop-phase3c/compact-navigation.png)
- [Minimal administrator section](images/desktop-phase3c/admin-accounts-light.png)
- [Empty add form](images/desktop-phase3c/add-admin-form.png)
- [Reauthentication reset form](images/desktop-phase3c/reset-form.png)
- [Explicit disable confirmation](images/desktop-phase3c/disable-confirmation.png)
- [Dark My Account](images/desktop-phase3c/admin-accounts-dark.png)
- [Legacy AUDITOR rejected](images/desktop-phase3c/legacy-rejected.png)

## Engineering and visual review

Independent read-only reviewers examined the core implementation and actual native
screenshots against the approved design. Confirmed findings were reproduced with
failing tests before correction:

- Repeated Refresh could overlap scans: gate current reads and serialize scans
  across view cancellation/theme rebuilds; check cancellation between pages.
- A 403 could retain password forms: clear forms/cards and gate account actions
  until a successful access refresh; keep a visible recovery action.
- Obsolete-session completion could strand a forcibly restored account view:
  refresh current busy state only, never deliver the old result. Normal navigation
  remains blocked while a submitted mutation is pending.
- An empty default-height form frame created a large blank gap: hide it when empty.
- Tab could focus form buttons outside the viewport: reveal focused buttons/cards
  as well as entries. Deferred scroll work belongs to the field/button so destroying
  the form cancels its callbacks.

Additional tests caught theme supersession of ambiguous disable reconciliation;
its read now uses the independent action channel. First-use native keyboard
traversal initializes Tk's lazy focus procedures before Python event callbacks.
All existing worker, session-generation, revocation, timer and UI-owned cyclic
collection safeguards are preserved.

## Verification results

- Account contract/state/generic auth tests: 74 passed at the admission checkpoint.
- Existing native audit/session regressions: 31 passed after ADMIN policy updates.
- Compact table/dashboard native checks: 17 passed.
- New account API/native workflows: 27 passed in default mode; two actual API
  workflows also passed separately using isolated MySQL.
- Review-fix account/contracts: 28 passed. Visual/account/audit native checks: 29 passed.
- Final full default SQLite/native suite: **478 passed, 4 explicit live-MySQL skips**
  in 161.22 seconds.
- Final full isolated MySQL/native suite: **482 passed, 0 skipped** in 274.64 seconds,
  using dedicated test migration/runtime accounts and guarded test-only databases.
- Dependency integrity and Python syntax checks passed. Changed-file credential
  pattern scan found no matches. Ignored configuration and artifacts remain untracked.
- Backend roles/security regression tests are retained; no backend business-rule,
  table, migration or grant changes. Production MySQL and real records were not accessed.

## Demonstration and remaining limits

Run `.\.venv\Scripts\python.exe -m scripts.desktop_demo` from `C:\BHLI-Audit`
in an interactive local terminal. Choose two separate hidden passwords, then use
`demo_admin` and `demo_admin2`. There are 60 active fictional audits (20/40 per
administrator), one archived history example and a separate legacy test account.
See [updated demo steps](WINDOWS_DESKTOP_DEMO.md).

The Windows policy does not narrow the backend ADMIN role's existing powers.
Existing backend reauthentication, concurrent last-active-admin guards, self-access
restrictions, rollback and atomic session revocation remain authoritative.
Account endpoints have no idempotency contract: ambiguous results are not replayed
automatically; a password may already have changed. Passwords and audit retry state
remain memory-only. A request sent before sign-out/close may still commit.

Administrator discovery scans the existing paginated API because no role filter
exists; offset changes may require Refresh. Recovery/reactivation remains in the
existing operator workflow. Packaging, deployment HTTPS/network policy and the
previously documented backend rate-limiting limits are outside this phase.

Publication requires green hosted Windows/SQLite/MySQL CI on the final HEAD.
Keep the Phase 3C pull request draft and unmerged for manual review. No Phase 3D work.
