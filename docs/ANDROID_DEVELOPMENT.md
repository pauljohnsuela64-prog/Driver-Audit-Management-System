# Android foundation development

Phase 4A is a read-only Android client. ADMIN and AUDITOR accounts can browse
shared active driver audits, search, filter dates, sort, paginate and inspect all
seven historical business fields. Account administration, mutations, archive
access and offline storage are outside this phase.

## Tools and configuration

Use the exact versions in `mobile/toolchain.json` and the isolated process
environment in [ANDROID_TOOLCHAIN.md](ANDROID_TOOLCHAIN.md). The baseline is
Flutter 3.47.8 / Dart 3.13.7, Temurin 21.0.12.1+1, Android SDK 36 and minimum
Android API 24. Do not commit SDKs, `local.properties`, signing keys or build
outputs. `mobile/pubspec.lock` pins application dependencies.

From `mobile`, run:

```text
flutter pub get --enforce-lockfile
dart format --output=none --set-exit-if-changed lib test integration_test
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
normal authenticated backend operations. Ctrl+C removes the fixture. No
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

The native acceptance test uses the fictional passwords documented in
`mobile/integration_test/fictional_api_test.dart`. Start this disposable fixture
with those two passwords, reverse its port, then run:

```text
flutter test integration_test/fictional_api_test.dart -d emulator-5554 --dart-define=DAMS_DEBUG_LOOPBACK=true --dart-define=DAMS_DEMO_ORIGIN=http://127.0.0.1:<port>
```

This test is not included in the ordinary unit/widget test total and requires a
running Android device and isolated API. It must never target real business data.

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
Production HTTPS, certificates and server deployment remain operator-managed.
Do not change production migrations, grants, Windows admission rules or backend
roles to run this client. Physical-device, TalkBack and production TLS acceptance
must be reported separately from widget tests and emulator results.
