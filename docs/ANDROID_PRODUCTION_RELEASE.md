# Android offline production release configuration

Prepared9 November2026. This config prepares signing but does NOT generate/use a production key, produce a signed release, authorize employee deployment or migrate devices. The approved route retains `com.bhli.audit.offline`, preserves the development app on its source device and uses a SEPARATE Android13+ device for verified full-backup restoration. No source app uninstall or data clear is part of this route.

## Identities and compatibility

| Variant | Application ID | Version name / code | Signing |
|---|---|---|---|
| offlineDebug (existing accepted candidate) | com.bhli.audit.offline | 1.0.0-offline-dev / 2 | Existing development build behavior |
| offlineRelease (prepared) | com.bhli.audit.offline | 1.0.0 / 3 | Explicit external production opt-in required |
| onlineDebug | com.bhli.audit.mobile | Existing1.0.0 / 2 | Unchanged |

Release output metadata is pinned through Android Components only for offlineRelease. Do not use ABI-split publishing with this first universal-APK procedure; code progression/split allocation needs separate review. Inventory every distributed code before signing; if any higher/equal successor code exists, review the next code rather than downgrade. Future updates use this same production package/signer and strictly increasing codes. A new unrelated signer is NOT an in-place update of the installed development APK, regardless of code.

The SQLite/backup logical application ID remains `com.bhli.audit.offline`, schema2, backup payload1/android platform. Full restore preserves original profile/installation UUIDs, all records/archives/history/attribution/receipts and sequence. Transfer is not a full-profile migration and skips divergent versions; it is unencrypted/unauthenticated. No database format/migration change is introduced. MainActivity and the corruption-preserving native vendor patch retain their exact package gates. INTERNET remains removed by the offline manifest. Existing logo/UI and online app stay unchanged.

The release build requires nonsecret Dart define `BHLI_OFFLINE_SOURCE_VERSION=1.0.0+3` so backups have truthful source metadata; default debug remains1.0.0+2. Older compatible backup source-version strings remain accepted; certificate fingerprints are not backup authentication fields.

## External signing contract - not enabled in PR CI

No signing configuration exists unless `BHLI_ANDROID_ENABLE_PRODUCTION_SIGNING=1` is explicitly set by the authorized release custodian. Required child-process environment inputs:

- `BHLI_ANDROID_KEYSTORE`: existing absolute keystore file OUTSIDE the repository/worktree.
- `BHLI_ANDROID_STORE_PASSWORD`: protected store password.
- `BHLI_ANDROID_KEY_ALIAS`: approved alias; androiddebugkey is rejected.
- `BHLI_ANDROID_KEY_PASSWORD`: key password.

These inputs are never embedded in source, command arguments, Gradle properties files, build manifests, logs or APK assets. Do not echo them or run environment dumps. The keystore format is PKCS12. Use a custodian-approved local hidden-input launcher or controlled secret store to populate only the isolated build process. Gradle keeps credentials in process memory; OS paging/process inspection and erasure guarantees are outside this configuration. Use a dedicated trusted signing machine/user and terminate its single-use build processes afterward. Do not inject these variables into untrusted PR jobs, shared global shell profiles or normal debug/test jobs. Avoid --debug, --info, --scan and diagnostic dumps when secrets are present. This document contains no operational secrets.

Missing opt-in blocks direct offline release packaging BEFORE dependency resolution, and a task-graph check also covers aggregate packaging paths. Missing credentials/path, in-repository key or a debug alias fail closed. No fallback to debug signing. Manifest/metadata inspection remains key-free and does not claim a signed artifact.

## Required future key operation - separate explicit approval

1. Name organizational key owner, release custodian and recovery custodian. Agree retention/access policy and protected locations before generating anything. No key action is authorized by this PR or these instructions.
2. After authorization, use the pinned trusted JDK keytool in a local interactive terminal on the signing machine. Illustrative command (replace the path; do NOT execute during config verification):

```text
keytool -genkeypair -keystore <protected-absolute-outside-Git-path.p12> -storetype PKCS12 -alias bhli-offline-production -keyalg RSA -keysize 4096 -validity 10000
```

Enter store/key passwords only through hidden local prompts; never -storepass/-keypass arguments or chat. Follow PKCS12 tooling requirements for matching key/store password where applicable. Verify public certificate fingerprint, subject and validity with keytool, register the PUBLIC SHA256 fingerprint in the custodian release record, and confirm it differs from development certificate `eb4e62df310bcd78d5e0f3d0c9fafae1d93f0cd23e404e21734b6366d3aaee86`. Do not expose/export the private key to establish a fingerprint.
3. Under separately authorized custody, keep encrypted recoverable off-machine key backups and passphrases in separately restricted stores, minimum necessary access and a recovery drill. Losing a directly distributed app's signer can prevent future compatible updates. Neither development-key substitution nor Play upload-key reset is an assumed recovery path. No key backup/copy occurs in this assignment.

## Repeatable isolated build - ONLY after key/build approval

Use a fresh detached worktree/clean checkout of the reviewed commit in a new directory, not an old mobile/build tree or accepted dist folder. Preserve all current installations/candidates. Reuse the installed pinned Flutter3.47.8/Dart3.13.7, JDK21.0.12.1+1, SDK/Build-Tools36.0.0 and project lockfiles. Configure local SDK paths in ignored local.properties; never copy signing files into the checkout. Resolve pinned dependencies with `flutter pub get --enforce-lockfile`; capture exact resolved inventories/notices. Release-variant public Gradle dependencies may need approved network/cache preparation; offline-cache absence is not a reason to change dependency versions or skip integrity checks.

Run tests/build from that isolated checkout with production secrets absent until the actual authorized signing step. The custodian's secure launcher then sets the five environment inputs for a one-use local process. Exact Flutter command, from mobile:

```text
flutter build apk --release --flavor offline --target lib/main_offline.dart --no-pub --build-name=1.0.0 --build-number=3 --dart-define=BHLI_OFFLINE_SOURCE_VERSION=1.0.0+3
```

Invoke through the reviewed wrapper/terminal with no persistent Gradle daemon, using a dedicated process/user and reviewed bounded worker/memory settings. When invoking Gradle directly, include `--no-daemon`; for Flutter use the controlled checkout's local Gradle/user properties `org.gradle.daemon=false` before the signing invocation. Do not modify the project's tracked performance settings just to run a release. Do not let ordinary build automation sign/upload on a PR.

Flutter output is `mobile/build/app/outputs/flutter-apk/app-offline-release.apk` INSIDE the isolated checkout. Copy only the verified finished APK and approved notices/manifests into a NEW empty release-candidate output directory. Never overwrite accepted debug APKs or Windows candidates. Keep filename accurately production/release only after verification; record exact reviewed commit, lock/tool/dependency hashes, public signer fingerprint, build type, version, permissions and APK SHA256. No passwords/keystore paths/private defines in distributable manifests.

## Verify the signed candidate before any installation

Use pinned Build-Tools tools on the exact finished APK:

```text
apksigner verify --verbose --print-certs <new-candidate.apk>
aapt dump badging <new-candidate.apk>
aapt dump permissions <new-candidate.apk>
python -m scripts.offline_android --release --apk <new-candidate.apk> --badging <saved-badging.txt>
```

`apksigner` must EXIT0; compare certificate SHA256 with the independently registered production fingerprint, reject the retained DEVELOPMENT fingerprint, confirm expected v2/v3 signing and no unknown signer. The Python inspector checks package/version/non-debug/network/private-payload metadata only; its `signature_verified=false`/`production_ready=false` are intentional and cannot be promoted to signature or deployment approval. Keep public signature-verification evidence separate. Verify no INTERNET/network permissions, no debuggable flag, code3/name1.0.0, exact official assets/native SQLite/vendor/security libraries and all license/notices. Check no test fixtures/providers, user databases, keys, backups, private configurations or confidential data. Generate SHA256SUMS and retain the full dependency/notice record. New source/build bytes require their own review/test/physical acceptance; old candidate acceptance is not inherited automatically.

## Key-free configuration verification used by reviewers

Keep production opt-in unset or0. Using the cached project Gradle/JDK toolchain:

```text
gradlew :app:verifyOfflineReleaseConfiguration :app:verifyOfflineDebugConfiguration :app:verifyOnlineDebugConfiguration --offline --no-daemon --max-workers=1
```

These tasks inspect real variant output providers; no key or APK signing. A direct `:app:assembleOfflineRelease --dry-run` with opt-in unset must fail with the explicit authorization/signing message before any packaging. A dry run is not evidence that a future signed APK builds. Manifest processing and final signed build are separate gates.

## Physical Android13+ acceptance - separate fresh target, fictional first

1. Confirm source and target are physically separate devices; target has no conflicting package install. Never uninstall a conflict to proceed automatically. Record OS model/version and exact APK hash/certificate through support without publishing device IDs/user data.
2. Fictional source must include active/archived records, rename/edit history and PRIOR IMPORTS WITH POPULATED RECEIPTS. Capture all IDs/counts/digests locally. Create/readback-verify a complete encrypted external Android backup and keep two protected copies with passphrase separately; do not rely on source private files surviving uninstall.
3. Install the verified production APK on target only under approved device policy. Do not disable Play Protect/device security. Confirm no server prompt, welcome, offline create/details/history/report/transfer and no INTERNET permission. Decline data clearing or uninstall prompts.
4. Preview the source backup, verify identity/counts and create/readback-verify the REQUIRED target-current recovery backup through normal UI. Test Cancel first; target rows unchanged. Repreview, explicitly confirm complete restore; wait for a known verified outcome.
5. Verify exact profile/installation identity, registry, record UUIDs/values/timestamps/archive states, raw history/original attribution, populated receipts/sequence and no missing/duplicates. Close/reopen and force-stop/relaunch only after writes finish. Verify backup/report/transfer plus a new audit on fictional target. Test wrong passphrase/tampering and storage/provider rejection without real data or disk exhaustion.
6. Review native corruption refusal and UNKNOWN/marker recovery paths using only disposable fixtures. Host file-lock/evidence tests do not verify Android SAF durability, native lease channels or package-manager signing behavior. API24 stays excluded; do not claim every Android13+ OEM/provider tested.
7. Obtain explicit native/physical signed-candidate and real-data migration/distribution approval before using employee records. During eventual cutover freeze source writes, take final verified external backup, restore/verify target, then select ONE active writer. Retain source app/data/backup intact and inactive until separately approved retirement.

## Limits and rollback

Complete backup logical cap64MiB,20,000 audits/100,000 events and bounded schema/history references. Confirm sufficient target scratch/private/external space for incoming and required recovery backups. Oversized/invalid/storage failures must abort without partial success; do not truncate a backup or use raw DB copying. Reports/transfers have different limits and cannot replace complete recovery.

Before target acceptance/new writes, source is intact; close target and deliberately resume source. Required target recovery backup can return target to its pre-restore complete state through normal explicit restore. After target has new writes, source is STALE: freeze target, create/verify a new backup first and plan forward recovery. Do not resume the old copy or restore an older backup and silently lose later work. Old debug signer/code cannot be assumed to install on a new-signed/code3 target; downgrade/signature bypasses are forbidden. Transfer conflicts are skipped, not reconciled. Unknown outcome/corruption: preserve DB/sidecars/markers/evidence, block changes, assisted review into a verified fresh instance. Lost backup passphrase cannot be reset.

## Primary references

- https://developer.android.com/studio/publish/app-signing
- https://developer.android.com/studio/publish/versioning
- https://developer.android.com/reference/tools/gradle-api/9.0/com/android/build/api/variant/VariantOutput
- https://developer.android.com/training/data-storage/app-specific

Source-specific evidence and actual executed results are recorded separately for this PR. No production key or signed release is supplied.
