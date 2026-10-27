# Phase 3A independent desktop acceptance — 2026-10-27

Reviewed original HEAD `219566d72554f16afc1168b3df9b8667ddefc1c6` against main
`09e8c585cd52aed826199ef1754f09d653cd1ecf`. All ten original commits are preserved.
PR #5 remains draft; this review does not authorize a merge or production rollout.

## Engineering findings and corrections

| Severity / review axis | Finding | Correction |
| --- | --- | --- |
| Medium / Standards | Untrusted Retry-After could overflow native deadline arithmetic and stop polling/session-expiry cleanup | `8b83b8f`: finite one-day delay ceiling, leading-zero handling, and `finally` rescheduling while still reporting callback failures |
| Medium / Spec | Back restored selection but not keyboard row focus; Enter/double-click could leave native class bindings referencing a destroyed Treeview | `8b83b8f`: restore widget focus, focus initial search, and stop remaining bindings after navigation |
| Medium / contract boundary | A valid 100-record page with long Unicode remarks exceeded the 2 MB body ceiling | `8e76d48`: bounded 16 MiB ceiling covering legal JSON pages, with separate oversized-body rejection/connection-close regression |
| Medium / lifecycle | Retained closed-screen font cycles could be collected on an API worker, blocking its Tcl font destructor after the GUI closed | `0a816d6`: clear closed view references and collect Tk cycles on the UI thread; weak-reference native close regression proves font release |
| Low / maintainability judgment | Client/callback interfaces have limited static typing; toolkit adapters use private pinned APIs | Nonblocking: existing seams, immutable models, version pinning and regressions contain the risk; no speculative refactor |

No critical/high finding remains. New developer-demo checks also reject insecure
password-input fallback and environment-proxy routing before publication.

Previously corrected logout delivery, stale-response cleanup, station-filter state,
retry cooldown, native DPI sizing, Tk `state()` availability and timer ownership
remain covered. Native close during an in-flight login verifies prompt return,
local cleanup, late-session revocation and zero callback errors.

## Native UI/UX and real-API evidence

The actual Windows application ran against a real FastAPI HTTP server with normal
authentication and disposable SQLite, using 60 fictional audits and 40 AUDITOR-owned
records. No shipping authentication bypass or MySQL connection is involved.

Actual Windows DPI: **144 (150%)**. Reviewed login, both role dashboards, expanded/
collapsed navigation, paginated/sorted audit table, filters, long details and original
attribution, Light/Dark, compact/maximized layouts, loading, incorrect-login, offline
and empty states. Keyboard Enter/Escape and restored row focus were exercised.
Capture completed with **19 screenshots and zero Python/Tcl callback errors**.

Text/action/error contrast was measured in both themes: tested combinations range
from **5.47:1 to 17.85:1**, exceeding the 4.5:1 text target. This does not certify
screen-reader or comprehensive assistive-technology support.

| Native evidence | Screenshot |
| --- | --- |
| Actual authenticated audit list | [Expanded list](images/desktop-acceptance/audits-expanded.png) |
| Real second page | [Pagination](images/desktop-acceptance/second-page.png) |
| Compact filters | [Compact](images/desktop-acceptance/compact-filters.png) |
| Maximized workspace | [Maximized](images/desktop-acceptance/maximized.png) |
| Immutable original attribution | [Details](images/desktop-acceptance/original-attribution.png) |
| AUDITOR's 40 owned records | [My audits](images/desktop-acceptance/auditor-own-records.png) |

Widget factors 100/125/150% are additional stress checks on the existing 150% display,
not actual Windows display-setting changes. Actual 100%/125%, mixed-monitor DPI,
and formal screen-reader acceptance remain unverified. Scrollbars and compact/
maximized control reachability were checked on the current Windows display.

## Regression, publication and boundaries

Fresh source-stable local verification after all corrections:

| Check | Actual result |
| --- | --- |
| Complete desktop suite, default | **79 passed** |
| Complete desktop suite, isolated MySQL mode | **79 passed**, including the previously stalled GUI-close/API transition |
| Complete default backend/desktop suite, native GUI enabled | **399 passed, 4 explicit live-MySQL skips**, 106.27 s |
| Complete isolated MySQL backend/desktop suite, native GUI enabled | **403 passed, zero skips**, 229.31 s |
| Syntax, dependency and text contrast checks | Passed |

No teardown exceptions or stalls occurred in these final runs. The earlier stalled
run was diagnosed with stack inspection, stopped, and its dedicated test fixture
schema was safely cleaned before rerunning. No production database was connected.
Demo-only fixtures deliberately use disposable SQLite in both test modes; actual
MySQL backend verification uses the guarded isolated database/runtime account.

Fresh desktop/default/isolated-MySQL results and final hosted Windows/SQLite/MySQL
run URLs are recorded on [draft PR #5](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/pull/5)
and in the final engineering report. Saved local full-suite logs are under ignored
`artifacts/desktop-acceptance/`; no skipped platform tests are represented as passed.

The real demonstration and its safety tests are documented in
[WINDOWS_DESKTOP_DEMO.md](WINDOWS_DESKTOP_DEMO.md). Run it from a local console;
choose passwords only at its hidden prompts. It removes its own temporary resources.

No backend implementation, schema/grants, production records, audit ownership or
seven business fields changed. Production revision 0002 deployment/permissions,
HTTPS/trusted networking and operator controls remain separate approvals. Account
and audit mutation UI, packaging/distribution, Android and reports remain out of scope.
