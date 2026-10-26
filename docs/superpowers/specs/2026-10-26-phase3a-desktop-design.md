# Phase 3A — BHLI Audit Windows desktop design

**Status:** Approved by the user for implementation on 2026-10-26 (design checkpoint `2341f49`).
**Branch:** `feat/dams-windows-desktop` · **Baseline:** `09e8c585cd52aed826199ef1754f09d653cd1ecf`.

## Intent and scope

Give ADMIN and AUDITOR employees a professional, responsive Windows workspace for signing in and reading driver audits through the existing FastAPI service. Python 3.14 and CustomTkinter are required. Preserve backend behavior, schema, permissions and history.

Phase 3A delivers login, a collapsible application shell, role-aware dashboard, read-only audit list/details, and read-only My Account. Employee Accounts and Administrator Activity are explicitly labeled future-module placeholders for ADMIN. No audit mutations, account mutations, password screens, exports, reports, database connections or production operations.

## Approach and design ownership

| Approach | Trade-off | Decision |
| --- | --- | --- |
| Sidebar workspace | Persistent context and room for role-specific navigation; consumes horizontal space | **User approved**, with collapsible rail |
| Tabbed workspace | More horizontal content space; becomes crowded as modules arrive | Not selected |

The user selected navy navigation, teal accents, Segoe UI, light/dark themes, icons with labels, accessible keyboard navigation and a separate details screen. Dimensions, tokens and module interfaces below are proposed engineering choices, subject to this document's approval.

UI UX Pro Max informs spacing, visual hierarchy, contrast and focus behavior. Its generated web marketing sections, web fonts and mobile-specific recommendations do not apply here. Matt Pocock's Codebase Design principles inform a small injected client interface with real HTTP and fake-test adapters.

## Screen layouts and navigation

**Login:** A restrained BHLI Audit brand panel beside a centered sign-in card; stack above the form at compact widths. Persistent Username and Password labels, show/hide password, Sign In, inline feedback and connection status. No default credentials, remembered password or token persistence. Enter submits once; pending submission disables duplicate requests. Clear password text after submission; failures retain username. Loading remains cancellable by closing the window.

**Shell:** Navy sidebar left; header above the content with screen title, account name/role, appearance selector and account menu. Expanded sidebar is 232 logical pixels; collapsed rail is 64, with labeled tooltips and accessible control names. Selection uses a contrasting surface and indicator, not color alone. Collapse control is always reachable. Account menu contains My Account and Sign Out; Escape closes it and restores focus.

| Destination | ADMIN | AUDITOR | Content |
| --- | --- | --- | --- |
| Dashboard | Yes | Yes | Role-specific welcome and real audit data |
| Driver Audits | Yes | Yes | Read-only records workspace |
| Employee Accounts | Future module | Hidden | Explicit “Coming in a later phase” page; no account requests |
| Administrator Activity | Future module | Hidden | Explicit placeholder; no history requests |
| My Account | Yes | Yes | `/auth/me` identity and session expiry; no editing |

**Dashboard:** Welcome, role explanation and Open Driver Audits action. Display active-audit total from `GET /audits?page=1&page_size=5&sort=-id` and the same response's five most recently created records, labeled accordingly. Both roles can read all active audits; do not imply an AUDITOR's total is personal. ADMIN receives links to the future modules. Loading/error states never substitute zero or fictional statistics. No charts requiring unavailable aggregates.

**Driver Audits:** Title and Refresh; search field plus Driver / Plate / Station selector; expandable filters for station, inclusive date range and “My audits” (authenticated user ID). Avoid two competing station inputs: selected Station search and station filter share one value. Apply/Clear are explicit; applying or sorting resets page 1. Validate real `YYYY-MM-DD` dates and ordered ranges locally; server remains authoritative. Sort choices map exactly to `-id`, `id`, `-audit_date`, `audit_date`. Page sizes 25/50/100; previous/next, range and total below the table. No automatic polling.

Table columns: Audit Date, Driver Name, Helper Name, Station, Plate Number, Audited By. Remarks remain fully available in details. ID is technical row identity, not another business field. Support row selection, vertical/horizontal scrolling, double-click or Enter to open and an explicit View Details button. Arrows/Home/End navigate rows. Preserve filter/sort/page and selected ID on return; refresh may change offset-page contents. Phase 3A excludes deleted records for both roles and sends no `include_deleted=true`.

**Audit Details:** Separate content screen with Back to audits, driver/plate heading, all seven fields in labeled sections, wrapped selectable remarks and optional technical metadata (record ID, version, UTC timestamps displayed with timezone labels). Optional helper/remarks show “Not provided.” Audited By shows the original server snapshot unchanged. Refresh reads the record again; 404 presents an unavailable state without leaving stale details visible. No edit/delete/history controls in this phase.

## Design tokens and reusable controls

| Semantic token | Light | Dark |
| --- | --- | --- |
| Window background | `#F1F5F9` | `#0B1220` |
| Surface / raised surface | `#FFFFFF` / `#F8FAFC` | `#111C2E` / `#17253B` |
| Main / secondary text | `#0F172A` / `#475569` | `#F1F5F9` / `#B8C5D6` |
| Navigation / navigation text | `#0F172A` / `#F1F5F9` | `#080F1D` / `#F1F5F9` |
| Primary action / action text | `#0F766E` / `#FFFFFF` | `#2DD4BF` / `#0B1220` |
| Focus indicator | `#0F766E` | `#5EEAD4` |
| Error text | `#B91C1C` | `#FCA5A5` |

Use Segoe UI at 14 logical-pixel-equivalent body size, 12 supporting text, 20 section titles and 28 screen titles; verify actual Tk font units rather than equating points and pixels. Spacing follows 4/8/12/16/24/32; cards radius 12, inputs/buttons 8. Controls target 40 logical pixels high. Use a coherent set of locally drawn monochrome navigation icons, never emoji or runtime asset downloads.

Reusable controls: primary/secondary/quiet buttons; labeled inputs; search/filter bar; safe notification banner; loading panel; empty/error panel with Retry; paginated table; detail field; role badge; sidebar item. Every control defines hover, pressed, disabled and visible keyboard-focus states in both themes. Text contrast target is at least 4.5:1; meaningful controls/focus at least 3:1 against adjacent surfaces. Measure final state combinations, not just these base tokens. Keep error/status text visible; never communicate state by color alone.

Initial window target 1280×800 logical pixels, minimum 800×600 within the actual screen work area. At compact widths collapse the sidebar, stack filter/dashboard/detail sections and allow table horizontal scrolling. Long names wrap or ellipsize with full accessible text/details. Large fonts and 100/125/150% display scaling must leave actions reachable; if screen work area is smaller than the preferred minimum, fit it and provide scrolling. No hover-only actions or mandatory animation.

Tab/Shift+Tab follow visual order; Enter submits login or opens the selected row; Escape dismisses menus/returns from details; Ctrl+F focuses audit search; F5 refreshes the active data screen. Navigation puts focus on the screen heading or first meaningful control; Back restores prior row focus. Screen-reader support depends on Tk/CustomTkinter and must be assessed honestly on Windows, not claimed from web accessibility guidance.

## Package structure and interfaces

```text
desktop/
  __main__.py, app.py        composition, lifecycle, navigation
  config.py                 desktop-only URL/timeouts; never loads server .env
  api.py, models.py         HTTP adapter, validated responses, safe error types
  session.py                in-memory identity/token/expiry and session generation
  tasks.py                  bounded workers, completion queue, cancellation
  theme.py                  semantic tokens and typography
  components/               shared visual controls and table adapter
  screens/                  login, dashboard, audits, details, account/placeholders
tests/desktop/              fake transport, state/task tests, native smoke checks
requirements-desktop.txt    separately pinned desktop dependency set
```

Expose an injected client interface: `login(username, password)`, `me(token)`, `logout(token)`, `list_audits(token, query)` and `get_audit(token, id)`. Return typed data, a detail result retaining ETag, or sanitized structured errors; keep HTTP details out of screens. Immutable audit query state owns supported parameter validation. Controllers/session state remain testable without Tk or MySQL. Screens receive dependencies instead of constructing transports.

Investigate CustomTkinter 6.0.0 on the actual Python 3.14.3/Tk 8.6 installation before pinning; import success alone is insufficient. Exercise table rendering, focus and DPI in both themes. Prefer a themed `ttk.Treeview` adapter for keyboard behavior, contingent on rendering compatibility; if incompatible, use a CustomTkinter-backed table behind the same interface and repeat keyboard/visual checks. Keep existing backend dependency pins unchanged.

## API integration, session safety and background work

Default `http://127.0.0.1:8000`; override with `DAMS_DESKTOP_API_URL` or `--api-url`. Parse and reject URL userinfo, query/fragment and unsupported schemes; allow HTTP only for literal loopback/localhost, require verified HTTPS elsewhere. Do not follow cross-origin redirects or use server `.env`. Connection/read timeouts proposed at 5/15 seconds. Never display/log full configured URLs, request bodies, passwords, Authorization headers or raw exceptions.

Login is `POST /auth/login`, followed by `GET /auth/me` using the returned token. Publish authenticated state only after both validate; reject unknown roles or malformed payloads. If identity retrieval fails, discard and best-effort revoke the provisional token. Store token only in memory with server expiry; never include it in object representations. Passwords exist transiently in widget/request memory, are not retained for retries, and cannot be guaranteed securely zeroed by Python. All navigation uses the validated server role; server permissions remain authoritative.

On logout, invalidate local session and pending results immediately, then send `POST /auth/logout` using the captured token. If remote revocation fails, state that local logout completed but server session may remain until expiry; never restore the token. Window close performs bounded best-effort revocation and exits without waiting on a long request. Clear identity and displayed audit data on logout/expiry/401. Sessions have no refresh; login is required again.

All network work runs in a bounded executor (proposed four workers). Workers produce results into a queue; only the main thread polls with Tk `after` and updates widgets. Work captures session generation and screen/request identity. Navigation, logout, new login or superseding searches invalidate obsolete completions, including stale 401 responses. Cancellation cannot undo an HTTP request already sent; finite timeouts bound it. Prevent duplicate submissions and avoid an unbounded queued backlog; worker threads never invoke Tk, including `after`. Closing cancels pending tasks, suppresses completions and destroys widgets safely.

Parse only expected JSON shapes; tolerate 204 without JSON. Use allowlisted local messages with server error codes; never render arbitrary server text/HTML. 401 requires login, 403 explains denial, 404 shows unavailable, 409/412 preserve safe conflict codes/status for future editing, 422 shows safe input feedback, 429 honors numeric or HTTP-date Retry-After with a nonblocking countdown, and network/500/503 errors offer explicit Retry. Do not automatically retry credential submissions. Retain ETag from detail reads for later phases without exposing mutation controls now.

## Verification, checkpoints and delivery

After design approval, write the detailed TDD implementation plan. Proposed coherent checkpoints:

1. Desktop configuration, typed client, session/task modules and isolated transport/concurrency tests.
2. Design tokens/reusable controls, native dependency compatibility and login/shell/navigation.
3. Real dashboard, read-only audit filtering/pagination/details and associated tests.
4. Security/concurrency corrections, native visual refinement, launch/setup documentation and independent review.

Commit only verified milestones; push to the existing desktop branch and create one draft Phase 3 PR targeting main after final verification. Preserve history; no merge. Document any changed checkpoint grouping rather than inventing commits.

Automated acceptance covers real request paths/parameters, timeouts, malformed JSON, safe errors/redaction, 204, 401/403/409/412/429, authentication failure/success, unknown roles, logout/expiry cleanup, both role menus, filters/page boundaries, superseded responses, shutdown and cross-session result isolation. Use fake HTTP transports and isolated API integration where valuable; no shipping mock-login bypass. Run affected backend regressions and full applicable regression before publication, reporting real skips separately.

Native Windows acceptance covers rendered login and all screens, both themes, narrow/large windows, keyboard-only operation, slow/offline/retry/empty states and 100/125/150% scaling. Capture local screenshots using fictional data only. Programmatic widget scaling does not prove real Windows DPI behavior: distinguish it from actual display-scale tests. Report unavailable native checks explicitly. Independent final review checks scope, authorization, error handling, worker lifecycle and visual consistency; verify hosted checks on published HEAD.

Document setup, backend startup using existing operator configuration, `python -m desktop`, URL configuration, dependency pins, architecture, design tokens, tests and known limitations. Production revision 0002 and runtime grants remain a separately approved rollout; this assignment does not migrate, grant or modify production data.

Remaining phases: Phase 3B audit mutations require ETag/If-Match and idempotency design; subsequent employee/activity/password interfaces, packaging/distribution and other Phase 3C–3E work need separate assignments. These are future candidates, not authorization or an assumed final phase allocation. No open product decision blocks approval of this Phase 3A design.
