# Phase 3A verification record

2026-10-26 · approved baseline `09e8c585cd52aed826199ef1754f09d653cd1ecf`.

## Engineering evidence

| Check | Observed result |
| --- | --- |
| Complete default regression after lifecycle correction `6806116` | **384 passed, 4 explicit live-MySQL skips**, 141.26 s; native Windows tests enabled |
| Complete isolated MySQL regression after lifecycle correction `6806116` | **388 passed, zero skips**, 264.04 s; native Windows tests enabled; no teardown errors |
| Final desktop regression including additional focus/visual polish | **65 passed**, including native Windows checks and real isolated FastAPI contracts |
| Dependency/syntax/workflow checks | `pip check`, `compileall` and YAML structural validation passed |
| Independent source review | All confirmed findings corrected; final lifecycle review found no concrete blocker |
| Publication CI | Consult the draft PR for exact final-HEAD SQLite, disposable MySQL and Windows job results; no hosted success is inferred from local tests |

Full regression outputs are retained locally under ignored `artifacts/desktop/`.
The final extra focus test and cosmetic loading-caption/menu treatment were verified
with the complete desktop suite; backend behavior did not change. Hosted jobs verify
the published HEAD separately, with native-only skips explicitly reported by Linux jobs.

## Callback root cause and corrections

Native Tk widget destruction leaves widget-owned `after` scripts pending. Their
Python/Tcl commands are deleted; an outstanding timer can refer to a deleted name
or a name subsequently reused for a different binding. This produced intermittent
teardown errors and could invoke an unrelated action on a replacement screen.

`destroy_view` now collects commands owned by the departing widget subtree and
cancels those timers through their original owning widgets before destruction.
Using the owner keeps Tk's command-registration bookkeeping consistent. It handles
CustomTkinter scrollable wrappers and preserves timers owned outside that subtree.
Root close intentionally cancels the entire application subtree, including polling.
Tooltip bindings target stable frames; theme changes preserve focus on the persistent
root before rebuilding screens. No exception suppression was used to pass verification:
native tests and visual capture collect both Python callback and Tcl background errors.
The deterministic regression proves the obsolete timer is removed and never fires.

Other verified corrections preserve remote logout when screen work is saturated,
Retry-After cooldown, superseded callback/request cleanup, station filters across
search modes, request-capture release, full-queue query supersession, DPI-aware
sizing, and Tk's native `state()` method. Tests reproduce each relevant failure
before the correction. The desktop never imports backend/ORM/database configuration.

## Native visual evidence

Python 3.14.3 · Tcl/Tk 8.6 · CustomTkinter 6.0.0 · actual Windows display DPI **144
(150%)**. All screenshots render the actual application with fictional API data,
not a browser mockup. Windows titlebar accents follow the host configuration.

Reviewed login, ADMIN/AUDITOR dashboards, expanded/collapsed navigation, audit
table, filters/pagination controls, details including original auditor attribution,
loading/empty/offline/incorrect-login states, light/dark, and compact/resized layouts.
The final harness captured **15 PNGs with zero Python/Tcl callback errors**. Selected
images below are committed for review; the full set and `verification.json` remain
under ignored `artifacts/desktop/`.

| Screen | Evidence |
| --- | --- |
| Login, light | [Screenshot](images/desktop/login-light.png) |
| ADMIN dashboard | [Screenshot](images/desktop/admin-dashboard-light.png) |
| AUDITOR dashboard, dark | [Screenshot](images/desktop/auditor-dashboard-dark.png) |
| Audit workspace, dark | [Screenshot](images/desktop/audits-dark.png) |
| Compact filters with collapsed navigation | [Screenshot](images/desktop/compact-filters-light.png) |
| Details and original attribution | [Screenshot](images/desktop/details-attribution-dark.png) |

Extra **widget-scaling factors** 100%, 125% and 150% were exercised on the existing
150% Windows display; they are multiplicative stress checks, not changes to OS DPI.
Actual Windows 100%/125% display settings, mixed-monitor DPI transitions and formal
screen-reader acceptance were not verified. Keyboard/focus interaction is tested;
this does not certify comprehensive assistive-technology support.

## Boundaries

No backend implementation, database schema/grants, seven audit business fields or
production records changed. Production MySQL was not accessed for this assignment.
Production revision 0002 rollout, HTTPS/trusted networking, operator credentials
and deployment controls remain separately approved operational work.

Phase 3A is read-only except login/logout. Employee/activity placeholders are
explicit; Phase 3B mutation UI, installers/code signing, Android and reports remain
out of scope. Remote revocation after network failure or process exit is best effort
and clearly reported; tokens are not persisted. Follow [launch instructions](WINDOWS_DESKTOP.md).
