# Phase 4A Android foundation research

Research date: 2026-10-28 (Asia/Manila). Scope: design and readiness only; no SDK installation, app generation, production change, or build validation.

## Dated local observations

Read-only inspection reported by the coordinating agent on this date found Flutter, Dart, `adb`, and `sdkmanager` absent from PATH; Android Studio, the default Android SDK, and checked common Flutter directories absent. VS Code exists, but its Dart/Flutter extensions were not found. PATH Java is `1.8.0_401`; hardware is an Intel i7-13700HX with 16 GB RAM. These are bounded checks, not proof that no alternative installation exists. WMI processor virtualization flags were false while a follow-up system query reported `HypervisorPresent=true`; those results do not establish that firmware changes are needed. Emulator acceleration must be checked later using the installed emulator's `-accel-check`, as documented by [Android](https://developer.android.com/studio/run/emulator-acceleration).

## Recommended baseline and implementation pins

| Area | Evidence checked today | Phase 4A recommendation |
| --- | --- | --- |
| Flutter | Official documentation identifies Flutter 3.47; the Windows installation example names `flutter_windows_3.47.5-stable.zip`. | Use stable Flutter 3.47 family as the design baseline. At implementation, verify the official stable archive/manifest and record exact version, revision, and archive checksum. An example filename is insufficient to establish the newest patch. |
| Dart | Flutter includes the complete Dart SDK. Dart documentation reflects 3.13.3 while current Dart API pages show 3.13.7. | Use Flutter's bundled Dart 3.13 family; record the actual bundled version from `flutter --version`. Do not install an independent Dart SDK for this app. |
| Android Studio | Official stable release page names Rabbit 1, 2026.2.1. | Use that stable family, recheck its patch at implementation, and record the installed version. |
| Android deployment | Flutter 3.47 supports API 24–37; CI covers 24–36. | Design minimum API 24, subject to plugin requirements. Test the floor and a contemporary API. Support through 37 is not a direction to compile or target 37. |

Sources: [Flutter manual installation](https://docs.flutter.dev/install/manual), [Flutter support matrix](https://docs.flutter.dev/reference/supported-platforms), [Dart installation and bundling](https://dart.dev/get-dart), [Dart API version](https://api.dart.dev/dart-io/HttpClient/badCertificateCallback.html), [Android Studio stable release](https://developer.android.com/studio/releases). The attempted official Windows releases JSON URL returned 404 during this research session; no exact newest stable patch is asserted.

Install SDK Platform API 36 as the current [Flutter Android setup guide](https://docs.flutter.dev/platform-integration/android/setup) specifies, along with Build-Tools, Command-line Tools, Platform-Tools, Emulator, CMake, and side-by-side NDK. Keep generated `flutter.compileSdkVersion`, `flutter.targetSdkVersion`, and `flutter.ndkVersion` defaults initially; inspect and record their resolved values after pinning Flutter. Flutter maintains these defaults for compatibility. API 36 is the setup baseline, not evidence that every future generated default or distribution requirement remains 36. Confirm plugin and distribution requirements before finalizing numeric compile/target pins. See [Flutter Gradle configuration guidance](https://docs.flutter.dev/deployment/android#review-the-gradle-build-configuration).

Use Android Studio's bundled JBR for Studio and a JDK compatible with the selected Gradle/AGP versions for builds. Java 8 on PATH is not the proposed build JDK: AGP 8.x requires JDK 17. Record the actual JDK selected by Flutter/Gradle rather than assuming PATH selection. Keep terminal and Studio builds consistent; see [Android JDK guidance](https://developer.android.com/build/jdks). Add the VS Code Flutter extension, which also installs Dart, following [Flutter's editor instructions](https://docs.flutter.dev/tools/vs-code). Installation and license acceptance remain future implementation actions.

## Local API networking

For an Android Emulator, `10.0.2.2` aliases the development host's loopback interface; `127.0.0.1` means the emulator itself. This alias is emulator-specific and should not be assigned to physical-device configuration. See [Android network address space](https://developer.android.com/studio/run/emulator-networking-address).

For a USB-connected physical device, enable USB debugging and accept its RSA authorization prompt; verify the selected serial with `adb devices` ([Android adb guide](https://developer.android.com/tools/adb)). A proposed local setup is `adb -s <serial> reverse tcp:<port> tcp:<port>`, with the app connecting to device `localhost:<port>`; remove the mapping afterward. Reverse forwarding and serial selection are documented in the [official adb manual](https://android.googlesource.com/platform/packages/modules/adb/+/HEAD/docs/user/adb.1.md). Choose the actual API port and URL from repository configuration. Forwarding does not fix TLS hostname or certificate trust failures.

## TLS and cleartext policy

Use HTTPS with normal certificate validation. Dart rejects an untrusted certificate when `badCertificateCallback` is null; do not add accept-all callbacks or certificate bypasses ([Dart API](https://api.dart.dev/dart-io/HttpClient/badCertificateCallback.html)). Its default security context obtains Android trust roots from platform certificate stores ([SecurityContext](https://api.dart.dev/dart-io/SecurityContext/defaultContext.html)).

The default `package:http` Android client is Dart `IOClient`, not a platform-native client ([official package documentation](https://pub.dev/packages/http#choosing-an-implementation)). Android XML network security configuration governs supported native networking settings ([Android configuration](https://developer.android.com/privacy-and-security/security-config)); it must not be treated as enforcing Dart socket cleartext or trust policy. Flutter explicitly distinguishes native sockets from Dart-owned sockets in its [network-policy caveat](https://docs.flutter.dev/release/breaking-changes/network-policy-ios-android). Enforce allowed schemes/hosts in the app's client configuration and verify the chosen client on-device. Any local HTTP exception must be explicit, development-only, and excluded from release configuration; a local HTTPS endpoint needs a valid hostname and deliberately configured development trust.
