# Android offline production release configuration plan

Approved baseline3b5d76a. Implement the reviewed same-package/separate-device migration design. Preparation only: no production key, signing, install/uninstall, real-data migration or release.

## Checkpoint1: release configuration and inspection

- RED focused tests for exact offline release metadata/non-debug inspection, rejected debug/network/private payloads, and fail-closed signing setup.
- Gradle offlineRelease only: versionName1.0.0/code3, preserve offlineDebug code2/dev suffix and online variants. Explicit external environment signing opt-in; keystore outside repository; no fallback to debug key. Fail requested release packaging when credentials absent. Allow unsigned manifest/configuration checks only. No secret-bearing operation performed by tests.
- Keep existing debug inspector contract; add explicit release inspection with no implied signature/deployment approval. Backup source-version metadata provided by explicit nonsecret Dart define; default debug remains1.0.0+2. No logical ID/schema changes.
- GREEN focused Python tests and actual Gradle configuration/manifest/no-credential packaging rejection where cached tools permit. Commit coherent configuration.

## Checkpoint2: populated-receipt migration tests and operations documentation

- Reuse real SQLite factory/ownership seams and existing coordinator fixtures. Populate source via transfer BEFORE full encrypted backup; verify complete rows including receipt/history/profile/sequence, cancellation, normal recovery rollback, tamper rejection, restart. Add focused size/storage rejection coverage through existing seams; do not physically fill disks.
- Run relevant Flutter backup/transfer tests serially, formatting and static analysis; relevant Python release/licensing checks. No full backend rerun locally unless affected.
- Document exact future controlled keystore generation/custody, env-only secrets, pinned isolated release command, signature/public fingerprint checks, physical Android13+ migration checklist, cutover and rollback after new writes. No keys created/read/copied; do not relabel old binaries.
- Independent source/security review, correct confirmed defects, verified checkpoint commit(s).
- Publish existing feature branch and one draft PR; inspect applicable CI. Keep unmerged; no production signing or publication.
