# Phase 3A desktop implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. User authorized continuous implementation; no further plan approval required.

**Goal:** Deliver the approved read-only BHLI Audit Windows workspace.
**Architecture:** Inject a typed HTTP client into a Tk application. Keep session/query state and bounded background workers independent of widgets; only main-thread queue draining invokes UI callbacks.
**Tech Stack:** Python 3.14, CustomTkinter (verify 6.0.0), standard-library HTTP/TLS, pytest.
**Spec:** `docs/superpowers/specs/2026-10-26-phase3a-desktop-design.md`.

## Global constraints
- Work on `feat/dams-windows-desktop`; preserve baseline `09e8c585cd52aed826199ef1754f09d653cd1ecf`.
- No backend behavior, schema, production data/grant changes or Phase 3B mutations.
- Token memory only; REST only; verified TLS beyond loopback; no credential logging.
- Preserve seven audit business fields, server role and historical attribution.
- Multiple verified commits; normal push; one draft PR; never merge.

## Review focus
- Late login completion after window close must revoke the orphaned session (task 2).
- Stale 401 after a different session starts must not sign out the new account (task 2).
- Malformed server JSON/error text must not expose secrets or crash screens (task 1).
- DPI/window constraints and long names must leave actions reachable (tasks 3–4).
- Dashboard and details must never show invented totals or stale inaccessible records (tasks 3–4).

### Task 1: Typed client and configuration
**Files:** `desktop/{__init__,config,models,api}.py`, `tests/desktop/test_api.py`.
**Interfaces:** `Config(base_url,connect_timeout=5,read_timeout=15)`; `ApiClient(config,transport=None)` with `login`, `me`, `logout`, `list_audits`, `get_audit`, `sign_in`; immutable `User`, `Login`, `Audit`, `AuditPage`, `AuditQuery`; sanitized `ApiError(status,code,retry_after)`.
- [ ] Write tests for URL rejection, login+me, token/header safety, query validation, HTTP/JSON/error/Retry-After cases; run to observe missing-module failure.
- [ ] Implement transport and strict response parsing; run focused tests green.
- [ ] Commit verified client and plan.

### Task 2: Session and bounded background operations
**Files:** `desktop/{session,tasks}.py`, `tests/desktop/test_state.py`.
**Interfaces:** `SessionState` stores login/expiry/generation, role destinations; `Tasks.submit(key,work,done,dispose=None)` coalesces by key, `drain()` delivers only current results, `invalidate()` cancels pending/obsolete deliveries, `close()` exits without waiting on network.
- [ ] Tests: expiry/roles/cleanup, superseded successes/errors, queued capacity, thread identity, shutdown and abandoned login cleanup; observe red.
- [ ] Implement memory-only state and fixed daemon-worker pool; observe green and commit.

### Task 3: Design system, login and shell
**Files:** `requirements-desktop.txt`, `desktop/{__main__,app,theme}.py`, `desktop/components/`, `desktop/screens/{login,shell}.py`, `tests/desktop/test_gui.py`.
**Interfaces:** `Application(client)` composes state/tasks/screens; dependency-injected native test harness uses fake transport only in tests. Theme exposes semantic pairs; screen factories return widgets and accept an app controller.
- [ ] Add native opt-in smoke tests before UI implementation, observe red.
- [ ] Install separate pinned dependencies; verify CTk 6.0.0 + ttk rendering on native Python/Tk.
- [ ] Implement branded login, worker login/logout, safe errors/countdown, collapsible role navigation/account menu, theme changes, focus/keyboard/resize behavior.
- [ ] Run state/client/native login checks and commit.

### Task 4: Dashboard, audit list and details
**Files:** `desktop/screens/{dashboard,audits,details,account}.py`, shared table, tests and `docs/WINDOWS_DESKTOP.md`.
**Interfaces:** controllers consume only task 1 typed results and task 2 guarded delivery. Query/page/selected ID survive details navigation. Only login/logout POST and audit/me GET requests exist.
- [ ] Add tests for supported filters, page resets, full details, errors/empty states, role menus and stale request protection; observe red.
- [ ] Implement real dashboard, list/filter/page/sort/table/details, account and clear placeholders.
- [ ] Native checks in both themes, compact/full layouts, keyboard and programmatic scaling; capture fictional screenshots, distinguish actual OS DPI limits.
- [ ] Run focused desktop and affected backend tests; commit verified features and documentation.

### Task 5: Independent review and publication
**Files:** review corrections only; desktop verification evidence/documentation; CI desktop dependency step only if needed for collection.
- [ ] Fresh whole-branch engineering/security review against approved spec; fix confirmed defects test-first.
- [ ] Full applicable suite with credentials disabled, isolated MySQL regression if configured; no production access.
- [ ] Verify clean staged diff, dependency integrity, secrets and cumulative scope; publish checkpoint commits normally.
- [ ] Create/reuse one draft desktop PR; check hosted SQLite/MySQL jobs and report actual conclusions.

## Execution ledger
- Preflight: tasks 2–4 consume task 1 immutable models/client; tasks 3–4 consume task 2 guarded delivery. No interface conflicts.
- Ruling: use the existing user-selected feature branch rather than another worktree; it is clean and isolated from main.
- Ruling: use standard-library HTTP rather than adding a second HTTP package; keeps backend dependency pins stable and avoids conflicting `httpx2` aliases.
