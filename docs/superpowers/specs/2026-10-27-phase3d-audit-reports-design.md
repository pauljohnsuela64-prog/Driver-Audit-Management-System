# Phase 3D: Simple Audit Reports and Export

Status: proposed; requires user approval before implementation.

## Verified starting point

- Phase 3C PR #7 merged into main at `93f6bcbed390c383c9e6883cee7bab42b248c69f`.
- Post-merge push run [40487335862](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40487335862): Windows, SQLite and disposable MySQL jobs all succeeded.
- Local main fast-forwarded to the same SHA with a clean working tree. Design branch: `feat/dams-audit-reports`. Existing branches and commits preserved.

## Scope and alternatives

Recommended: Excel export now, individual PDF later. This delivers the main daily HR workflow with one small desktop dependency. CSV is smaller but lacks reliable Excel text-cell typing and presentation. Excel plus PDF adds a separate pagination, Unicode font embedding, printing and long-remarks acceptance surface. A useful PDF is feasible, but disproportionate to this first lightweight reporting increment.

This is a proposal, not an already approved scope decision. Approval should explicitly confirm Excel-only or request inclusion of PDF. No product code, dependencies or database changes are part of this design checkpoint.

## Layout and workflow

Keep Dashboard, Driver Audits and My Account as the only sidebar destinations. Preserve navy/teal styling, Segoe UI, both themes, collapsible sidebar and 38-logical-pixel table rows.

Driver Audits action row: **New Audit** (primary), **Export to Excel** (secondary). Wrap actions into a second row at compact widths rather than shrinking the search box or table columns.

1. Export captures the last successfully applied immutable `AuditQuery`, excluding its current page and page size. Never export an earlier query silently when visible filter controls contain unapplied edits: require Search/Apply first, with an inline message.
2. A small dialog summarizes search, station, inclusive date range, auditor scope, sort and archived inclusion; states **all matching records**, not the visible page. Existing auditor selection is All / My audits, backed by `audited_by_user_id`; preserve any selected ID without adding an employee directory or role selector.
3. User chooses an `.xlsx` destination through the native Save As dialog, with a date-based filename containing no business data. Cancel has no side effects. Existing-file overwrite requires explicit confirmation.
4. Show fetched-record count, current stage and Cancel. Do not promise a fixed completion percentage when the server total changes. One export at a time; no automatic retry or resume. Keep ordinary read-only navigation responsive, with job status reachable from Driver Audits. Theme/view rebuilds retain safe job state, never Tk widget references in workers.
5. Success appears only after workbook close and final file publication succeed, showing actual row count and destination. Offer Open folder; do not automatically launch Excel. Zero results shows an empty state and leaves no report.

Keyboard: ordinary Tab order, visible focus, Enter activates the focused action, Escape cancels the report dialog/job. Restore focus to Export after dismissal. Progress updates use the UI queue and avoid disruptive focus changes.

## Workbook contract

Format: macro-free `.xlsx`, one `Audits` sheet plus a short `Report information` sheet.

Ordered business columns: Driver Name, Helper Name, Audit Date, Station, Plate Number, Remarks, Audited By. Append technical columns Record ID and Status (`Active` / `Archived`); these are report metadata, not new business fields. Historical `audited_by_name` is used directly; never substitute the user's current name. Optional values become blank cells. Audit dates use unambiguous ISO `YYYY-MM-DD`; identifiers, including record ID and plate number, are explicit text cells. All user-controlled text uses string writing, never formula or hyperlink inference. Preserve Unicode, leading zeros, newlines and the full supported 10,000-character remarks without silent truncation.

Freeze headings, enable an ordinary worksheet autofilter, set bounded column widths and wrap remarks. Avoid merged cells, charts, macros and external links. Long remarks remain fully available in the cell even when on-screen row height is capped for readability. Spreadsheet appearance is light and printable independently of desktop theme.

Report information records generation start/end in UTC, actual rows exported, filter/sort summary, archived inclusion and the pagination caveat. Exclude tokens, passwords, connection strings and unrelated account information. Explain that exported business data is an unencrypted local document, outside session revocation; choose an appropriate protected destination.

## Architecture and dependency

Reuse `ApiClient.list_audits(token, query)` and its strict models, authentication, bounded responses and sanitized errors. Fetch from page 1 with page size 100, preserving every other query property. No direct MySQL access, new backend endpoint or schema changes.

A focused report module owns iteration, validation, workbook generation and file publication behind a small interface accepting the existing client, token, immutable query, destination, cancellation event and progress sink. The desktop adapter owns dialogs and job lifecycle. Inject existing dependencies rather than creating another transport abstraction or reporting framework. Tokens remain memory-only and never enter job representations or progress messages.

Proposed desktop-only dependency: `XlsxWriter==3.3.0`, verified as an available release during design; recheck Python 3.14 compatibility, package integrity and advisory status before installation. Use constant-memory sequential row writing, `write_string` for untrusted text, and disable string-to-formula, URL and numeric inference. No pandas, Office automation or extra runtime reader library. Tests inspect XLSX ZIP/XML with the standard library; native Excel acceptance remains separate from structural checks.

Sources: [package](https://pypi.org/project/xlsxwriter/), [streaming trade-offs](https://xlsxwriter.readthedocs.io/working_with_memory.html), [workbook options](https://xlsxwriter.readthedocs.io/workbook.html).

## Limits, consistency and safe failure

Proposed explicit limits: 20,000 records, 200 pages, 100 MiB cumulative UTF-8 field payload, 256 MiB temporary working directory and 10 minutes elapsed. Exceeding any limit fails the entire export with guidance to narrow filters. Check bounds during iteration/writing and before publication; never label a truncated file complete. Preserve existing HTTP response and timeout bounds. Cancellation takes effect between requests/rows; a blocking HTTP operation can finish only at its configured timeout. Workbook finalization also runs off the UI thread; cancellation is checked again before publication.

Validate returned page number/size, stable total, duplicate IDs, expected sort order including ID tie-breaks, and the final unique-row count. Detectable inconsistencies abort with a refresh/retry message. The existing API offers no snapshot token: edits can change membership or values without changing totals, so these checks cannot guarantee a point-in-time report. Disclose this on confirmation and in workbook metadata; recommend exporting while other administrators are not editing. Do not invent snapshot guarantees or silently change the chosen sort.

Use a unique, exclusively created temporary work directory beside the destination so workbook intermediates stay on the selected volume. Final destination stays untouched until complete validation and workbook close. Use an atomic same-volume publication operation, preserving an existing file on cancellation/error. Detect destination changes since overwrite confirmation and require renewed confirmation rather than replacing an unexpected file. Clean up temporary data on normal cancellation/failure; cleanup failure is reported without claiming it was removed. Abrupt process termination can leave temporary files; document this limitation and never silently delete unrelated directories. Protect reserved/invalid Windows paths, extension handling and collisions; sanitize user-visible errors without leaking response bodies or secrets.

401 clears the session and cancels the job. 403, offline/server failures or malformed responses abort without a report. Logout, local session expiry and close cancel export; prevent stale worker callbacks from touching destroyed widgets. Serialize cancellation and the final publication decision: cancellation before that decision prevents publication; a completed publication is reported as complete. Revocation cannot retract an already saved file. There is no automatic export retry after re-login.

## Proposed implementation checkpoints after approval

1. **Export contract and writer (TDD):** exact columns, all seven fields, text typing/injection payloads, Unicode, optional values, long remarks, archived status, metadata and structural XLSX compatibility. Add the justified pinned desktop dependency only here.
2. **Authenticated multi-page job (TDD):** query preservation, deterministic sort, all pages, duplicate/drift detection, resource ceilings, session/error behavior, cancellation and atomic destination handling, including permission errors, locked files and destination races. Commit coherent verified work.
3. **Desktop integration:** secondary Export action, confirmation/save/progress/success states, unapplied-filter protection, keyboard support, off-thread work, lifecycle and safe cancellation. Preserve audit CRUD, history, ETags and idempotency unchanged.
4. **Acceptance and publication:** extend the isolated two-ADMIN fictional demo with Unicode, identifiers, long remarks and archived records; independent engineering/UI review; complete default SQLite, isolated MySQL and native Windows regressions; Excel manual open/readability checks (record unavailable Excel as a limitation), light/dark, compact/maximized, real DPI and keyboard checks. Commit meaningful milestones, then publish one draft PR and verify hosted Windows/SQLite/MySQL CI. No merge.

Testing must cover all filter combinations and sort choices, multi-page export beyond the visible page, exact cell contents and types, formula-like `=`, `+`, `-`, `@` and whitespace-prefixed payloads, explicit hyperlinks, invalid XML characters, cancellation at each stage, failure during workbook close/publication, session expiry, legacy desktop rejection, UI responsiveness and clean shutdown. Never use production MySQL or real business records in screenshots/tests.

## Approval gate and exclusions

Approve the Excel-first scope, workbook metadata columns, limits and pagination caveat before implementation. PDF, packaging, reports navigation, analytics, production access, new grants/migrations, backend role changes and Phase 3E are excluded. If PDF is requested now, revise this design to specify Unicode fonts, pagination, safe PDF generation and separate native print acceptance before coding.
