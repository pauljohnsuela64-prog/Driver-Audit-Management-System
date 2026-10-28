# Android toolchain provenance

Resolved on 2026-10-28 for Phase 4A. Tools live in ignored
`C:\BHLI-Audit\local\android-toolchain`; nothing here requires changing the
machine's Python, Java 8, global PATH, Windows features or security controls.

| Component | Verified pin |
| --- | --- |
| Flutter stable | 3.47.8, revision `737ba8f885dc774b53b442759999a312c9461e4e` |
| Bundled Dart | 3.13.7 |
| Flutter engine | `cf636b1dfb818dd6a3ff16e390e93b1a036969c8` |
| Build JDK | Eclipse Temurin 21.0.12.1+1 LTS, Windows x64 |
| Android command-line tools | 22.0, archive build 15859902 |
| Android platform / Build-Tools | API 36 / 36.0.0 |
| Android Platform-Tools | 37.0.1 |
| Android Emulator | 37.2.12.0, build 16428233 |
| API 36 emulator image | `system-images;android-36;google_apis;x86_64`, revision 7 |
| Android NDK | 28.2.13676358, r28c |
| Portable Android Studio | Rabbit 1 / 2026.2.1.8, build `AI-262.9437.185.2621.16467767` |
| Flutter template defaults | compile/target 36, Gradle 9.3.1, AGP 9.1.0, Kotlin 2.4.0, NDK 28.2.13676358 |

The [official Flutter manifest](https://storage.googleapis.com/flutter_infra_release/releases/releases_windows.json)
identifies the exact stable archive and paired Dart version. Its `base_url`
is `https://storage.googleapis.com/flutter_infra_release/releases`; the earlier
URL containing an additional `/flutter/` returns HTTP 404.

The downloaded
[`flutter_windows_3.47.8-stable.zip`](https://storage.googleapis.com/flutter_infra_release/releases/stable/windows/flutter_windows_3.47.8-stable.zip)
matched its published SHA-256 before extraction:

```text
11e19ea3409808fe3b3765ea8149640c299e58cce6eda7c9f38fc1b4a193eb6e
```

The [official Android downloads page](https://developer.android.com/studio)
published `commandlinetools-win-15859902_latest.zip` with the SHA-256 below;
the downloaded archive matched before extraction:

```text
90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a
```

The build JDK was resolved through the
[official Adoptium API](https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse)
and downloaded from the Eclipse Adoptium GitHub release. The downloaded
`OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip` matched:

```text
f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e
```

The official portable Studio archive was also verified and extracted locally;
its SHA-256 is
`6e83e7ce3e0a76c4e8e78d98eb5ef538cbc9fb386c745bda425fc0bacb9de6d4`.
Its bundled JBR reports 25.0.3, build `25.0.3+-15898627-b508.16`.
The reproducible build environment below explicitly selects Temurin 21.

For reproduction, use the exact pins and checksums above, rather than running
an SDK upgrade or selecting a floating stable version. Save and inspect the
official manifests, compare `Get-FileHash -Algorithm SHA256` before extracting,
and install Android packages with the verified SDK manager. Licenses must be
accepted by an authorized operator; this session's explicit setup authorization
covered the required official Android SDK terms. The accepted base license
record is `android-sdk-license`, hash
`24333f8a63b6825ea9c5514f83c2829b004d1fee`.
The SDK manager also lists seven unaccepted agreements for other available SDK
packages. They were not accepted merely to silence a broad doctor warning;
all packages actually requested here installed successfully.

Required package IDs installed with the official SDK manager:

```text
platform-tools
platforms;android-36
build-tools;36.0.0
emulator
ndk;28.2.13676358
system-images;android-36;google_apis;x86_64
```

Use these assignments in a dedicated PowerShell process. They affect that
process and its children only. The existing PowerShell script execution policy
is preserved; paste the commands rather than changing the policy to run a script.

```powershell
$toolchainRoot = 'C:\BHLI-Audit\local\android-toolchain'
$env:ANDROID_HOME = "$toolchainRoot\sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:ANDROID_USER_HOME = "$toolchainRoot\android-user"
$env:ANDROID_AVD_HOME = "$toolchainRoot\avd"
$env:GRADLE_USER_HOME = "$toolchainRoot\gradle"
$env:PUB_CACHE = "$toolchainRoot\pub-cache"
$env:JAVA_HOME = "$toolchainRoot\jdk-21.0.12.1+1"
$env:CI = 'true'
$env:FLUTTER_SUPPRESS_ANALYTICS = 'true'
$env:PATH = "$toolchainRoot\flutter\bin;$env:JAVA_HOME\bin;$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\cmdline-tools\latest\bin;$env:ANDROID_HOME\emulator;$env:PATH"
flutter --version --machine
flutter doctor -v
adb devices -l
& "$env:ANDROID_HOME\emulator\emulator.exe" -accel-check
```

Native `flutter --version --machine` confirmed the framework, engine and Dart
pins above. The actual acceleration diagnostic exited 0 and reported
`WHPX(10.0.26200) is installed and usable.` No Windows feature or firmware
change was needed. Initial `flutter doctor -v` recognized the isolated SDK and
Java 21; its Windows desktop Visual Studio warning is outside this Android-only
project. Doctor also warns about the seven unaccepted optional package
agreements described above.

The isolated `bhli_api36` AVD uses the Pixel 4a profile adjusted to two cores,
2 GB RAM and a 720×1560 display at 320 dpi. A headless SwiftShader launch reached
ADB status `device` as `emulator-5554`, and its log confirmed the WHPX accelerator
was operational. Simultaneous emulator boot, SDK extraction and Flutter tests
caused severe host contention on this 16 GB machine. The boot-completed property
did not return before shutdown, so full Android boot and native application
acceptance remain unverified. The owned emulator process tree was stopped and
the AVD retained; run native tests separately after unit/widget checks finish.

To start the existing development AVD from the configured process:

```powershell
$emulator = Start-Process -FilePath "$env:ANDROID_HOME\emulator\emulator.exe" -ArgumentList @('-avd', 'bhli_api36', '-port', '5554', '-no-window', '-no-audio', '-no-boot-anim', '-no-snapshot', '-gpu', 'swiftshader', '-memory', '2048', '-cores', '2') -WindowStyle Hidden -PassThru
adb -s emulator-5554 shell getprop sys.boot_completed
# Expect 1 before treating Android boot as complete.
adb -s emulator-5554 emu kill
```

This initial setup evidence did not establish native application acceptance.
Subsequent application acceptance is recorded in ANDROID_VERIFICATION.md.

### Subsequent Windows rendering diagnosis

The retained AVD later booted but the software renderer crashed before app
acceptance. Read-only minidump inspection identified exception `0xc0000005` in
`libGLESv2.dll`. Disabling Vulkan alone did not resolve it. Using `-gpu host
-feature -Vulkan` on this Windows host allowed complete boot (`sys.boot_completed=1`),
installation and native acceptance. No SDK reinstall, AVD wipe, driver change or
Windows security setting change was required. Use that rendering combination
instead of `-gpu swiftshader` for this host. Keep the emulator in a managed
terminal/session during testing and shut it down with `adb emu kill` afterward.

The first Gradle build also installed pinned-plugin requirements Android
platform 35 and CMake 3.22.1 inside the isolated SDK. The application still targets
API 36. SDK XML metadata version warnings were nonfatal; both debug builds exited
successfully. Build limits are two Gradle workers and a 3 GB heap.

Ignored raw evidence and official metadata are under
`local/android-toolchain/downloads/`; the local work ledger is
`local/phase4a-toolchain.md`. No Android Studio UI, SDK license prompt, physical
USB authorization or production certificate configuration is silently assumed.
