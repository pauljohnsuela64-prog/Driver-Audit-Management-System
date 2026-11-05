# BHLI AUDIT — PHASE 6C: WINDOWS OFFLINE FOUNDATION

**Project:** `C:\BHLI-Audit`

**Repository:** `pauljohnsuela64-prog/Driver-Audit-Management-System`

**Verified main baseline:**
`81d0439d96c0578cb68d8130ef91e2dfd2629533`

**Previous milestone:** Phase 6B merged through PR #13.

## OBJECTIVE

Implement the Windows Offline Foundation for BHLI Audit.

The Android Offline Foundation has been completed and merged into main.

Our next goal is to make the Windows CustomTkinter application work completely offline using a local SQLite database.

The Windows offline edition must offer the same core audit-recording functionality as the Android offline edition.

**Do not rebuild the Windows interface from scratch.**

Reuse the existing code, visual design, forms, validation, history screens and business rules wherever practical.

Preserve the existing online Windows application and published Version 1.0 release.

## 1. VERIFY REPOSITORY BASELINE

Before making changes:

1. Inspect the current Git branch, HEAD and working tree.
2. Fetch the latest `origin/main`.
3. Verify the Phase 6B merge and its ancestry.
4. Confirm all five Phase 6B commits are preserved.
5. Verify the working tree is clean.
6. Inspect repository instructions, architecture and existing tests.
7. Review the completed Phase 6A offline architecture recommendations and actual Phase 6B SQLite implementation.

Recommended new branch:

`feat/dams-windows-offline-foundation`

Create the branch from the verified latest main.

If unexpected uncommitted changes or conflicting work are found, preserve them and report the issue rather than discarding anything.

## 2. WINDOWS OFFLINE ARCHITECTURE

Use Python's built-in `sqlite3` for local database storage.

Do not require:

- FastAPI.
- MySQL.
- A running backend process.
- An API connection.
- Internet access.
- Wi-Fi.
- Cloud hosting.
- A database username or password.

The Windows offline application must operate independently.

Preserve the existing FastAPI and MySQL source code for the original Version 1.0 application.

Create a separate offline application entry point and local repository interface.

Do not simply replace the REST client with a different connection string.

## 3. SEPARATE WINDOWS INSTALLATION IDENTITY

The Windows Offline Edition must coexist safely with the original online Windows version.

Proposed application name:

`BHLI Audit Offline`

Use an independent:

- Application entry point.
- Installer identity/GUID.
- Installation directory.
- Application shortcut.
- Application data directory.
- Single-instance identity, if applicable.

Store persistent SQLite data in an appropriate per-user Windows application data directory, such as:

`%LOCALAPPDATA%\BHLI Audit Offline\`

Never store the employee's live database inside the installed application binaries or temporary build folders.

Application updates must preserve existing SQLite records.

Do not uninstall, replace or modify the original Version 1.0 software.

## 4. SQLITE DATA MODEL

Inspect the actual Phase 6B Android SQLite implementation first.

Use compatible logical entities, identifiers, validation and history semantics on Windows.

Expected entities include:

- `app_meta`
- `local_profile`
- `audit_records`
- `audit_events`

Preserve the same seven audit fields:

1. Driver's Name
2. Helper's Name
3. Audit Date
4. Station
5. Plate Number
6. Remarks
7. Audited By

Maintain the existing field requirements and limits.

Requirements:

- Globally unique record UUIDs.
- Immutable original auditor attribution.
- Creation and modification timestamps.
- Record revisions.
- Archive state.
- Local history.
- Transactional operations.
- Schema versioning and migrations.
- Foreign-key enforcement.
- Safe database error handling.

Use SQLite constraints and Python validation appropriately.

Establish cross-platform compatibility tests against the existing Android field and normalization contract.

## 5. LOCAL AUDITOR PROFILE

On the first launch of the offline Windows application:

- Ask the employee for their name.
- Create a local auditor profile.
- Store a unique local profile ID.
- Use the name for new audit records.
- Allow the locally configured name to be changed in settings.

Changing the profile name must not rewrite historical Audited By values.

A profile name is locally declared, not independently verified authentication.

Do not create a fake ADMIN user, default password or server authentication session.

## 6. REUSE THE EXISTING WINDOWS UI

Preserve the polished CustomTkinter interface wherever possible.

Adapt the existing screens and operations for:

- Dashboard or main audit workspace.
- Creating audits.
- Viewing records.
- Searching and filtering.
- Editing existing audits.
- Archiving.
- Viewing history.
- Local auditor settings.
- Empty-list states.
- Error handling.

Remove the need to enter an API URL or log in through the server for this offline entry point.

Do not delete the original online UI or its authentication behavior.

Ensure the employee can launch the offline software and begin recording audits without technical configuration.

## 7. SAFE DATABASE OPERATIONS

Pay particular attention to the existing desktop worker and background-task architecture.

The Phase 6A review identified that the existing workers were designed around HTTP operations and may not be suitable for durable local database writes without adaptation.

Requirements:

- SQLite connections must remain on their owning threads.
- UI updates must occur safely on the GUI thread.
- Record creation and history insertion must be atomic.
- Editing must reject stale revisions.
- Retries must not duplicate records.
- Failed commits must not leave partial history.
- Application shutdown must not silently abandon writes.
- Database locks, disk-full errors and corrupted databases must produce clear user-facing errors.
- Do not overwrite an existing user database to recover from initialization failures.

Preserve data correctness over UI responsiveness shortcuts.

## 8. OFFLINE OPERATION

The Windows application must work when:

- Internet is disconnected.
- Wi-Fi is disabled.
- FastAPI is stopped.
- MySQL is stopped.
- No local or remote server is available.

The application must not attempt unexpected network requests during normal offline operation.

Records must persist across:

- Closing and reopening the application.
- Windows restart.
- GUI errors.
- Failed write attempts that roll back safely.

## 9. CLEAN FIRST-LAUNCH EXPERIENCE

A newly installed Windows Offline Edition must contain:

- Zero audit records.
- No fictional driver names.
- No fake station records.
- No default demonstration accounts.
- No preloaded test database.
- No API setup requirement.

Display a useful empty-state message.

The employee must be able to configure their local profile and create their first audit.

Keep development fixtures inside isolated tests.

Never delete actual user data to make an installation appear clean.

The full employee-ready cleanup remains Phase 6G.

## 10. REPORTING BOUNDARIES

Preserve the existing Excel reporting engine and its source code.

Review how it currently depends on the REST API.

Prepare a clean interface that can later read records from SQLite.

However, complete daily, weekly, monthly and custom-date offline report generation in Phase 6E.

Do not introduce an unreliable or incomplete reporting system simply to finish Phase 6C.

Document any reporting screens intentionally deferred to Phase 6E.

## 11. TESTING REQUIREMENTS

Add appropriate automated tests covering:

- Database creation.
- Empty first launch.
- Auditor profile initialization.
- Record creation.
- Record searching and filtering.
- Record editing.
- Revision conflicts.
- Archive behavior.
- History correctness.
- UUID retry protection.
- Validation parity with Android.
- Transaction rollback.
- Database persistence.
- Application restart.
- Thread ownership.
- Shutdown during pending writes.
- Database locking.
- Disk-full simulation.
- Migration safety.
- Absence of unwanted network requests.
- Original online Windows regression safety.

Run existing applicable Python, SQLite, desktop and packaging tests.

Verify formatting, dependency and packaging checks.

Build a Windows offline development candidate if the current environment supports it.

Do not claim physical-device or installation acceptance unless those tests were actually executed.

Use fictional test data only.

## 12. PRESERVE THE ORIGINAL RELEASE

Do not modify or delete:

- Published Version 1.0 binaries.
- Version 1.0 release tags.
- Existing online entry points.
- FastAPI source.
- MySQL migrations.
- Existing tests.
- Original Windows installation data.
- Phase 6B Android offline functionality.

Keep production data inaccessible and unchanged.

Historical MySQL records are out of scope.

## 13. GITHUB WORKFLOW

GitHub commits are required for completed development work.

Follow this process:

1. Work on the isolated Phase 6C branch.
2. Implement changes in small logical steps.
3. Add tests for each significant change.
4. Run focused tests.
5. Run applicable regression tests.
6. Review changes for correctness and security.
7. Create descriptive local Git commits.
8. Verify that the working tree is clean.
9. Record commit hashes and test evidence.

Local commits are authorized.

**Do not push the branch or open a PR yet.**

Do not merge into main.

Do not create release tags or publish installers.

Do not force-push or rewrite existing history.

We will conduct a separate review before GitHub publication, following the Phase 6B workflow.

## 14. FUTURE DEVELOPMENT PHASES

Do not begin these tasks:

- Phase 6D — Manual Android/Windows record transfer.
- Phase 6E — Offline reporting and backup/restore.
- Phase 6F — Offline release and installation acceptance.
- Phase 6G — Final cleanup and employee-ready release.

Preserve compatibility with their planned requirements.

In particular, the Windows SQLite model must support future import/export without losing record identities or history.

## 15. FINAL DELIVERABLE

Provide a full Phase 6C report containing:

1. Starting and ending Git state.
2. Local commit hashes.
3. Changed files.
4. Reused existing Windows modules.
5. SQLite schema and migration design.
6. Local auditor profile behavior.
7. Completed offline workflows.
8. Transaction and shutdown safeguards.
9. Automated test results.
10. Windows candidate build results.
11. Any native installation limitations.
12. Original Version 1.0 preservation verification.
13. Outstanding issues or known limitations.
14. Readiness for GitHub review and publication.

## FINAL INSTRUCTION

Implement and verify Phase 6C locally.

Keep the original online application working.

Do not touch actual employee records.

Do not proceed to another phase.

STOP after successful implementation, testing, independent review and local Git commits.

Wait for operator approval before GitHub publication.