# Offline visual refinement — Phase 6G

This change keeps the existing offline Windows and Android workflows. It changes presentation only: no audit fields, storage schema, roles, authentication, API requirements, application IDs or package IDs change. Existing Phase6F candidates and release assets are preserved.

## Styling and branding

- Muted blue primary `#315E8E` on light backgrounds; pale blue `#A8CFF0` for dark-mode actions/focus. Existing light/dark behavior and reusable controls remain. Normal text and primary-button text meet the tested 4.5:1 contrast threshold; focus against its surface meets 3:1.
- Windows chooses the offline tokens using the existing application's offline root marker. Android opts into the blue theme explicitly. The original online theme defaults remain unchanged.
- The official BASIC Hauling & Logistic Inc. artwork was supplied by the operator as `bhli LOGO.jpg`. Both bundled JPEG copies retain the exact original bytes and **957 × 250** dimensions, SHA-256 `432417eb95db3199ec1068cdacc0173680ac24e2664c622fda54b82129c53eb4`.
- The artwork is fitted proportionally without cropping or recoloring. Its original brand colors remain. Windows welcome/expanded navigation and Android welcome use it. Compact Windows navigation keeps its existing initials; a regression prevents the full logo remaining clipped behind those initials.
- Existing application/package IDs and launcher identities are retained.

## Windows table and backup layout

Driver Name, Helper Name, Station, Plate Number and Audited By cells are centered in offline tables. Existing column widths/minimums/stretch flags, 38-logical-pixel row density, sorting, selection, keyboard opening, scrolling and pagination remain intact. Audit Date and online table alignment are unchanged.

Backup/restore actions use one aligned fluid-width column. Long labels wrap and controls grow with their text at the tested scales. Explanation/status text follows the available width and remains scrollable. Warnings, passphrase handling, preview, recovery-backup requirements, acknowledgement, cancellation and final confirmation remain unchanged.

## Visual evidence

Only fictional test data appears. Windows images are native owned-window captures; Android images are **Flutter widget renders using existing SDK Roboto/Material fonts**, not physical-device or emulator screenshots. Font binaries are not added to the application/repository.

| Native Windows | Screenshot |
| --- | --- |
| Official welcome/logo and blue focus | [Welcome](images/phase6g/windows-welcome.png) |
| Centered offline audit columns | [Driver Audits](images/phase6g/windows-audits.png) |
| Aligned backup actions, light | [Backup top](images/phase6g/windows-backup-light.png) |
| Restore/cancel controls, dark and compact navigation | [Backup bottom](images/phase6g/windows-backup-dark.png) |

| Flutter widget rendering | Screenshot |
| --- | --- |
| Standard-width light welcome | [Android light](images/phase6g/android-welcome-light.png) |
| Standard-width dark welcome | [Android dark](images/phase6g/android-welcome-dark.png) |

## Verification scope and limits

Native geometry regressions cover both themes, compact `800×650` and wider `1200×700` logical window requests, and toolkit scaling multipliers `1×`, `1.5×`, `2×` where specified. They assert equal action widths, text containment, no vertical overlap, column anchors and collapsed/expanded logo handling. Toolkit multipliers run at the host DPI; they are **not** evidence of changing Windows display settings or moving between monitors with different DPI.

Mobile rendering regressions cover standard `390×844`, compact `320×640`, 200% text and keyboard insets, with the same Backup & restore entry point as the real offline repository. Existing offline persistence, attribution, reports, transfer and backup tests remain in the regression suites.

The updated visual source has not been reaccepted on a physical Android device or in a newly built frozen offline installer. The accepted Phase6F binaries remain unchanged; future updated candidates need their own visual acceptance. Android13+ remains the approved physical scope; API24 remains excluded. No signing, release publication or automatic merge is part of this change.

## Operator-requested button sizing follow-up

Backup and restore actions use one left-aligned column capped at 360 logical pixels, shrinking to the available width on narrow windows. Labels still wrap and button height follows the content. Existing actions, warnings, confirmation requirements and keyboard behavior are unchanged. Native geometry coverage asserts this width cap alongside equal widths, text containment and no overlap in both themes and existing scaling cases.
