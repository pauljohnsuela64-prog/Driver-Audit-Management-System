# Android audit management development

Current candidate version is `1.0.0+2`; the Version 1.0 development/demo
milestone is not a published release. See [release readiness](RELEASE_READINESS.md)
for dated evidence and limitations. [Phase 4A](ANDROID_VERIFICATION.md) and
[Phase 4B](ANDROID_PHASE4B_VERIFICATION.md) verification reports remain historical.

Phase 4B extends the foundation with authenticated creation, owner/ADMIN editing,
explicit conflict review, ADMIN archiving and archive browsing, and read-only
history. Search, filters, sorting, pagination and the seven historical business
fields remain intact. Account administration and offline storage are outside
this Android scope. See [personal acceptance instructions](ANDROID_PHASE4B_ACCEPTANCE.md).

## Tools and configuration

Use the exact versions in `mobile/toolchain.json` and the isolated process
environment in [ANDROID_TOOLCHAIN.md](ANDROID_TOOLCHAIN.md). The baseline is
Flutter 3.47.8 / Dart 3.13.7, Temurin 21.0.12.1+1, Android SDK 36 and minimum
Android API 24. Do not commit SDKs, `local.properties`, signing keys or build
outputs. `mobile/pubspec.lock` pins application dependencies.

From `mobile`, run:

```text
flutter pub get --enforce-lockfile
dart format --output=none --set-exit-if-changed lib test integration_test test_driver
flutter analyze --fatal-infos
flutter test --reporter expanded
flutter build apk --debug
```

Run resource-intensive commands serially on a 16 GB Windows development host.
The Gradle configuration limits workers to two and heap to 3 GB. Native builds
may install additional SDK platforms required by pinned plugins.

## Disposable demonstration

From the project root, using the existing Python virtual environment:

```text
.venv\Scripts\python.exe -m scripts.mobile_demo
```

Enter separate fictional passwords through the hidden prompts. The fixture
creates a temporary SQLite database and loopback API with 60 active and one
archived fictional audit. It provisions `demo_admin` and `demo_auditor` through
normal authenticated backend operations, plus `demo_auditor_b` as a second
independent AUDITOR. Choose three separate passwords. Ctrl+C removes the fixture. No
production configuration is loaded.

Start the retained `bhli_api36` development AVD as documented in the toolchain
guide. Use the exact port printed by the fixture:

```text
adb -s emulator-5554 reverse tcp:<port> tcp:<port>
flutter run -d emulator-5554 --dart-define=DAMS_DEBUG_LOOPBACK=true
```

In Connection setup, enter the printed `http://127.0.0.1:<port>` origin, test
the connection, save and sign in. Only explicit debug builds with this flag
permit loopback HTTP. Normal builds require trusted HTTPS. There is no TLS
verification bypass, LAN HTTP exception or shipping authentication bypass.
On this Windows host use the toolchain guide's verified `-gpu host -feature
-Vulkan` emulator workaround; SwiftShader crashed in the installed emulator.

Native tests take temporary credentials from an **ignored local** dart-define
JSON file, never source literals or production secrets. The keys are
`DAMS_DEBUG_LOOPBACK` (true), `DAMS_FICTIONAL_CAPTURE` (true only for deliberate
fictional screenshots), `DAMS_DEMO_ORIGIN`, `DAMS_DEMO_ADMIN_PASSWORD`,
`DAMS_DEMO_AUDITOR_PASSWORD`, and `DAMS_DEMO_AUDITOR_B_PASSWORD`. Use the same
fictional passwords as your newly started fixture, reverse its port, then run:

```text
flutter drive --driver=test_driver/acceptance_driver.dart --target=integration_test/audit_management_test.dart -d emulator-5554 --dart-define-from-file=../local/native-acceptance.json
```

This test is not included in the ordinary unit/widget test total and requires a
running Android device and isolated API. It must never target real business data.
Passwords are embedded only in that temporary integration-test APK; do not publish
it or its define file. Sanitize Gradle `dart-defines` output before sharing logs,
stop the fixture afterward, and remove the local credential file. For manual
acceptance use the ordinary `flutter run` command above, which embeds no passwords.
The older read-only `fictional_api_test.dart` also accepts these credential keys
and expects a fresh 60-record fixture.

## Session and privacy behavior

Only the API origin and appearance preference are stored locally. Bearer tokens,
passwords, identity and audit records remain in memory. Process death requires
login again. Logout clears local data even if server revocation cannot be
confirmed; the UI reports that limitation. Tokens already issued by an
unobservable interrupted login remain bounded by server expiry.

Backgrounding conceals records; foreground return validates `/auth/me` before
revealing them. Repeated resumes await the same pending verification. Native
Android windows start with `FLAG_SECURE`, backups exclude application data, and
saved Android activity state does not restore protected screens.

For genuine fictional screenshots only, an explicit debug
`DAMS_FICTIONAL_CAPTURE=true` build can relax capture protection for loopback.
That build refuses remote authentication. Native non-debuggable builds refuse
capture relaxation independently. Do not use the capture build for real data.

The existing API uses offset pagination: concurrent changes can shift results
between pages. The client validates page echoes, cancels superseded reads and
never labels retained records as a different page or filter. Refresh restarts
at page one. Failed same-query refresh may display clearly marked stale rows.

## Delivery boundaries

This phase supplies internal debug build verification, not signed distribution.
The ordinary default debug APK is distinct from the explicit loopback-demo and
integration-test builds. Default-candidate launch/settings/HTTP-rejection checks
do not establish authenticated HTTPS acceptance. That needs isolated trusted test
HTTPS or an explicit coverage limitation; loopback acceptance is not equivalent.
Never distribute a test APK with embedded fictional passwords or capture relaxation.
Production HTTPS, certificates and server deployment remain operator-managed.
Do not change production migrations, grants, Windows admission rules or backend
roles to run this client. Physical-device, TalkBack and production TLS acceptance
must be reported separately from widget tests and emulator results.
