# BHLI Audit Windows desktop

Phase 3C provides an ADMIN-only sidebar workspace with compact audit tables,
audit creation/editing/soft deletion/history and essential administrator account
actions inside My Account, all through the existing FastAPI endpoints.
Install `requirements-desktop.txt`, then run
`python -m desktop` from the repository root.

See [setup, architecture, security and tests](../docs/WINDOWS_DESKTOP.md).

# Excel export

Driver Audits exports all matching pages to a genuine `.xlsx` workbook. See [export workflow, limits and disposable demo](../docs/WINDOWS_DESKTOP_EXPORT.md). Use a new filename; existing workbooks are never overwritten.
