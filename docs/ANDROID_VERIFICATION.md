# Phase 4A verification — 2026-10-28

Scope: read-only Android foundation based on merged main `c1f7cf6` and approved
design `b373011`. No backend schema, migrations, grants, production records or
Windows ADMIN-only admission were changed.

## Automated and native evidence

- Flutter unit/widget suite: **60 passed, zero failed, zero skipped**.
- Full default Python regression: **514 passed, 60 skipped** in 72.92 seconds.
- Full isolated MySQL regression: **518 passed, 56 skipped** in 183.35 seconds.
  Only dedicated `driver_audit_test_phase1` migration/runtime credentials were
  exported into that process. Default mode omitted live MySQL credentials. Skip
  counts include opt-in native Windows/packaging checks; hosted Windows jobs
  provide their separate acceptance gate. No skip is counted as a pass.
- `flutter analyze --fatal-infos`: no issues; all Dart application, test,
  integration-test and screenshot-driver sources formatted.
- Enforced application lockfile resolves successfully with Flutter 3.47.8 and
  Dart 3.13.7. Temurin 21.0.12.1+1 builds the Android application.
- Normal debug APK built successfully. A separate native-acceptance debug APK
  also built successfully with explicit loopback-only test configuration.
- Actual emulator: Android 16/API 36, x86_64, `emulator-5554`, 720×1560 at 320 dpi.
  Boot completion returned `1`; the application installed and launched.
- One real-API native acceptance scenario passed for both ADMIN and AUDITOR:
  normal authentication, 60 active fictional records, two disjoint 25-record
  pages, detail refetch and historical-name agreement, rendered audit/details
  screens and logout to cleared login. Framework teardown adds a second progress
  counter; it is not a second business test.
- Six genuine Flutter-surface screenshots were captured on that running Android
  application, then independently inspected for readable light/dark styling,
  Unicode, wrapping and viewport clipping. No visible blocker was found.

| ADMIN / light | AUDITOR / dark |
| --- | --- |
| [Audits](images/android-phase4a/demo_admin-audits.png) | [Audits](images/android-phase4a/demo_auditor-audits.png) |
| [Details](images/android-phase4a/demo_admin-details.png) | [Details](images/android-phase4a/demo_auditor-details.png) |
| [Signed out](images/android-phase4a/demo_admin-signed-out.png) | [Signed out](images/android-phase4a/demo_auditor-signed-out.png) |

All screenshot content is fictional. Screenshots cover the Flutter app surface,
not Android system UI or a physical handset.

## Independent review and corrections

- Throwing transport cleanup could replace sanitized cancellation or produce an
  unhandled stream error. Existing regression reproduced it; closing and stream
  cancellation now contain both synchronous and asynchronous cleanup failures.
- Repeated pause/resume during delayed `/auth/me` could reveal cached records
  before validation completed. A failing widget regression reproduced it; resume
  calls now await the same validation future within a session generation.
- A failed page request could label previous-page records as the requested page
  and allow Next to skip it. Failing regression reproduced it; changed query/page
  requests clear the previous result, while same-query refresh can retain stale
  records with a warning.
- Independent reviewer inspected both corrections and the six actual native
  screenshots; no additional important source or visible UI blocker remained.

## Remaining acceptance boundaries

Physical-phone installation, TalkBack navigation, real Android keyboard layouts,
production trusted-HTTPS certificates and deployment remain unverified. Compact
320dp and enlarged-text behavior have automated widget coverage; the recorded
native device uses 360 logical pixels. Process/session races, expiry, cancellation,
safe failures, redirect/body limits and strict response validation have automated
coverage; screenshots alone do not prove these properties.

This is internal foundation verification, not signed Android distribution or
production deployment approval. Offset-pagination changes during concurrent
backend writes remain an API limitation. No Android mutations or offline data
storage are included. See ANDROID_DEVELOPMENT.md for the disposable demonstration.
