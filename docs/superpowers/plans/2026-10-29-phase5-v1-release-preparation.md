# Phase 5 Version 1.0 Development/Demo Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Independent review is required before publication. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finalize accurate portfolio documentation and traceable development/demo
candidate artifacts without new features or production deployment.

**Architecture:** Keep the existing REST-only Windows/Android clients and backend
modules. Reuse PyInstaller/Inno Setup, pinned Flutter and the five existing CI jobs;
add only release metadata/retention checks at the existing build interfaces.

**Tech Stack:** Existing Python 3.14, FastAPI/SQLAlchemy/Alembic, CustomTkinter,
openpyxl, PyInstaller/Inno Setup, Flutter/Dart/Gradle and GitHub Actions pins.

**Spec:** [Phase 5 design](../specs/2026-10-29-phase5-v1-release-preparation-design.md).
**State:** Proposed, not executed. Baseline `dfe5789`; branch
`feat/dams-v1-release-preparation`. Stop for operator approval before Task A.

## Global constraints

- Preserve exactly seven business fields; six editable and server-owned Audited By.
- No new features, architecture rewrite, dependency/toolchain upgrade or package-ID change.
- No production query/write, migration, grant, signing key, certificate or deployment.
- Never overwrite local configuration, delete installed applications, force-push,
  amend verified history or modify main directly. Use explicit paths for commits.
- Source tests only use disposable SQLite / empty `driver_audit_test_phase1` with
  `dams_test_migrate` and `dams_test_app`; export test environment explicitly.
- Serialize emulator/build/full-suite work; reuse current tools and completed
  unchanged evidence. Full final suites are required once for the frozen candidate.
- Draft PR, release/tag and any merge require appropriate later authorization.

## Review focus

1. Existing `.env` or user install: docs/setup must preserve it; test on isolated profiles.
2. Mismatched version or stale installer: candidate selection must reject it.
3. Test APK/secret define accidentally published: only ordinary main-entry debug artifact allowed.
4. Green checks on another SHA: evidence and checksums must identify exact candidate source.
5. Historical claims mistaken for current verification: dated reports and skip accounting stay explicit.

## Task A — Documentation and portfolio cleanup

**Files:** Modify `README.md`, `docs/ARCHITECTURE.md`, `mobile/README.md`,
`docs/WINDOWS_DESKTOP.md`, `docs/BACKEND_INTEGRATION_READINESS.md`,
`docs/AUTHENTICATION.md`, `docs/DATABASE_SETUP.md`, `database/README.md`,
`docs/WINDOWS_INSTALLATION.md`, `docs/ANDROID_DEVELOPMENT.md`,
`docs/WINDOWS_DESKTOP_EXPORT.md`. Create `docs/RELEASE_READINESS.md` and
`CHANGELOG.md`. Use existing `docs/images/desktop-phase3e/` and `android-phase4b/`.
No new application source in this task.

**Interface:** README is the current overview; RELEASE_READINESS is the dated
evidence/limitation index; domain guides remain the detailed command contracts.
Historical phase reports retain their original outcomes and dates.

- [ ] Correct only the confirmed stale statements listed in the design. Describe
  Windows ADMIN-only versus Android ADMIN/AUDITOR permissions and actual account
  and export availability without implying Android account administration/export.
- [ ] Make the first quick start a fictional demo; setup copies `.env.example`
  only if `.env` does not exist. Production upgrade/bootstrap/grant commands get
  explicit separately-approved prerequisites, not a quick-start execution chain.
- [ ] Add portfolio layout, genuine image captions/alt text, small REST diagram,
  stack/roles/security/evidence and concise limitations. UI UX review checks GitHub
  reading width, phone image height, color-independent labels and no invented metrics.
- [ ] Create current release index and draft changelog. Record proposed versions,
  no LICENSE decision, production revision supplied as 0001 (not re-queried),
  application head0002, prior operator acceptance and dated suite evidence.
- [ ] Validate all Markdown local paths and anchors; inspect selected external
  links and Windows/Android command sequences. Run documented demo entrypoint
  `--help`/source-contract checks without launching production or copying config.
  Do not add implementation-mirroring tests for prose edits.
- [ ] Independent documentation review; correct verified inaccuracies. Commit
  coherent docs as `docs: present completed DAMS development demo and release boundaries`.

**Acceptance:** A newcomer can distinguish installed client, source demo, API host
and production prerequisites; no current entrypoint describes implemented features
as future; no unsafe overwrite/migration is in the demo path. No full-suite rerun
for prose-only changes.

## Task B — Candidate version integrity and verification

**Files:** Modify `desktop/version.py`, `packaging/windows/version_info.txt`,
`packaging/windows/installer.iss`, `mobile/pubspec.yaml` (description/version),
`.github/workflows/backend-tests.yml` (installer path),
`.github/workflows/mobile-tests.yml` (ordinary debug artifact/provenance upload).
Tests: extend `tests/desktop/test_packaging_contract.py` and
`tests/desktop/test_installer_contract.py`; create `tests/test_release_contract.py`.
Only if needed, minimally extend `scripts/build_windows.py` to reject mixed stale
installer outputs; preserve existing `build(iscc)` interface and bundle guard.

**Interface:** `desktop.version.VERSION == '1.0.0'`; PE numeric1.0.0.0; Inno
AppVersion1.0.0 and expected installer filename. Android pubspec1.0.0+2 (confirm
no higher already distributed code); ordinary debug APK at
`mobile/build/app/outputs/flutter-apk/app-debug.apk`. API metadata remains0.2.0.

- [ ] TDD: add failing `test_candidate_versions_and_identities_are_consistent`
  asserting exact versions across desktop/PE/installer/pubspec/workflow filename,
  unchanged AppId/app identity/package and independent API version. Run the focused
  test and record expected mismatch failure before changing metadata.
- [ ] Apply only approved version/description values; update installation guide
  candidate names, not historical 0.3.0 verification records. Run focused contracts
  and record GREEN. Use a coherent version-alignment commit.
- [ ] Add failing `test_android_candidate_upload_excludes_test_configuration`
  for ordinary default main target, no `--dart-define-from-file`, no capture/demo
  credential flags or release/signing build, exact APK+manifest+checksum+notice
  upload allowlist and `contents: read` permissions. Validate structured YAML with
  correct handling of GitHub's `on` key; do not merely grep one flag.
- [ ] Extend existing Android job with finite-retention internal-debug upload,
  SHA-256 and JSON source/toolchain/version/build provenance. Inventory third-party
  notices from resolved pinned dependencies; never upload broad build/cache trees,
  debug keystores, credentials or integration-test APKs. If notice obligations
  cannot be established, hold binary publication and document the specific gap.
- [ ] TDD: `test_candidate_inventory_rejects_stale_installer` asserts exactly
  the intended 1.0.0 candidate, not a glob of old/new installers. Prefer fresh
  hosted output; if a script correction is necessary, reproduce with a temporary
  isolated output fixture before changing the builder. Do not remove user's dist
  evidence/installation to manufacture a pass. Commit only verified build changes.
- [ ] Validate full workflow YAML, pip integrity, Python compileall and Flutter
  formatting/analyzer. Run affected packaging/release contracts first. No speculative
  app refactors or dependency upgrades.
- [ ] Freeze committed source before release builds; record SHA in every manifest.
  Run full default, isolated MySQL, native Windows and Flutter suites serially;
  commands/isolation/evidence are in the checklist. Record skips, never sum overlap.
- [ ] Rebuild unsigned Windows folder/installer from frozen source using clean
  hosted runner or new isolated output. Verify bundle exclusions/licenses/hashes,
  frozen-client launch and fictional API/export. Native installer roundtrip only
  on a clean disposable runner/profile; preserve existing developer install.
- [ ] Build ordinary internal/debug Android APK without test defines; verify
  package/version/debug status, install on owned API36 emulator and check launch,
  signed-out state, settings and HTTP rejection. For authenticated acceptance of
  this exact default APK use isolated trusted test HTTPS if available. Otherwise
  disclose that its authenticated HTTPS workflow remains unverified. Separately
  run the same committed main entry with only `DAMS_DEBUG_LOOPBACK=true` against
  the disposable API for ADMIN/AUDITOR flows, lifecycle, themes/compact/large-text
  checks; this demo variant is not the default candidate and is not uploaded.
  Restore the ordinary APK afterward. Never automatically uninstall an unrelated
  package or an incompatible previously signed app to make installation succeed.
- [ ] Independent engineering/security and artifact/UI review; fix only confirmed
  finalization defects using RED/GREEN and affected regressions. Any source change
  invalidating evidence requires relevant reruns and rebuilt affected artifacts.

**Acceptance:** Exact-head candidate build and provenance, version/identity contracts,
all required local suites passed with skip explanation, native acceptance and
artifact exclusions verified. Any unavailable check is explicitly classified; no
production-ready/signed-release claim. No actual build is run during planning.

## Task C — Final review and authorized publication

**Files:** Finalize `docs/RELEASE_READINESS.md`, `CHANGELOG.md` and operator-facing
instructions before the final candidate freeze. Use ignored `artifacts/phase5-*`
for machine logs/manifests and proposed PR/release bodies. Do not commit binaries.

**Interface:** Candidate source SHA, five hosted run URLs, precise artifact paths
and SHA-256 values connect source, acceptance evidence and release notes. Public
prerelease proposal `v1.0.0-rc.1`; no stable release implied.

- [ ] Confirm operator's publication scope and owner-approved redistribution terms.
  Default handoff is one DRAFT PR; tag/release needs explicit authorization. Do not
  invent a project license or treat public Git visibility as a chosen OSS license.
- [ ] Review final cumulative diff/history/private-file scan, all seven business
  fields, identities and unchanged production/backend/Windows semantics. Review
  screenshots for fictional data; preserve all previous commits.
- [ ] Commit final source/docs checkpoint before artifact generation; record new
  exact SHA and require builds/checks on that SHA. Do not attach artifacts from
  an older build as if they came from final HEAD. Keep run-specific evidence in
  PR/release body and ignored logs to avoid circular rebuilds for report-only edits.
- [ ] If authorized, push normally and create exactly one draft Phase 5 PR against
  main; verify ancestry, conflict status, source SHA and all five hosted jobs.
  Investigate failures without weakening tests. No merge without explicit approval.
- [ ] Download/inspect final-head Windows artifact and Android internal-debug
  artifact. Verify each SHA-256 against recorded manifest and actual bytes; retain
  finite-retention CI artifacts or explicitly authorized release assets. Checksums
  detect corruption, not publisher authenticity. No production signed artifacts.
- [ ] If separately authorized, create a draft prerelease targeting an explicitly
  approved immutable SHA/tag, with RC/demo title, notices, complete folder ZIP,
  unsigned installer, internal-debug APK and manifests/checksums. Do not tag an
  unapproved/unmerged feature tip or silently publish a stable v1.0.0 release.
- [ ] Final report: implementation/commit list, exact local/hosted results, artifact
  checksums/provenance, operator acceptance, remaining limits and production hold.
  Stop; no deployment or next phase.

**Acceptance:** The [release checklist](../../PHASE5_RELEASE_CHECKLIST.md) is
complete or each demo-only exception is explicitly accepted. Full binary
redistribution is held if owner/licensing/notices or artifact evidence is unresolved.

## Planning handoff

Recommended execution: implement the three dependent checkpoints inline with an
independent review at each gate; no need for repeated full reviews of untouched
modules. This recommendation is not execution authorization. Operator review of
the design/plan and publication scope is required first.
