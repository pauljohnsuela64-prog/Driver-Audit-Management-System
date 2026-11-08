# BHLI AUDIT — FINAL WINDOWS SIDEBAR STABILITY & SIMPLIFICATION

Project: `C:\BHLI-Audit`

Repository: `pauljohnsuela64-prog/Driver-Audit-Management-System`

Approved main:
`844042defb44db8cdc8d80217df04d5a8b0a973e`

Existing compact-button branch:
`feat/dams-backup-action-layout`

Existing compact-button commit:
`44f9363`

## Objective

Implement the operator-approved Option A navigation redesign for the **Windows offline application only**, while fixing the confirmed sidebar stability issues.

Keep all existing driver audit, reporting, backup/restore, transfer, auditor identity and SQLite behavior intact.

Do not introduce new features.

## 1. Git and preservation requirements

Before editing:

1. Inspect the current branch, HEAD and working tree.
2. Verify that the compact-button commit `44f9363` exists and its changes are preserved.
3. Fetch origin and verify current main ancestry.
4. Create a dedicated implementation branch based on the compact-button commit, provided its ancestry is correct.
5. If the repository state differs from expectations, stop and report rather than resetting or discarding work.
6. Preserve existing Phase 6F and Phase 6G candidates, SQLite databases, screenshots and release assets.

Do not use `git reset --hard`, force-push, or destructive cleanup.

The final PR should contain both the compact-button improvement and the approved sidebar refinements if the compact-button change has not already been merged independently.

## 2. Approved navigation structure

Replace the current ordinary sidebar destinations:

- Dashboard
- Driver Audits
- Local profile

With:

- **Driver Audits**
- **Settings & Tools**

Driver Audits becomes the first page after the existing auditor welcome/Continue flow.

Remove Dashboard as a separate sidebar destination, but do not delete useful functionality without checking whether it is available elsewhere.

Preserve the existing audit recording, details, history, editing, sorting, search, filtering, pagination and Excel export functionality.

Keep **New Audit** and **Export to Excel** immediately accessible on Driver Audits.

Do not create a separate Reports screen.

## 3. Settings & Tools page

Implement a clean dedicated Settings & Tools page.

Group the existing functions logically:

### Local Auditor Profile
- Display and update the local auditor name using existing behavior.
- Keep any required recovery or missing-profile flow accessible.

### Backup & Restore
- Provide access to the existing backup and restore interfaces.
- Preserve the compact, consistent button layout from commit `44f9363`.
- Keep existing warnings, acknowledgement, recovery backups and confirmations.

### Manual Data Transfer
- Provide access to the existing transfer workflow.
- Preserve preview/import validation and cancellation behavior.
- Ensure transfer remains easy to locate without adding another ordinary sidebar destination.

### Appearance
- Move the light/dark theme selector here.
- Keep existing theme functionality and readability.

Remove duplicated profile controls from ordinary navigation or headers only when their functionality remains accessible from Settings & Tools.

Do not create an additional authentication, account or password system.

## 4. Fix confirmed sidebar issues

### A. Resize instability

Current confirmed reproduction:

- Set window to approximately 800×650.
- Manually expand sidebar.
- Resize to approximately 801×650.
- Sidebar unexpectedly collapses.

Fix the state-management logic so ordinary resize events do not continually override the user's explicit choice.

If automatic collapse is necessary for compact widths, make it predictable and apply it only on appropriate size-band transitions.

Prevent jitter, repeated layout recalculations and unstable intermediate states.

### B. Theme reset

Current confirmed behavior:

- Collapse sidebar at a wide window size.
- Change theme.
- Sidebar expands unexpectedly.

Preserve user-selected collapse/expand state during shell or theme rebuilding.

The appearance change must not unexpectedly navigate away or discard unsaved form content.

### C. Audit History highlight

Make Audit History consistently highlight **Driver Audits**, matching related audit detail screens.

Ensure Settings & Tools and its child screens retain appropriate active navigation highlighting.

### D. Mouse hover and tooltip behavior

Keep the standard hand-shaped pointer over clickable buttons.

- Remove redundant tooltips for expanded sidebar buttons that already show readable labels.
- Keep tooltips for collapsed icon-only navigation.
- Avoid immediate tooltip placement beneath the pointer.
- Prefer a short delay and an offset outside the button.
- Cancel pending tooltip display when the pointer leaves, navigation changes, or the sidebar expands.
- Avoid flickering, orphaned tooltips and stale widget references.

Do not claim physical-pointer flicker is fixed unless actually reproduced and verified.

### E. Collapse/expand visual stability

Make transitions clean and predictable.

Verify:

- No duplicate button rendering.
- No clipped or stale company logo.
- No flickering labels.
- No unexpected state resets.
- No rapid width oscillation.
- No callback errors.
- No unnecessary animations that worsen performance.

Preserve the already verified collapsed-logo fix.

## 5. Protect business workflows

Retain all seven original audit fields:

1. Driver name
2. Helper name
3. Audit date
4. Station
5. Plate number
6. Remarks
7. Audited by

No additional fields.

The application must remain fully standalone and offline.

Do not introduce:

- API dependencies
- MySQL requirements
- Internet connectivity
- Login/password authentication
- New reporting modules
- Database migrations without a demonstrated need

Preserve stable record identities, history, persistence, backups and transfers.

## 6. Test-driven verification

Before fixing sidebar state behavior, reproduce the confirmed issues with regression tests.

Cover:

- Resize near compact/expanded breakpoints.
- Repeated collapse and expansion.
- Theme changes in both sidebar states.
- Navigation and history highlighting.
- Tooltip lifecycle and positioning.
- Logo rendering.
- Settings & Tools accessibility.
- Existing profile recovery paths.
- Transfer navigation.
- Backup and restore entry points.
- Navigation after cancel/return.
- 100%, 150% and 200% widget scaling.
- Multiple supported window widths.

Check that essential actions are keyboard accessible.

Reuse prior passing test evidence where applicable, but run all affected native Windows GUI tests and relevant Python regression tests.

Capture before/after screenshots for review.

Distinguish automated geometry checks from actual Windows DPI transitions or physical mouse observations.

## 7. Independent code review

Review the implementation for:

- Unintended workflow changes.
- Unsaved data loss on navigation/theme changes.
- Broken active-page highlighting.
- Inaccessible controls.
- Tooltip/widget lifecycle problems.
- Performance or layout regressions.
- Missing backup access when no local profile exists.
- Unexpected changes outside Windows offline UI.

Correct confirmed defects before PR preparation.

## 8. GitHub delivery

If tests and review pass:

1. Commit the implementation in logical commits.
2. Push the dedicated branch.
3. Open a **draft pull request** against main.
4. Include the compact-button commit if still unmerged.
5. Attach screenshots, reproduction results and tests.
6. Verify required hosted CI checks.
7. Provide the PR URL, commits, test results and outstanding limitations.

Do not merge automatically.

## 9. Restrictions

- No Android UI changes.
- No new features or architecture changes.
- No changes to real audit records.
- No overwriting previously accepted EXE/APK/installer artifacts.
- No new final installation builds yet.
- No release publication.
- No changes to signing keys.

## Final deliverable

Report:

1. Exact sidebar bugs reproduced and fixed.
2. Final navigation structure.
3. Confirmation that compact Backup & Restore buttons are preserved.
4. Windows GUI and regression test results.
5. Screenshots and visual review.
6. Draft PR and hosted CI status.
7. Remaining acceptance requirements.

Stop after the draft PR is prepared and verified.