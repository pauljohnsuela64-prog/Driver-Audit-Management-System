# BHLI Audit desktop — Phase 3A

Windows desktop foundation: employee sign-in, role-aware collapsible navigation,
dashboard with real active-audit totals, searchable/filterable/paginated audit table,
separate read-only details, My Account, appearance selection and sign-out.
Employee Accounts and Administrator Activity are clearly labeled future modules.
The desktop preserves the seven audit business fields and original auditor snapshot.

## Setup and launch

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

An operator must separately prepare the backend and its restricted runtime account:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

See [database setup](DATABASE_SETUP.md) and [authentication](AUTHENTICATION.md).
This desktop assignment does not approve production revision 0002 or its grants.
Do not start an unprepared production rollout merely to test the GUI. Native checks
use a fictional transport; real API integration tests use isolated test fixtures.

Default API origin is `http://127.0.0.1:8000`. Override without database credentials:

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

ADMIN sees Dashboard, Driver Audits, two future administration modules and My Account.
AUDITOR sees Dashboard, Driver Audits and My Account. Both roles can read all active
audits; “My audits” filters by the authenticated stable account ID, not display name.
The dashboard total is for all active visible records, never a fabricated personal metric.

Search by driver, plate or station; expand Filters for station/date range/My audits.
Apply resets the page; clear removes filters. Dates use `YYYY-MM-DD`. Sort by
creation ID or audit date ascending/descending. Page sizes are 25/50/100. Refresh
reloads the current query. Concurrent server writes can shift offset pages.
Enter/double-click or View Details opens the selected audit. Back retains query/page
and selected ID. Details display Driver Name, optional Helper Name, Audit Date,
Station, Plate Number, optional Remarks and original Audited By. No create/edit/delete
or deleted-record visibility is exposed in Phase 3A.

Tab/Shift+Tab traverse controls; Enter signs in or opens a selected row; Space
activates buttons/checkboxes; dropdowns can be opened with Enter/Space and navigated
with arrow keys. Home/End select table edges. Ctrl+F focuses search, F5 refreshes,
Escape dismisses the account menu or returns from details. Screen-reader support
must be assessed with Windows assistive technology; native Tk accessibility is not
equivalent to browser ARIA support.

## Architecture and security

`desktop/api.py` owns HTTP, bounded response size, 5-second connection and 15-second
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
callbacks. Independent bounded revocation work cannot be canceled by navigation or
starved by a full screen queue. Closing suppresses late UI callbacks and performs
best-effort revocation without waiting indefinitely.

Logout clears local identity, token and audit views immediately and requests server
revocation. Unconfirmed revocation is reported: a server session may remain until
expiry after a network failure/process exit. Abandoned successful logins are best-
effort revoked. Sessions have no refresh; expiry or a current-request 401 requires
new login. Server authorization remains authoritative despite role-based navigation.

403 is permission denial; 404 removes unavailable details; known conflict codes for
409/412 are retained for future editing; 422 gives safe validation feedback. 429
uses a nonblocking Retry-After cooldown (numeric or HTTP-date), including read-screen
retries. Network/500/503 errors offer manual retry without raw exceptions, SQL,
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
Consult the draft PR for exact latest local/hosted counts and run URLs.
See the [verification record and native screenshots](WINDOWS_DESKTOP_VERIFICATION.md)
for measured results, callback root cause and display-scaling limitations.

## Remaining work

Phase 3B may add audit mutations with ETag/If-Match and idempotency handling, subject
to its own assignment. Employee/activity/password interfaces, packaging/installers,
code signing, update distribution and client acceptance are future work. Production
HTTPS/network policy, gateway rate limits, backups, service supervision and revision
0002 rollout remain operator prerequisites. No GUI mutation, reporting or Android
implementation is included here.
