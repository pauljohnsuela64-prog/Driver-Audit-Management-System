# Phase 3B Audit Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver safe desktop audit creation, editing, soft deletion and history.
**Architecture:** Keep HTTP/typed contracts in the existing client; isolate draft and mutation decisions in a UI-independent operation module. Compose full-page forms/history into the existing sidebar and use a separate bounded mutation queue so read supersession cannot lose operation outcomes.
**Tech Stack:** Python 3.14, CustomTkinter 6, existing FastAPI REST API, pytest, native Windows Tk.
**Spec:** `docs/superpowers/specs/2026-10-27-phase3b-audit-management-design.md` (approved at `b888cbf`).

## Global Constraints

- Exactly seven business fields; six editable, server-owned immutable Audited By.
- Memory-only sessions/drafts, no private-data logging, all HTTP off the UI thread.
- Exact ETags and one UUID per frozen creation intent; never silently replay destructive operations.
- No production MySQL, migrations, grants, backend business-rule changes, or Phase 3C.
- Preserve prior history; commit on `feat/dams-audit-management`, publish one draft PR, never merge.

## Review Focus

- Theme rebuild while a draft/request exists: retain intent, never resubmit (Task 2).
- Late completion after logout/new login: no cross-account UI delivery (Task 2).
- A lost committed creation response: same key/body resolves to one CREATE (Task 2).
- Repeated conflict during explicit reapply: newest exact ETag still required (Task 3).
- Large escaped Unicode in two history snapshots: valid page fits finite transport ceiling (Task 4).

## Task 1: Typed contracts and operation decisions

Files: modify `desktop/api.py`, `desktop/models.py`; create `desktop/audit_operations.py`, `tests/desktop/test_audit_operations.py`, `tests/desktop/test_audit_api.py`.
Interfaces: `normalize(values) -> dict`, `CreationIntent(user_id, payload)` with immutable key/body; `changed_fields(record, values) -> dict`; client `create_audit(token,payload,key) -> Audit`, `update_audit(token,id,payload,etag) -> Audit`, `delete_audit(token,id,etag) -> None`, `audit_history(token,id,page=1,include_deleted=False) -> EventPage`; extend GET/query parsing with explicit deleted access.

- [x] Write tests for normalization/bounds/clearable optionals, immutable intent, exact headers, malformed ETags/events/deleted access.
- [x] Run new tests; expect missing-interface failures before implementation.
- [x] Implement contracts and pure operation decisions, retaining finite response limits.
- [x] Run `python -m pytest tests/desktop/test_audit_operations.py tests/desktop/test_audit_api.py tests/desktop/test_api.py -q`; expect all pass; commit.

## Task 2: Create form and operation lifecycle

Files: create `desktop/screens/audit_form.py`, `desktop/components/audit_dialogs.py`, `tests/desktop/test_audit_gui.py`; modify `desktop/app.py`, `desktop/screens/audits.py`, existing integration tests.
Interfaces: `AuditForm(parent,app,draft)`; application-owned draft and separate mutation queue; `app.mutate(work,done)` delivers only to originating session, not a destroyed view; `app.open_create()`; draft capture on theme rebuild.

- [x] Add failing state/native tests for create/validation/double Save/ambiguous retry, theme preservation, logout and queue lifecycle; run targeted cases to observe failures.
- [x] Implement reusable form, confirmation focus, app-owned lifecycle and frozen intent. Disable ordinary navigation during submission; logout/close remain explicit and bounded.
- [x] Add a real API integration test that drops the committed create response and retries the frozen intent; assert one record/event and original attribution.
- [x] Run desktop focused tests in default and isolated MySQL modes; expect pass; commit.

## Task 3: Edit and conflict resolution

Files: extend form/operation module/app/details, `tests/desktop/test_audit_gui.py`, `tests/desktop/test_integration.py`.
Interfaces: `app.open_edit(record)` fetches current detail/ETag; edit draft stores baseline/local/latest; comparison screen exposes Reload and Review/reapply actions; no-op Save sends no PATCH.

- [x] Add failing ownership, changed-fields-only, stale conflict, repeated-conflict, ambiguous PATCH and historical attribution tests.
- [x] Implement explicit baseline/local/latest comparison and reviewed reapply with exact newest ETag; retain unsaved values on errors.
- [x] Run affected desktop/API/native/integration tests in both modes; expect pass; commit.

## Task 4: Soft delete and history

Files: create `desktop/screens/audit_history.py`; extend dialogs/app/details/list/models; tests in audit API/native/integration modules.
Interfaces: ADMIN deleted-list toggle; `app.confirm_delete(record)` fetches fresh detail before confirmation; `app.open_history(id)`; 25-event chronological pages with scrollable snapshots.

- [x] Add failing tests for ADMIN-only deletion, stale reconfirmation, ambiguous deletion reconciliation, deleted visibility/history and maximum Unicode history page size.
- [x] Implement explicit confirmation, no automatic destructive retries, deleted banners/read-only details, stable owner/actor separation and paginated history.
- [x] Run affected tests in default and isolated MySQL modes; expect pass; commit.

## Task 5: Acceptance, review and publication

Files: extend `scripts/desktop_demo.py` only if needed for fictional workflows; update desktop/demo docs and screenshots; new native acceptance capture as needed.

- [x] Verify both-role workflows and all error/conflict states in real disposable API/native Windows sessions, both themes and compact/maximized layouts. Document actual versus simulated DPI.
- [x] Run complete desktop/native/default and isolated MySQL suites, recording pass/fail/skip counts; no production access.
- [x] Perform fresh independent whole-branch engineering/UI review, fix confirmed defects test-first, and commit verified changes.
- [ ] Inspect cumulative diff and staged secret/config exposure, push normally, create one draft PR and inspect hosted Windows/SQLite/MySQL CI; fix genuine failures without weakening tests.
- [ ] Report commits, verification/screenshots, demo instructions, limits and draft PR URL. Keep unmerged.

## Verified execution record

- `c22f075`: typed contracts and immutable creation intents; 78 contract/client tests passed.
- `435ad50`: shared Create/Edit form and mutation lifecycle; 23 native/API tests passed, four real-API tests also passed in isolated MySQL.
- `b50a5c2`: deletion/history and shared native fixture; 22 native tests passed.
- `7a19f81`: extended real demo, capture harness and responsive form correction; six focused layout/demo tests passed.
- `8331afd`: independent-review recovery, keyboard and snapshot corrections; 15 native tests passed.
- `40c3210`: reproduced worker-thread cyclic collection corrected; 36 mixed native/demo tests and pending-login close passed.
- Final default/native: 446 passed, four explicit live-MySQL skips. Final isolated MySQL/native: 450 passed, no skips.
- Final real-API visual capture: 13 screenshots, zero Python/Tcl callback errors, actual DPI 144, simulated widget factors 1.0/1.25/1.5.
- Publication and hosted-check outcomes are recorded in the draft PR and final report to avoid a documentation-only CI feedback loop.
