# Source license, artwork and branding rights

Copyright 2026 Paul John Suela applies to the original contributions the owner
has authority to license. Those contributions use [Apache License 2.0](LICENSE).
See [NOTICE](NOTICE) for project attribution. The grant does not cover the entire
repository without exceptions.

## Original source scope

The grant covers authorized original portions of Python code in `backend/`,
`desktop/`, `scripts/`, `migrations/` and `tests/`; Dart code and tests in
`mobile/lib/`, `mobile/test/`, `mobile/integration_test/` and `mobile/test_driver/`;
original SQL/provisioning source in `database/`; original Kotlin, Android XML
configuration and Gradle configuration under `mobile/android/`; original build
source in `packaging/`; original repository/CI configuration; and original text
documentation, including README, CHANGELOG and Markdown under `docs/`.

This describes original contributions, not a claim of authorship over generated
templates, imported code, dependency/toolchain files or copied license texts.
Upstream rights in those portions remain intact. In particular, material under
`packaging/notices/`, the bundled JUnit source archive and dependency resources
retain their own terms. The exact protected assets below are excluded even when
they sit within an otherwise licensed source directory. Historical Git authorship
and upstream notices are preserved.

## Branding and excluded artwork

BHLI names, trade names, marks, logos and company branding are not granted for
unrestricted use by the application-source license. Artwork copyright is excluded
separately from trademark rights. This document does not determine who owns any
excluded image or screenshot; depicting BHLI does not prove BHLI owns the whole
image or all material visible within it. No new asset license is created here.

The operator has confirmed permission to distribute the official BHLI-branded
builds. That specific permission is not a downstream trademark sublicense and
must not be read as permission for arbitrary forks, altered logos, endorsement
claims or reuse of protected screenshot content. Obtain permission from the
relevant rights holder before such use. Exclusion does not remove permissions or
exceptions that applicable law may independently provide.

Public source availability and the source-code license do not grant API access,
credentials, access to real company records or rights to personal information.

## Third-party resources

| Resource actually used by client builds | Separate terms and attribution |
| --- | --- |
| CustomTkinter themes, icons and shapes font | Package MIT terms retained; independent artwork authorship is not asserted here |
| Bundled Roboto Regular/Medium 2.137 | Apache 2.0 and embedded Google attribution, preserved in Windows notices |
| Pillow image/font codecs | Complete Pillow composite licenses plus FreeType/IJG product acknowledgments |
| Flutter MaterialIcons font | The matching bundled font carries CC BY 4.0; Google attribution and its supplied license are retained |
| Flutter/Dart engine resources and native dependencies | Their component and composite notices remain applicable |
| Segoe UI | Windows system font use; no font files are copied or relicensed by this project |

See [third-party notices](THIRD_PARTY_NOTICES.md). These are not converted to the
application's Apache grant. A permissive package license is not proof that every
independent asset has the same author or origin.

## Developer replacement guidance

For a generic build, supply artwork you have permission to use in place of the
excluded desktop icon and Android launcher/launch artwork at the paths below.
Replace BHLI-facing names and marks in your fork as appropriate; review captions,
window/launcher labels and documentation screenshots as well. Do not carry the
protected screenshots into a newly branded product without permission. Retain
applicable source and third-party notices, and state your modifications as Apache
2.0 requires. Choosing new package identities is a separate distribution decision;
this checkpoint does not change existing identities, assets or application logic.

## Exact protected asset paths

All 66 paths below are excluded from the original-source Apache grant. They are
repository source paths, not an installed-file manifest. Their listing does not
assign copyright ownership or grant an artwork license. Third-party elements
within captures may carry additional rights.

| Excluded source path | Category |
| --- | --- |
| `desktop/assets/bhli.ico` | Protected icon/launcher/launch artwork |
| `docs/images/android-phase4a/demo_admin-audits.png` | Protected screenshot/capture |
| `docs/images/android-phase4a/demo_admin-details.png` | Protected screenshot/capture |
| `docs/images/android-phase4a/demo_admin-signed-out.png` | Protected screenshot/capture |
| `docs/images/android-phase4a/demo_auditor-audits.png` | Protected screenshot/capture |
| `docs/images/android-phase4a/demo_auditor-details.png` | Protected screenshot/capture |
| `docs/images/android-phase4a/demo_auditor-signed-out.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/compact-form-scroll.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/compact-landscape-history.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/compact-optional-helper.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/phase4b-admin-archive-confirm.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/phase4b-admin-archived-details.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/phase4b-admin-history-page2.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/phase4b-auditor-b-read-only.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/phase4b-auditor-conflict.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/phase4b-auditor-create.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/phase4b-layout-dirty-form.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/phase4b-layout-landscape.png` | Protected screenshot/capture |
| `docs/images/android-phase4b/phase4b-layout-optional-remarks.png` | Protected screenshot/capture |
| `docs/images/desktop-acceptance/auditor-own-records.png` | Protected screenshot/capture |
| `docs/images/desktop-acceptance/audits-expanded.png` | Protected screenshot/capture |
| `docs/images/desktop-acceptance/compact-filters.png` | Protected screenshot/capture |
| `docs/images/desktop-acceptance/maximized.png` | Protected screenshot/capture |
| `docs/images/desktop-acceptance/original-attribution.png` | Protected screenshot/capture |
| `docs/images/desktop-acceptance/second-page.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3b/create-compact-dark.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3b/create-light.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3b/delete-confirmation.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3b/edit-conflict.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3b/history-dark.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3b/history-light.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3c/add-admin-form.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3c/admin-accounts-dark.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3c/admin-accounts-light.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3c/audits-light.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3c/compact-navigation.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3c/dashboard-light.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3c/disable-confirmation.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3c/legacy-rejected.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3c/reset-form.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3d/compact-export.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3d/export-light.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3d/export-progress-dark.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3d/filter-confirmation.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3d/microsoft-excel.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3e/compact.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3e/connection.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3e/dashboard.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3e/export-dark.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3e/export-light.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3e/history.png` | Protected screenshot/capture |
| `docs/images/desktop-phase3e/login.png` | Protected screenshot/capture |
| `docs/images/desktop/admin-dashboard-light.png` | Protected screenshot/capture |
| `docs/images/desktop/auditor-dashboard-dark.png` | Protected screenshot/capture |
| `docs/images/desktop/audits-dark.png` | Protected screenshot/capture |
| `docs/images/desktop/compact-filters-light.png` | Protected screenshot/capture |
| `docs/images/desktop/details-attribution-dark.png` | Protected screenshot/capture |
| `docs/images/desktop/login-light.png` | Protected screenshot/capture |
| `mobile/android/app/src/main/res/drawable-v21/launch_background.xml` | Protected icon/launcher/launch artwork |
| `mobile/android/app/src/main/res/drawable/bhli_mark.xml` | Protected icon/launcher/launch artwork |
| `mobile/android/app/src/main/res/drawable/launch_background.xml` | Protected icon/launcher/launch artwork |
| `mobile/android/app/src/main/res/mipmap-hdpi/ic_launcher.png` | Protected icon/launcher/launch artwork |
| `mobile/android/app/src/main/res/mipmap-mdpi/ic_launcher.png` | Protected icon/launcher/launch artwork |
| `mobile/android/app/src/main/res/mipmap-xhdpi/ic_launcher.png` | Protected icon/launcher/launch artwork |
| `mobile/android/app/src/main/res/mipmap-xxhdpi/ic_launcher.png` | Protected icon/launcher/launch artwork |
| `mobile/android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png` | Protected icon/launcher/launch artwork |
