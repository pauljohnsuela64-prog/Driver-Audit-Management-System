# Android release-configuration verification

Approved baseline3b5d76a3e628b420fe8327e3161da4b861a9664c. Preparation only; no production signing key generated, read, copied or used. No signed APK build, device installation/uninstallation, employee-data migration, release or deployment performed. Accepted Windows/Android artifacts remain separate and unchanged.

## Implemented scope

- Gradle selects offlineRelease packagecom.bhli.audit.offline, versionName1.0.0/code3, non-debug, while default offlineDebug remains1.0.0-offline-dev/code2 and onlineDebug remains1.0.0/code2.
- External process-environment production-signing opt-in, PKCS12 keystore outside repository, mandatory credential inputs, rejected debug alias and no debug-signing fallback. Direct and task-graph release packaging admission fail without authorization. The actual signing-enabled path is NOT executed in this assignment.
- Explicit release metadata inspection preserves debug defaults and network/private-payload rejection. It intentionally reports signature_verified=false/production_ready=false; actual apksigner/certificate acceptance remains separate.
- Backup source-version metadata uses a nonsecret compile define; release packaging requires1.0.0+3, debug defaults1.0.0+2. Logical app identity, platform, schema2, payload1, crypto and restore/transfer contracts unchanged.
- Hosted Android job gains only key-free metadata and expected unsigned-packaging rejection checks. Existing debug artifact generation/upload paths remain unchanged; no signing secrets are provided to CI.

## Executed local evidence

- Python release-inspector RED:7 failures before explicit release support; GREEN existing+new inspector/release contracts37passed. Hosted gate contract RED failed before CI step existed. Final targeted release/licensing contracts54passed.
- New real-SQLite migration/size tests2passed. Source includes a previously imported donor audit and ONE POPULATED transfer receipt before full backup. Four audits and six CREATE/UPDATE/ARCHIVE history events, local profile/installation/identity registry, all owned rows/raw history/sequence/receipt compare exactly after full encrypted restore and process-style repository reopen. Original auditor preserved despite profile rename; source stays unchanged.
- Cancellation and required recovery publication failure preserve target; normal recovery-backup restoration returns target to prior complete rows. Wrong passphrase/tampered input rejected. Transfer repeated import adds no duplicate audit/history and preserves decoded history values, not raw JSON key order.
-64MiB plaintext and corresponding envelope upper limits reject oversize buffers before crypto. Injected private evidence/destination storage failures plus existing oversized-row and actual SQLite insertion rollback paths tested; no disk was physically filled. Not exhaustive boundary/performance proof for every record/event/provider limit.
- Additional nonsecret release-provenance invocation:2migration/limit tests passed with BHLI_OFFLINE_SOURCE_VERSION=1.0.0+3; overlaps the default suite.
- Affected Flutter backup/restore/transfer/repository suite112passed in47seconds, including the two new tests. These overlap the focused run; do not add totals.
- Dart formatting checked101files with0changes. Flutter static analysis: no issues. No dart fix or unrelated rewrites.
- Real Gradle variant metadata checks passed; default debug identities/code values verified. Direct APK/bundle release requests with signing opt-in0 rejected with intended authorization message. These checks did NOT create or sign a production artifact.

## Findings and limitations

The first Gradle probe caught a Kotlin DSL java accessor shadowing java.io/java.util; corrected with explicit imports before verification. Subsequent manifest processing compiled the script but failed because release-runtime dependencies were not cached for offline mode. Metadata checks avoid runtime resolution and passed. Manifest processing is NOT reported as passed, and no dependency versions were changed/downloaded to disguise that limitation. Future authorized release environment must resolve the existing reviewed runtime graph, inspect actual merged manifest and signed payload, and record all native/dependency/notices evidence. Existing AGP/template deprecation warnings remain unchanged in scope; no toolchain upgrade.

Read-only independent review found no concrete blockers/unsafe claims, including a follow-up review of PKCS12 and key-free CI additions. It did not run tests, builds or key operations. Host file-lock/evidence adapters do not prove Android native lease, SAF durability, real storage exhaustion, production signer update compatibility or physical-device acceptance.

## Remaining gates

1. Review/merge this configuration separately; PR stays draft until operator action.
2. Explicitly authorize key owner/custody/generation and controlled signing build; production secrets must never enter PR jobs. Inventory distributed version codes before using3.
3. Build new accepted signed/non-debug APK in fresh isolated checkout/output, verify registered production certificate differs from dev signer, exact metadata/permissions/assets/native dependencies/licenses/checksums. Preserve old app/candidates.
4. Rehearse signed native restore with populated receipts on fictional Android13+ target, then operator physical acceptance and separate real-data migration/distribution approval. Keep source device intact, one active writer after accepted cutover.

Exact key operation, repeatable build/verification procedure, physical checklist, limits, rollback before/after new writes and primary references: [ANDROID_PRODUCTION_RELEASE.md](ANDROID_PRODUCTION_RELEASE.md). Hosted final-head results are recorded on the draft PR; no success claim is implied until its checks complete.
