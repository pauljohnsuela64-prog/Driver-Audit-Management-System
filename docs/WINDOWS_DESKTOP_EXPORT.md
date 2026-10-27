# Audit Excel export

In **Driver Audits**, apply search/filters and wait for results, then choose **Export to Excel**. Review the human-readable filter summary and choose a **new `.xlsx` filename** in a protected folder. Export includes all matching pages, regardless of the current table page. Unapplied filter edits must be applied first.

The workbook contains Driver Name, Helper Name, Audit Date, Station, Plate Number, Remarks and historical Audited By, followed by Record ID and Active/Archived Status. It preserves optional blanks, Unicode, leading-zero identifiers and full supported remarks. Text is stored as text, including formula-like input; there are no formulas, auto-generated hyperlinks, macros or external links. Headings are frozen and filterable. Long remarks are wrapped with a capped visual row height; the full text remains available in the cell/formula bar.

The Report information sheet records UTC generation times, actual count, applied filters/sort and consistency/security caveats. Current-user names do not replace original auditor-name snapshots.

## Progress, cancellation and safe files

Fetching and workbook generation run off the Tk UI thread. The status below the table shows progress and Cancel export; navigate away and return to Driver Audits to inspect the same job. Theme changes preserve the job. Escape on Driver Audits cancels; confirmation dialogs support Page Up/Down, arrows and Home/End for keyboard reading. Success includes actual count, destination and Open folder.

- One export at a time; no automatic retries or resume.
- Cancel, logout, session expiry and close request cancellation. A current HTTP operation may finish at its configured timeout before cleanup; workbook finalization cannot be interrupted mid-library operation. Final cancellation/session/deadline checks occur before publication.
- Existing files are **never overwritten**, even if a native Save As dialog offers overwrite confirmation. Choose a new filename. This is a deliberate tightening of the original design after independent review reproduced a check/replace race with another process.
- Reports publish atomically without clobbering a racing file. The selected filesystem must support hard links (for example, local NTFS). Unsupported filesystems fail safely; choose a local NTFS destination and move the finished file manually if needed.
- Temporary workbook data is kept in a unique `.dams-export-` directory beside the selected destination. Normal cancellation/errors clean it up. Cleanup failure is explicitly reported. Abrupt process termination can leave temporary files: inspect and remove only the abandoned DAMS directory after closing the app.
- Once publication has been accepted, cancellation cannot undo the completed report. Logout/revocation cannot retract saved files. Reports are unencrypted business-data documents; store/share them appropriately.

Limits: 20,000 records, 200 API pages, 100 MiB UTF-8 field payload, 256 MiB temporary workspace and ten minutes. Conservative workspace reservation includes streaming XML duplication, ZIP assembly and buffered-row headroom; export may therefore reject a large report before using the whole nominal disk budget. Limit failures never produce a truncated final report: narrow filters and retry.

## Consistency limitation

The REST API uses offset pagination, not a snapshot. The exporter rejects changed totals, duplicate IDs, wrong page sizes, unexpected archived rows and inconsistent ordering, with the original sort and ID tie-breaker preserved. It cannot detect every concurrent edit: matching totals do not prove snapshot consistency. Export while other administrators are not editing. No production schema, roles, migrations, grants or API contracts were changed.

## Disposable demonstration

From `C:\BHLI-Audit`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-desktop.txt
.\.venv\Scripts\python.exe -m scripts.desktop_demo
```

Choose two distinct passwords in the hidden local prompts. Sign in as `demo_admin` or `demo_admin2`. These are separate normal ADMIN accounts; the API/database is disposable loopback SQLite, not production MySQL. The legacy AUDITOR fixture is still rejected by desktop admission.

Try all 60 active records, Include deleted (61), My audits as the second administrator (40), station/date/search filters and both sorts. The fictional Unicode record has plate `000123` and formula-like remarks `=SUM(1,2)`, which must remain literal text in Excel. Another record has long remarks; archived history retains the original auditor name.

Choose a new filename, export, then open the completed report in Excel. Verify nine columns, leading zeros, Unicode, optional blanks, full remarks, archived status and literal formula-like text. Close the app to stop/remove the temporary API/database; saved export files remain under your control.

PDF, analytics, packaging and a Reports sidebar module are deferred.
