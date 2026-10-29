# Phase 4B Checkpoint 6 verification

Verified 2026-10-29 on `feat/dams-android-audit-management`, preserving
Checkpoint 5 `abb0072` and main baseline `54c1f2e`. Result: **PASS WITH
LIMITATIONS** for local checkpoint review; no publication or merge authorization.

## Automated evidence

| Check | Passed | Skipped | Failed |
| --- | ---: | ---: | ---: |
| Complete Flutter tests | 217 | 0 | 0 |
| Complete default Python suite | 549 | 60 | 0 |
| Complete isolated MySQL Python suite | 553 | 56 | 0 |
| Windows desktop including native GUI | 247 | 0 | 0 |

These suites overlap; do not add their totals. Default skips are 56 native GUI
and four live-MySQL cases. The MySQL run skips the 56 GUI cases exercised by the
separate native Windows run. No skipped test is represented as passed.
Flutter analysis has no issues; formatting checks 51 Dart files with no changes.
Dependency integrity and Python syntax checks pass.

The Python suites include 35 real-HTTP demo/mutation cases and three history
serialization cases. Coverage includes ADMIN and two distinct AUDITOR accounts,
stable-ID ownership, unchanged historical attribution, validation, same-key
concurrent creation, stale edits, edit/delete races, archive visibility, session
revocation/reactivation, exact history and dropped responses after real commits.
Fault injection is test-only and adds no shipping authentication bypass.
Ten worst-case escaped history events serialize to 1,302,356 bytes, below the
unchanged 2 MiB client cap; history remains ten events per page.

Ignored local logs: `artifacts/phase4b-cp6-full-flutter.txt`,
`phase4b-backend-{default,mysql,desktop}.txt`,
`phase4b-cp6-{analyze,format}-final.txt`, and
`phase4b-native-acceptance-final.txt`.

## Actual Android acceptance

Retained Flutter 3.47.8, Dart 3.13.7, Temurin 21.0.12.1+1 and Android emulator
37.2.12.0 were used. The actual Android 16/API 36 x86_64 emulator used WHPX,
host graphics and Vulkan disabled. No toolchain reinstall was necessary.

Three distinct native business scenarios pass against disposable FastAPI/SQLite:
mutation/fault contracts; three-account create/edit/conflict/archive/history
walkthrough; and responsive dirty-form/history/landscape interaction. Flutter's
additional teardown counter is not a fourth business scenario. Normal 360dp and
compact 320dp/200% text layouts were exercised, including light/dark states.

The ordinary main-entry APK was separately tested with actual ADB keyboard,
Back, HOME and process-restart operations. All eight assertions pass: login,
keyboard visibility, IME-before-dirty-confirmation Back behavior, secure window,
background account revocation hiding protected content, reactivation/new login,
process restart requiring login and public API-origin retention. Tokens and
drafts remain memory-only. The screenshot test build deliberately permits
fictional capture; ordinary main-entry secure-window protection was verified
separately. No signed release or physical-device acceptance is claimed.

## Confirmed corrections and independent review

- External wrapping form labels fix optional-label clipping at 320dp/200% text
  without the overlap found in the first attempted correction. Tests measure
  geometry and retain full semantic editor names.
- Nested system Back uses `maybePop` so dirty and pending form guards run.
  Regression tests cover keeping edits and truthful uncertain-write exit.
- Every interrupted lifecycle state now requires identity verification before
  cached protected content is revealed. A rapid inactive/resumed revocation
  previously exposed stale cached content (a privacy defect, not server-side
  authorization bypass). Delayed verification and real native revocation tests
  cover the correction.

Independent engineering/security and mobile-UX re-reviews found no remaining
confirmed blocker. Harness-only fixes address lazy scrolling, repeated fictional
names and authoritative IME visibility; they do not weaken product assertions.

## Genuine emulator screenshots

All records and identities are fictional. Normal-width captures:

- [Create form](images/android-phase4b/phase4b-auditor-create.png)
- [Conflict comparison](images/android-phase4b/phase4b-auditor-conflict.png)
- [Non-owner read-only details](images/android-phase4b/phase4b-auditor-b-read-only.png)
- [Archive confirmation](images/android-phase4b/phase4b-admin-archive-confirm.png)
- [Archived details](images/android-phase4b/phase4b-admin-archived-details.png)
- [History page two](images/android-phase4b/phase4b-admin-history-page2.png)

Separate compact 320dp/200% captures:

- [Wrapping helper label](images/android-phase4b/compact-optional-helper.png)
- [Enlarged form scroll position](images/android-phase4b/compact-form-scroll.png)
- [Landscape history](images/android-phase4b/compact-landscape-history.png)

## Isolation and Windows compatibility

Only `driver_audit_test_phase1` with `dams_test_migrate`/`dams_test_app` was used
for MySQL tests; fixtures start and finish empty. Production connections were
excluded from regression subprocesses. No backend business rules, schemas,
migrations, grants, Windows shipping source or dependencies changed.

The retained Windows bundle is source-equivalent for unchanged desktop/packaging
inputs (artifact source `0a06f2c`). Inspection checks 375 modules and finds no
forbidden backend/private configuration payloads. Isolated-profile frozen-client
launch smoke passes; this is not a full packaged authentication walkthrough.
Installer contracts pass in desktop tests. Native install/uninstall roundtrip
was deliberately not run because an existing developer installation is present;
it was preserved. No unrelated process or installed application was removed.

## Remaining limits and handoff

- Physical Android, API 24, actual TalkBack traversal and trusted production
  HTTPS acceptance remain unverified. Automated emulator acceptance does not
  replace the operator's personal manual acceptance.
- Hosted CI is not run on this unpublished checkpoint. Existing CI definitions
  are unchanged. No push, PR, merge or deployment was performed.
- Offset pagination can shift during concurrent changes. Retry information is
  RAM-only; after process death inspect Audits before creating again. Cancellation
  never promises server rollback.
- Production rollout, server TLS, migration/grant changes and signed release
  remain separately authorized activities.

Fresh-session PowerShell launch, three hidden demo-password prompts, emulator
setup, all three role workflows, conflict reproduction and cleanup are documented
in [Android Phase 4B personal acceptance](ANDROID_PHASE4B_ACCEPTANCE.md).
