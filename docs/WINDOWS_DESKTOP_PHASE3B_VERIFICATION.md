# Phase 3B verification and acceptance

Baseline: merged Phase 3A `2757d68811468e8961b77ed64193a0030f8950e1`.
Approved design: `b888cbf`. Branch: `feat/dams-audit-management`.

## Delivered behavior

The existing sidebar workspace now supports six-field creation with server-owned
Audited By, ownership-aware editing, ADMIN soft deletion, and chronological audit
history. ADMIN can explicitly include deleted records. The seven business fields,
stable owner IDs and historical auditor names are preserved. Desktop traffic uses
only the existing REST API; backend code, migrations and grants are unchanged.

Creation freezes a UUID and normalized payload across ambiguous retries. Editing
uses changed fields and exact ETags with explicit original/local/latest comparison.
Deletion fetches current identity/version, requires confirmation, and never silently
replays DELETE. An ambiguous outcome is reconciled through a permitted read.
Separate mutation delivery is session scoped, survives read supersession and theme
rebuilds, and cannot update a later account's workspace.

## Independent review and corrections

Fresh engineering/spec and UI/maintainability reviewers examined the cumulative
implementation. Confirmed medium-severity findings were reproduced and corrected:

- Invalid drafts entering comparison could become frozen: validate before comparing.
- Failed pre-edit/pre-delete reads left stale details actionable: remove unavailable
  content and actions on 403/404, including deletion reconciliation failures.
- A deleted/inaccessible edit could repeat PATCH: retain the draft but block Save.
- DELETE history hid unchanged business fields: show the retained business snapshot.
- Remarks intercepted Tab/Shift-Tab: explicit traversal and focus-driven form scrolling.

History selection also restores keyboard focus. Native visual checks identified and
corrected compact-form half-width inputs and Windows dialog teardown/scaling issues.

A full mixed native/demo run exposed Tk font finalization on an API worker. Stack
diagnostics showed `tkinter.font.__del__` on the worker while the UI thread waited
for a demo HTTP response. Automatic cyclic GC is now paused for the application
lifetime and replaced by UI-thread collection every two seconds; close restores
the previous setting. A regression measures actual collector thread ownership.
The mixed native/demo regression passed 36 tests after correction. Pending-login
close remains prompt, releases fonts, revokes late sessions, and reports no callbacks.

## Local verification

- Full default suite with native Windows enabled: **446 passed, 4 skipped** in
  125.74 seconds. All four skips explicitly require live MySQL.
- Full isolated MySQL/native suite: **450 passed, 0 skipped** in 266.15 seconds,
  using the guarded dedicated test database and separate migration/runtime accounts.
- Real API desktop integration: four tests passed separately in both database modes,
  covering lost committed create response/retry, stable attribution after rename,
  ownership denial, stale ETag and soft-delete/history permissions.
- Dependency integrity and Python syntax checks passed; changed-file credential
  pattern scan found no matches. Ignored `.env`, `local/` and `artifacts/` are untracked.
- No production database access, schema execution or grant changes were performed.

## Native visual evidence

`python -m tests.desktop.audit_acceptance_capture` uses a real disposable HTTP API,
temporary SQLite, normal authentication and generated memory-only credentials.
It completed Create/Edit, concurrent edit/reapply, Cancel/Delete, deleted history,
both roles and both themes, compact/maximized windows, with **zero Python/Tcl
callback errors** and 13 screenshots under ignored `artifacts/desktop-phase3b/`.

Actual display DPI: **144 (150%)**. Widget factors 1.0, 1.25 and 1.5 were exercised;
these are simulated widget scaling, not tests at three different OS DPI settings.
Other actual OS scaling settings, mixed-monitor transitions and screen readers
remain unverified. Screenshots contain fictional records only.

Selected evidence is retained under `docs/images/desktop-phase3b/`:

- [Create, light theme](images/desktop-phase3b/create-light.png)
- [Compact Create, dark theme](images/desktop-phase3b/create-compact-dark.png)
- [Explicit edit conflict comparison](images/desktop-phase3b/edit-conflict.png)
- [Soft-delete identity confirmation](images/desktop-phase3b/delete-confirmation.png)
- [Deleted history, light theme](images/desktop-phase3b/history-light.png)
- [Deleted history, dark theme](images/desktop-phase3b/history-dark.png)

## Manual demonstration and limitations

From `C:\BHLI-Audit`, run `.\.venv\Scripts\python.exe -m scripts.desktop_demo`
in a local interactive terminal. Choose separate hidden ADMIN/AUDITOR passwords,
then sign in as `demo_admin` or `demo_auditor`. There are 60 active fictional records
(40 owned by AUDITOR) and one archived CREATE/UPDATE/DELETE example. See
[complete demo steps](WINDOWS_DESKTOP_DEMO.md). Closing removes the disposable API
and database; no shipping authentication bypass exists.

Unresolved creation intents are memory-only and lost on exit/logout after warning.
Inspect server records before creating a replacement intent. A sent request may
commit after local cancellation/logout. History actors are server-provided IDs,
not resolved employee names. Offset pages may shift during concurrent writes.
Windows account-management screens remain future work. Deployment HTTPS, trusted
networking and backend rate-limiting limitations remain as previously documented.

The local verification gate passed. Hosted Windows/SQLite/MySQL CI must also pass
on the published HEAD; results are recorded in the draft PR and completion report.
The Phase 3B PR must remain draft and unmerged for final review.
