# BHLI Audit Windows desktop

Implemented desktop: individual ADMIN sign-in, collapsible navigation,
dashboard with real active-audit totals, searchable/filterable/paginated audit table,
separate details, audit creation/editing, ADMIN soft deletion, chronological history,
My Account, appearance selection, Excel export and sign-out. Client-only packaging
and a per-user Windows installer are implemented; production distribution remains
separate. See [installation](WINDOWS_INSTALLATION.md), [Excel export](WINDOWS_DESKTOP_EXPORT.md)
and [current release readiness](RELEASE_READINESS.md).
The three primary destinations are Dashboard, Driver Audits and My Account.
The desktop admits individually authenticated ADMIN accounts only.
The desktop preserves the seven audit business fields and original auditor snapshot.

The [Phase 3C verification and before/after screenshots](WINDOWS_DESKTOP_PHASE3C_VERIFICATION.md)
record the historical desktop simplification checkpoint.

See the [Phase 3B verification and screenshots](WINDOWS_DESKTOP_PHASE3B_VERIFICATION.md)
for independent-review corrections, complete local test results and native evidence.

## Setup and launch

For safe manual inspection without MySQL or existing server configuration, use the
[disposable real-API demonstration](WINDOWS_DESKTOP_DEMO.md):
`python -m scripts.desktop_demo`. It prompts for two hidden local passwords and
opens this same application with fictional data and normal authentication.

Python 3.14 with Tcl/Tk is required. From `C:\BHLI-Audit`, an independent desktop
environment can be installed without backend/database packages:

```powershell
py -3.14 -m venv .venv-desktop
.\.venv-desktop\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv-desktop\Scripts\python.exe -m desktop
```

Alternatively install `requirements-desktop.txt` into the existing `.venv`, then
run `.\.venv\Scripts\python.exe -m desktop`. Backend dependency pins are unchanged.
CustomTkinter 6.0.0 was selected after native Python 3.14.3/Tk 8.6 rendering checks.
Pillow provides locally drawn DPI-aware icons; no external images/fonts are fetched.

For an already approved/configured backend only, an operator can launch it as
below. The disposable demo above requires none of these production prerequisites:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

See [database setup](DATABASE_SETUP.md) and [authentication](AUTHENTICATION.md).
This guide does not approve production revision 0002 or its grants.
Do not start an unprepared production rollout merely to test the GUI. Native checks
use a fictional transport; real API integration tests use isolated test fixtures.

Source development defaults to `http://127.0.0.1:8000`; an unconfigured frozen
client instead requires first-launch API setup. Override without database credentials:

```powershell
$env:DAMS_DESKTOP_API_URL = 'https://audit-api.example.com'
.\.venv-desktop\Scripts\python.exe -m desktop
# Or: python -m desktop --api-url https://audit-api.example.com
```

Only HTTP(S) origins are accepted, without URL credentials, paths, queries or
fragments. HTTP is limited to literal loopback/localhost. Remote HTTPS uses the
system/default trusted certificate store and certificate verification; redirects
are not followed. Use an operator-managed trusted certificate for internal HTTPS.
There is no insecure TLS switch. Desktop configuration never loads server `.env`.

## Interaction and design

Navy navigation, teal actions, Segoe UI and semantic light/dark surfaces follow the
[approved design](superpowers/specs/2026-10-26-phase3a-desktop-design.md). A 232-unit
sidebar collapses to a 64-unit icon rail with labels available as tooltips. Compact
windows collapse navigation, while tables scroll horizontally and long details
scroll vertically. The window starts within the available screen dimensions after
conversion to logical DPI units. Focus indicators and errors do not rely on color alone.

Every HR administrator sees Dashboard, Driver Audits and My Account. Dashboard has
a prominent New Audit action, including empty/offline states. Both shared tables
use 38-logical-pixel rows (previously 44), 8-pixel heading padding, alternating theme
surfaces and balanced columns; only Driver/Audited By absorb extra width.
“My audits” filters by the authenticated stable account ID, not display name.
The dashboard total is for all active visible records, never a fabricated personal metric.

Search by driver, plate or station; expand Filters for station/date range/My audits.
Apply resets the page; clear removes filters. Dates use `YYYY-MM-DD`. Sort by
creation ID or audit date ascending/descending. Page sizes are 25/50/100. Refresh
reloads the current query. Concurrent server writes can shift offset pages.
Enter/double-click or View Details opens the selected audit. Back retains query/page
and selected ID. Details display Driver Name, optional Helper Name, Audit Date,
Station, Plate Number, optional Remarks and original Audited By.

New audit opens a validated six-field form; the server supplies Audited By. ADMIN
can edit any active audit. Backend AUDITOR ownership permissions remain unchanged
for compatible clients; AUDITOR identities are not admitted to this Windows UI.
Only changed fields are submitted with the exact GET ETag. A stale/ambiguous edit
requires explicit original/draft/latest comparison and review before another Save.
ADMIN deletion fetches current identity/version and requires confirmation; stale
deletion requires a new confirmation. Deletion preserves history and ownership.
ADMIN can enable Include deleted in Filters to inspect read-only deleted details/history.
History shows chronological actions, UTC timestamps, actor IDs and before/after changes,
25 events per page. Actor IDs are distinct from original auditor-name snapshots.

Ambiguous creation retains the original UUID and normalized payload in memory.
Retry same creation reuses both; editing is locked until reconciliation or explicit
abandonment with a duplicate-risk warning. No automatic mutation replay exists.
Drafts survive theme changes. Leaving unsaved work asks for confirmation; leaving
a submitted request cannot undo a server commit. Exiting loses unresolved retry
state: inspect records before starting another creation. A new login never inherits it.

Tab/Shift+Tab traverse controls; Enter signs in or opens a selected row; Space
activates buttons/checkboxes; dropdowns can be opened with Enter/Space and navigated
with arrow keys. Home/End select table edges. Ctrl+F focuses search, F5 refreshes,
Escape dismisses the account menu or returns from details. Screen-reader support
must be assessed with Windows assistive technology; native Tk accessibility is not
equivalent to browser ARIA support.

## Architecture and security

My Account contains Change My Password and an expandable Manage Admin Accounts
section: view ADMIN accounts, add another ADMIN, reset another's password with
current-password reauthentication, or disable another after fresh confirmation.
There is no role picker, account-count limit, employee directory, profile editor,
activation control or account deletion. Backend self/last-active-admin guards and
transactional session revocation remain authoritative. Own password change revokes
all own sessions and requires sign-in again. Resetting a disabled account preserves
its disabled status. Existing operator recovery procedures remain available.

Windows admission checks the `/auth/me` role on a worker before creating session/UI
state. A non-ADMIN token is revoked; failed revocation is disclosed without exposing
the token. Backend roles, legacy accounts, records and immutable attribution are
not converted or removed. Administrator discovery filters all `/users` pages before
view delivery, with cancellation and serialized scans. Password inputs are masked,
cleared on submission/navigation/theme/logout and never stored in application drafts.
Account writes have no idempotency contract: ambiguous outcomes are not automatically
replayed. Refresh/check status or explicitly retry with reauthentication as appropriate.

`desktop/api.py` owns HTTP, bounded 16 MiB response size (including full Unicode pages), 5-second connection and 15-second
read timeouts, strict data parsing and sanitized errors. `models.py` owns immutable
responses and audit query validation. Screens receive an injected client; test
transports and the real HTTP transport use the same interface. No backend ORM,
database driver, business mutation logic or MySQL configuration is imported.

Login calls `/auth/login`, then `/auth/me` before enabling the workspace. Tokens
exist only in process memory and are hidden in data representations; passwords
are cleared from the form after submission and worker captures released after use.
Python does not guarantee secure zeroing of freed memory. No remember-me, registry
token, token file, request-body logging or automatic credential retries exists.

`session.py` owns identity/expiry/generation. `tasks.py` uses four daemon workers and
at most eight outstanding screen requests; the main thread drains completions.
Navigation and supersession invalidate stale results, including stale errors. Even
if a replacement request is refused because the queue is full, the previous query
cannot update the screen under new filters. Workers never invoke Tk or retain UI
callbacks. A separate single-operation mutation queue retains write results across
read supersession and theme rebuilds, and discards delivery after session changes.
Independent bounded revocation work cannot be canceled by navigation or
starved by a full screen queue. Closing suppresses late UI callbacks and performs
best-effort revocation without waiting indefinitely.

While the single application is open, automatic cyclic collection is replaced by
UI-thread collection every two seconds. This prevents detached Tk font/image cycles
from finalizing on HTTP/API workers; reference counting remains enabled. Closing
collects remaining views on the UI thread and restores the previous GC setting.

Logout clears local identity, token and audit views immediately and requests server
revocation. Unconfirmed revocation is reported: a server session may remain until
expiry after a network failure/process exit. Abandoned successful logins are best-
effort revoked. Sessions have no refresh; expiry or a current-request 401 requires
new login. Server authorization remains authoritative despite role-based navigation.

403 is permission denial; 404 removes unavailable details; known conflict codes for
409/412 require operation-specific conflict resolution; 422 gives safe validation feedback. 429
uses a nonblocking Retry-After cooldown (numeric or HTTP-date), including read-screen
retries. Untrusted delays are bounded to one day before native arithmetic. Polling
continues after a reported callback failure, preserving later completion/expiry handling.
Network/500/503 errors offer manual retry without raw exceptions, SQL,
tokens or server-provided messages. HTTP 204 is handled without JSON decoding.

## Testing and visual evidence

Install backend dependencies as well for pytest's shared fixtures. No production
database is required for default desktop checks:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
.\.venv\Scripts\python.exe -m pytest tests/desktop -q -rs
# Native Windows checks (requires an interactive desktop/Tk installation):
$env:DAMS_DESKTOP_GUI_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/desktop -q
.\.venv\Scripts\python.exe -m tests.desktop.visual_capture
```

The visual harness renders the actual application using fictional API responses,
captures only its HWND through Windows GDI, and writes ignored PNGs and metadata
under `artifacts/desktop/`. It has no shipping authentication bypass. Credentials
and production records are never loaded. Visual acceptance includes login, dashboard,
audit list/details, light/dark, compact windows, empty/offline states and extra widget
scaling. Actual OS display-scale tests are distinguished from programmatic widget
scaling in the verification report; unavailable manual/assistive checks remain limitations.

Existing SQLite/MySQL CI jobs still run unchanged backend behavior plus desktop
headless contracts. Native tests are explicitly skipped without opt-in Windows.
A separate Windows job installs desktop dependencies and opts into native checks.
Consult [release readiness](RELEASE_READINESS.md#verification-evidence) for dated
local/hosted counts and run URLs rather than treating an old phase total as current.
See the [verification record and native screenshots](WINDOWS_DESKTOP_VERIFICATION.md)
for measured results, callback root cause and display-scaling limitations.
The [2026-10-27 independent acceptance](WINDOWS_DESKTOP_ACCEPTANCE.md) adds real-API
manual demonstration, maximized-window checks and subsequent engineering corrections.

## Distribution and deployment limits

Windows packaging/installation and Excel reporting are implemented. Android audit
management is a separate implemented client, supporting ADMIN and AUDITOR under
the existing backend rules; Windows admission stays ADMIN-only. Production code
signing, automatic update distribution and additional target-machine acceptance
remain outstanding. HTTPS/network policy, gateway limits, backups/restore, service
supervision and revision0002 rollout are operator prerequisites. Earlier phase
verification documents remain historical evidence; see the current release index
for known local-installer, clean-VM and display-scaling coverage limitations.
