# Phase 3D Excel export verification

Verified on Windows, 2026-10-27, from main baseline `93f6bcbed390c383c9e6883cee7bab42b248c69f`.

## Implemented

Driver Audits exports all matching REST pages using applied search, station, dates, auditor scope, ordering and archived inclusion. Genuine XLSX output contains the seven unchanged business fields plus Record ID/Status, literal text identifiers and untrusted text, frozen/filterable headings, bounded widths and wrapped remarks. A second sheet records generation times, count, filter summary and consistency/security caveats.

Application-owned background work survives navigation/theme rebuilding. Save selection, progress, cancellation, useful errors, session expiry, logout and window close are handled without worker access to Tk widgets. Existing sidebar destinations, table density, ADMIN-only admission, audit CRUD, ETags, idempotency and history are preserved. No backend, schema, migration, grant or production-record changes.

## Final local evidence

| Verification | Actual result |
| --- | --- |
| Full SQLite/default suite, native GUI enabled | **538 passed, 4 skipped**, 185.63 seconds |
| Full isolated MySQL suite, native GUI enabled | **542 passed, 0 skipped**, 238.28 seconds |
| Focused final export engine/API/native regressions | **60 passed**, including nonblocking publication cancellation |
| Actual disposable REST export | 105 records across two pages; archive exclusion/inclusion and AUDITOR archive denial verified |
| Large export | 20,000 complete records, no truncation |
| Native actual-API capture | 10 screenshots; **0 Python/Tcl callback errors** |
| Native close while export request blocked | Prompt return, cancelled output, no final/temporary files, worker completed safely, no callback errors |
| Syntax/dependency integrity | compileall passed; pip check found no broken requirements |
| Changed-file credential-pattern scan | 0 matches; ignored `.env`, `local` and `artifacts` files not tracked |

The four default-mode skips explicitly require live MySQL: authentication/schema verification, migration roundtrip and two runtime-permission checks. They passed in isolated MySQL mode; skips are not counted as passes. Final SQLite verification was repeated after the last cancellation correction; the older 537-pass log is superseded.

Local logs remain under ignored `artifacts/phase3d-full-default-final.txt`, `phase3d-full-mysql-final.txt`, `phase3d-native-final.txt`, `phase3d-close-export.txt` and `phase3d-excel.txt`. Hosted Windows/SQLite/MySQL results and final published SHA are recorded on the draft PR and in the completion report, after the publication checkpoint.

## Microsoft Excel and native visuals

Microsoft Excel **16.0** opened the fictional **61-record** workbook read-only with macros/link updates disabled. Confirmed leading-zero plate `000123` stored as text, Unicode, literal `=SUM(1,2)`, long remarks (3,730 characters), frozen heading, autofilter, no formulas and no hyperlinks. ZIP/XML contract tests additionally verify full supported 10,000-character remarks and all nine cell types. No real business workbook or production data was opened.

Native acceptance used **144 DPI (150%)** and compact/maximized windows in light/dark themes. Both normal ADMIN accounts exported successfully: 60 active records, 61 including archived, and 40 belonging to the second administrator. Keyboard activation, Escape and Page Up/Down disclosure scrolling are tested. Other actual OS DPI settings, mixed-monitor transitions, screen readers and non-Microsoft spreadsheet applications remain unverified.

- [Driver Audits / light](images/desktop-phase3d/export-light.png)
- [Human-readable filter confirmation](images/desktop-phase3d/filter-confirmation.png)
- [Background progress / dark](images/desktop-phase3d/export-progress-dark.png)
- [Compact window / saved report](images/desktop-phase3d/compact-export.png)
- [Actual Microsoft Excel workbook](images/desktop-phase3d/microsoft-excel.png)

## Independent review and corrections

Two independent read-only reviews covered engineering/security and UI/UX/architecture. Reproduced defects received focused regression coverage before correction:

- Existing-file fingerprint/replace race: use atomic no-clobber publication and **require a new filename**. Confirmed overwrite is deliberately unavailable to preserve existing files against concurrent writers.
- Cleanup failure masking an active HTTP 401: preserve authentication status and expose the cleanup warning at login.
- Temporary XML duplication during workbook finalization: conservative workspace headroom reserved before close.
- Elapsed deadline after slow fsync: recheck at the locked publication decision.
- Cancellation waiting on slow file publication: nonblocking Event signal; cancellation after the commit decision cannot undo a completed report.
- Internal query values and overflowing confirmation disclosure: readable HR labels and keyboard scrolling.

Final source checks from both reviewers reported no unresolved findings. Native tests and screenshots were executed by the primary agent, not claimed as reviewer execution.

## Dependency and limitations

Only report dependency: **XlsxWriter==3.3.0**, installed through `requirements-reports.txt`, included by desktop requirements and Linux CI. Python 3.14 support and release verified from [PyPI](https://pypi.org/project/xlsxwriter/3.3.0/); [upstream security page](https://github.com/jmcnamara/XlsxWriter/security) reported no published advisories at review time. This is not a guarantee against unknown vulnerabilities.

- Offset pagination is not snapshot isolation; some concurrent edits are undetectable. Export while other administrators are not editing.
- Existing files are never overwritten; select a new filename. Atomic publication requires hard-link support, such as local NTFS.
- Limits: 20,000 rows, 200 pages, 100 MiB text payload, 256 MiB temporary workspace with conservative headroom, ten minutes. Limit failures never publish truncated results.
- Cancellation waits for current HTTP/library work to return; publication already accepted cannot be undone. Abrupt process termination can leave temporary files; normal cleanup failures are reported.
- Saved reports are unencrypted and remain after logout. Protect their destination and sharing.
- PDF, packaging, Android and subsequent phases are excluded. No production MySQL access or deployment was performed.

Launch the safe two-ADMIN fictional demo with `python -m scripts.desktop_demo`; see [full instructions](WINDOWS_DESKTOP_EXPORT.md#disposable-demonstration).
