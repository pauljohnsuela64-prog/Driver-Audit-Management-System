# Version 1.0 development/demo candidate readiness checklist

Planning date: 2026-10-29, Asia/Manila. **Not a release approval or completed
Phase 5 verification report.** Checked items below are planning evidence only;
unchecked items belong to later authorized implementation.

## 1. Baseline and scope

- [x] PR #11 merged at `dfe5789a23e9ef73bb2b87d688e782c4b8e661ed`.
- [x] All five post-merge jobs passed:
  [backend/Windows](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40853445652),
  [Android](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40853445787).
- [x] Clean original worktree; main safely fast-forwarded; dedicated planning
  branch `feat/dams-v1-release-preparation`; previous history/config preserved.
- [x] Existing application, packaging, docs and fictional screenshots inventoried;
  51 Markdown files / 112 relative path links inspected, no broken path found.
- [x] Read-only scan: 649 reachable-history blobs; no local-credential or selected
  private-key/provider-token matches; no tracked private/generated paths found.
- [ ] Operator approves [design](superpowers/specs/2026-10-29-phase5-v1-release-preparation-design.md)
  and [plan](superpowers/plans/2026-10-29-phase5-v1-release-preparation.md).
- [ ] Operator defines publication scope (draft PR versus prerelease/tag) and
  confirms branding/redistribution terms before binary publication. No license is
  selected on the owner's behalf; no claim of an existing OSS license.

## 2. Documentation and presentation

- [ ] Current README/architecture/mobile descriptions match implemented behavior.
- [ ] Five-table schema and unchanged seven fields explained; no client MySQL access.
- [ ] Windows ADMIN-only and Android role/ID permissions are unambiguous.
- [ ] Demo-first commands preserve `.env`, use hidden runtime-chosen passwords,
  never trigger production migration/bootstrap, and explain the API dependency.
- [ ] Current version/release index points to dated historical phase evidence;
  no old test total or phase roadmap is presented as current release certification.
- [ ] Genuine fictional Windows/Android screenshots, readable layout and alt text;
  captions identify original phase rather than pretending to show rebuilt 1.0 UI.
- [ ] All local path/anchor and selected external links, commands and platform
  prerequisites checked. External URLs unavailable at review are recorded.
- [ ] Changelog and release notes distinguish completed functionality, demo limits
  and separately approved deployment work; no production usage/metrics invented.

## 3. Version and artifact integrity

- [ ] Proposed client1.0.0/Android+2 values explicitly approved; code exceeds any
  distributed build. API0.2.0 and Alembic0002 remain separately versioned.
- [ ] Desktop, PE tuple/string, Inno version/output and CI installer path agree.
- [ ] Windows AppId/identity/settings/mutex and Android package/minSdk unchanged.
- [ ] No new dependencies; existing locks, tool checksums, license copies and
  compiler signature verification preserved. If a security update is necessary,
  stop for scoped review rather than silently upgrading the toolchain.
- [ ] Only expected installer from fresh candidate output; stale0.3 artifacts excluded.
- [ ] Candidate builds use committed reviewed source; exact SHA recorded for each.
- [ ] Windows entire folder ZIP, installer, BUILD-MANIFEST and checksums consistent.
- [ ] Android ordinary-main debug APK inspected for expected package/version/debug
  status, no capture relaxation, test credentials, fixture or private config.
- [ ] Android source/toolchain/version manifest, checksum and dependency notices
  accompany finite-retention CI upload. No debug keystore/signing secrets uploaded.
- [ ] SHA-256 recomputed from downloaded bytes, not trusted solely from filenames.
  If folder ZIP is created, hash the ZIP as well as its component manifest.
- [ ] Third-party notice obligations reviewed for all distributed outputs; ownership
  or license uncertainty holds public binary redistribution until resolved.

## 4. Local verification, serialized

Use retained pinned tools; no emulator/Gradle build concurrently with full Python
suites. Preserve existing local configuration. Never dot-source all `.env` values
into a test process. Store logs under ignored `artifacts/phase5-*`; record command,
source SHA, runtime, counts, duration, skipped reasons and exit code. Do not print
URLs/passwords or private Dart defines.

- [ ] Python dependencies and syntax:
  `.venv\Scripts\python.exe -m pip check` and
  `.venv\Scripts\python.exe -m compileall -q backend desktop scripts migrations tests`.
- [ ] Focused release/packaging tests first:
  `.venv\Scripts\python.exe -m pytest tests/test_release_contract.py tests/desktop/test_packaging_contract.py tests/desktop/test_installer_contract.py tests/desktop/test_installer_completion.py -q -rs`.
- [ ] Full default:
  `.venv\Scripts\python.exe -m pytest -q -rs` with
  `PYTHON_DOTENV_DISABLED=1` and blank `DATABASE_URL`, `DAMS_PROD_RUNTIME_URL`,
  `DAMS_TEST_DATABASE_URL`, `DAMS_TEST_RUNTIME_URL`. No MySQL skip counted as pass.
- [ ] Dedicated MySQL: parse only two test URLs from ignored local configuration
  with `dotenv_values` and SQLAlchemy `make_url`; assert `mysql+pymysql`, local
  host, database exactly `driver_audit_test_phase1`, accounts `dams_test_migrate`
  and `dams_test_app`, same host/port/database and separate nonempty passwords.
  Export only those two values to a child with production URLs blank and dotenv
  disabled. Fixtures must reject nonempty schemas, production/root targets and
  unsafe query options. Run `.venv\Scripts\python.exe -m pytest --mysql -q -rs`.
- [ ] Verify isolated schema empty before/after; migration0001/0002 roundtrip,
  partial-DDL failure/recovery and restricted runtime grants/denials pass. No
  production query or destructive production downgrade, even to check readiness.
- [ ] Native Windows:
  `.venv\Scripts\python.exe -m pytest tests/desktop -q -rs` with
  `DAMS_DESKTOP_GUI_TESTS=1`, production/test URLs blank and dotenv disabled.
  Record skips distinctly; do not add overlapping totals into a unique count.
- [ ] From `mobile`, locked dependencies then formatting, analysis and full tests:
  `flutter pub get --enforce-lockfile`;
  `dart format --output=none --set-exit-if-changed lib test integration_test test_driver`;
  `flutter analyze --fatal-infos`; `flutter test --reporter expanded`.
- [ ] Native API36 emulator: documented fictional three-account API; create/owner
  edit/non-owner denial, admin archive/history, stale ETag/conflict choices,
  same-key uncertain retry and cancellation, logout/account switch, rapid resume
  and process death. Use [existing instructions](ANDROID_PHASE4B_ACCEPTANCE.md).
  Temporary integration-test APK may embed fictional credentials; sanitize logs,
  never publish it, restore ordinary main APK and remove exact owned config afterward.
- [ ] Ordinary candidate installed/launch/settings/default HTTP rejection checked
  separately from the main-entry loopback demo variant. Only isolated trusted test
  HTTPS can establish authenticated workflows on the exact default candidate.
  If unavailable, disclose that gap; loopback functional acceptance is not proof
  of default-candidate HTTPS authentication. Do not upload the loopback/test APK.
- [ ] Actual Windows/frozen candidate: new API configuration, ADMIN admission and
  legacy AUDITOR rejection, CRUD/history/account safeguards, Excel export/readback,
  light/dark/compact/resizing and clean shutdown. Fictional backend only.
- [ ] Installer native install/uninstall/reinstall on owned clean runner/profile;
  verify shortcuts, in-use refusal, Unicode path and settings/report preservation.
  Existing developer installation is preserved; inability to run locally is a
  disclosed local coverage limit, not a reason to bypass the ownership guard.
- [ ] Excel: nine expected columns, Unicode/text plate000123, formulas literal,
  long remarks, all matching pages and archived status, cancellation/no-clobber.
  Verify compatible spreadsheet open where available; record actual application.
- [ ] Independent engineering/security, artifact and documentation/visual reviews;
  confirmed corrections get regression coverage and relevant reruns.

## 5. Publication gate — separate authorization

- [ ] Final clean worktree; meaningful commits, no force-push/squash or history loss.
- [ ] Review all reachable candidate history and tracked paths for actual secrets,
  private config, SDKs/builds, fixture credentials and real business data. Human
  review supplements pattern checks; any exposure stops publication for remediation.
- [ ] No production/backend/schema/grant/identity/security contract changes hidden
  in cleanup. Client tokens/drafts memory-only; runtime DB grants remain restricted.
- [ ] If authorized, one draft PR against verified main; all five hosted jobs PASS
  on final candidate source. Record URLs and exact SHA, not pending success.
- [ ] Download and inspect final-head artifacts/provenance/notice inventory/hashes.
  Hosted debug build is not Android emulator acceptance; frozen smoke is not a
  complete interactive Windows workflow; hosted installer pass is distinct from
  local roundtrip. Report each evidence type separately.
- [ ] If explicitly authorized, draft prerelease/tag `v1.0.0-rc.1` targets approved
  source; title/notes clearly say development/demo, unsigned Windows and internal
  debug Android. Stable release and merge require separate explicit approval.
- [ ] Final evidence/report, installation/demo instructions and artifact hashes
  supplied. No signed Android release, deployment or automatic next phase.

## 6. Disclosed limitations versus production gates

| Item | Demo RC treatment | Real deployment treatment |
| --- | --- | --- |
| Physical device / API24 / TalkBack | Unverified; disclose, no blanket device/accessibility claim | Operator validation required for intended devices/users |
| Production HTTPS/networking | No deployed endpoint verified; use fictional loopback or isolated trusted test TLS only | Trusted certs, host/firewall/proxy/gateway policy and verification required |
| Windows installer local roundtrip | Existing install preserved; hosted disposable pass recorded separately | Clean target-machine acceptance and distribution/signing decision |
| Windows clean VM/reboot/mixed DPI | Coverage incomplete; do not equate CI with every target PC | Verify intended target environment |
| MySQL production0001/app head0002 | Never queried or changed for demo; disposable DB at app head | Approved backup+restore, migration, grant review, partial-DDL recovery, bootstrap |
| Signing/distribution/license | Candidate labeling; redistribution terms/notices resolved before public binaries | Publisher/key management, maintenance/release ownership |
| Offset pagination/RAM-only retries | Known limits and user guidance; cancellation is not rollback | Same API semantics; operational procedures account for concurrent edits |

**Final demo acceptance:** no confirmed material defect, coherent versions and
identities, safe reproducible fictional demo, current documentation, complete
relevant local/hosted evidence, genuine screenshots, traceable candidate hashes,
and explicit accepted limits. **Production readiness is not an acceptance claim.**
