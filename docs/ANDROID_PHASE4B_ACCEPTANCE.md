# Phase 4B: personal Android acceptance on Windows

This is a fictional, disposable demonstration, not production deployment. Automated
emulator results do not constitute the operator's personal acceptance. No signed
Android release is supplied. Use only the retained development emulator and the
temporary server below; never substitute production credentials or data.

## 1. Start the temporary API

Open a fresh Windows PowerShell terminal:

```powershell
Set-Location C:\BHLI-Audit
& .\.venv\Scripts\python.exe -m scripts.mobile_demo
```

Enter three **different** fictional passwords through the hidden prompts. Passwords
must be nonblank and 15–128 characters. Keep this terminal open. It prints a
loopback origin and an ephemeral port, not passwords. The normal authenticated API
creates these accounts:

| Account | Role | Purpose |
|---|---|---|
| `demo_admin` | ADMIN | Edit/archive any audit, include archived records |
| `demo_auditor` | AUDITOR A | Create records and edit their own records |
| `demo_auditor_b` | AUDITOR B | Shared active reads; cannot edit A's records |

The existing seed-only `demo_admin2` identity is retained for historical samples;
its random password is not disclosed. Use the three accounts above for acceptance.

The server owns a newly allocated temporary SQLite database with 60 active seed
audits and a separate archived example. It does not accept a database URL/path or
read production configuration. Ctrl+C stops the server and removes its database.
Restarting creates a new fixture, new port and fresh records.

## 2. Configure the retained toolchain

Open a **second** fresh PowerShell terminal and paste these process-only settings.
No execution-policy or global environment change is required:

```powershell
Set-Location C:\BHLI-Audit
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
$env:PATH = "$toolchainRoot\flutter\bin;$env:JAVA_HOME\bin;$env:ANDROID_HOME\platform-tools;$env:PATH"
adb devices -l
```

Reuse `emulator-5554` if it already represents your `bhli_api36` AVD. If that AVD
is not running, launch its visible interactive window:

```powershell
Start-Process -FilePath "$env:ANDROID_HOME\emulator\emulator.exe" -ArgumentList @(
  '-avd', 'bhli_api36', '-gpu', 'host', '-feature', '-Vulkan',
  '-no-snapshot-load', '-no-snapshot-save'
)
```

Wait until `adb devices -l` shows `device` and this returns `1`:

```powershell
adb -s emulator-5554 shell getprop sys.boot_completed
```

Do not start a second emulator, reinstall the SDK, wipe the AVD or run a large
regression suite during boot/build. The host-GPU/Vulkan workaround is documented
in [ANDROID_TOOLCHAIN.md](ANDROID_TOOLCHAIN.md).

## 3. Launch the actual application

Set the port printed by **your current** server; do not reuse a port from a report:

```powershell
$demoPort = Read-Host 'Port printed by the disposable server'
adb -s emulator-5554 reverse "tcp:$demoPort" "tcp:$demoPort"
Set-Location C:\BHLI-Audit\mobile
flutter run --debug -d emulator-5554 --dart-define=DAMS_DEBUG_LOOPBACK=true
```

In Connection setup/settings enter `http://127.0.0.1:<your-port>`, test the
connection and save. Sign in using the fictional passwords chosen in step 1.
Only an explicit debug-loopback build allows this HTTP origin. Normal remote
connections still require trusted HTTPS; do not disable certificate verification.
Keep capture relaxation off for ordinary manual privacy checks. Tokens and drafts
remain memory-only; only public connection/theme preferences are persisted.

## 4. Inspect the workflows

1. **AUDITOR A:** create an audit using the six editable fields. Try missing values
   and an invalid calendar date first. Optional helper/remarks may be empty.
   Use Unicode and a plate with leading zeros. Audited By is server-assigned.
2. Open the result and edit your own audit. Check original Audited By is unchanged.
   Cancel a dirty form: Keep editing retains it; Leave confirms abandonment.
3. Log out and sign in as **AUDITOR B**. Search for A's driver name. The active
   record and history are readable; Edit, Archive and Include archived must be
   absent. Create B's own audit and verify its Edit action is available.
4. **Conflict:** leave an edit of A's record open on Android. In a third terminal,
   start the existing Windows client against this same fictional API:

   ```powershell
   Set-Location C:\BHLI-Audit
   $demoPort = Read-Host 'Current disposable API port'
   & .\.venv\Scripts\python.exe -m desktop --api-url "http://127.0.0.1:$demoPort"
   ```

   Sign in as `demo_admin`, change the same helper/remarks field plus an unrelated
   station value and save. Save the older Android draft. Review latest/proposed
   values explicitly; verify unrelated station changes remain preserved. No save
   occurs until Save reviewed changes is chosen. Discard requires confirmation.
5. Log in as **ADMIN** on Android. Archive a fictional record after checking its
   ID, driver and plate in the confirmation. It leaves the active list; enabling
   Include archived shows active **and** archived rows. Archived details have no
   Edit/Archive controls, but ADMIN history remains available. AUDITOR access to
   archived data stays denied.
6. Expand history entries. Check Created/Updated/Archived, account IDs, local
   timezone and UTC detail, null values and previous/updated values. Audited By is
   historical attribution, not the action actor. With more than ten events use
   Next/Previous; Refresh starts at page 1. More edits can be made through the
   fictional clients to create a second page.
7. Check search, station/date filters, sort and pagination after mutations. A saved
   record may not match active filters; a refresh failure must not claim a
   confirmed save/archive failed.
8. Inspect light/dark themes, keyboard-open forms, Back, landscape, long remarks
   and enlarged text. Home/background the app and return: protected content must
   remain concealed until identity verification completes. Stop/relaunch the app:
   it must require login again, while public connection settings may remain.

For an **owned test emulator only**, these settings exercise compact/enlarged UI:

```powershell
adb -s emulator-5554 shell wm density 360  # 720 physical pixels / 2.25 = 320dp
adb -s emulator-5554 shell settings put system font_scale 2.0
# After inspection, restore the retained AVD's original settings:
adb -s emulator-5554 shell wm density reset
adb -s emulator-5554 shell settings put system font_scale 1.0
```

## 5. Stop the demonstration

Log out, close the Windows demo client, stop `flutter run`, and press Ctrl+C in
the API terminal. Remove the reverse mapping using the same current port:

```powershell
adb -s emulator-5554 reverse --remove "tcp:$demoPort"
# Only if this emulator belongs to this demonstration:
adb -s emulator-5554 emu kill
```

Physical phones, API24 execution, interactive TalkBack and trusted production
HTTPS require their own acceptance environments. They are not established by
widget tests, screenshots or this local loopback demonstration. Offset pagination
may shift under concurrent changes; refresh before comparing pages.
