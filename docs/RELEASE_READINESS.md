# Release readiness — development/demo

Updated for Phase 5 Checkpoint A, 2026-10-29 (Asia/Manila). This is the current
status index; original phase specifications and verification reports remain
historical records. **Documentation cleanup is not a new release, build, test run
or production approval.**

## Current functionality

| Area | Implemented | Boundary |
| --- | --- | --- |
| Backend | FastAPI REST, strict validation, sanitized errors, transactional services | Only the backend connects to MySQL |
| Authentication | Argon2id, opaque session tokens stored as digests, eight-hour expiry, logout/revocation | No refresh/remember-me; clients keep tokens in memory |
| Accounts | ADMIN create/list/detail/profile/access/reset; self-service password change; last-active-ADMIN locks | Minimal Windows tools expose only approved administrator actions; no Android account administration |
| Audit management | Create/read/edit/soft-delete, stable-ID ownership, immutable historical auditor, atomic history | Six editable fields plus server-owned Audited By; no restore/hard-delete |
| Concurrency | UUID frozen creation retries, exact ETags, explicit conflict choices | Cancellation is not rollback; no automatic background write retry |
| Account activity | Separate append-only runtime history and ADMIN-only API | Not a full security-attempt log or tamper-proof against DB administrators |
| Windows | ADMIN-only CustomTkinter workspace, compact tables, account tools, light/dark, all-page safe XLSX export | Dashboard, Driver Audits, My Account; no PDF/analytics module |
| Windows packaging | PyInstaller folder and per-user Inno Setup installer, API setup, shortcuts, preserved settings/reports | Unsigned test candidates; API/database not bundled |
| Android | Flutter ADMIN/AUDITOR create/browse/authorized edit/conflict/history; ADMIN archive/browse | No offline sync, Excel/PDF or signed production distribution |
| Demonstration/CI | Disposable fictional API/SQLite demos and five hosted jobs including isolated MySQL | Demos neither load production config nor authorize deployment |

The five application tables are `users`, `audit_records`, `audit_events`,
`auth_sessions` and `admin_activity_events`; `alembic_version` is separate.
The seven business fields remain Driver Name, Helper Name, Audit Date, Station,
Plate Number, Remarks and immutable server-assigned Audited By.

## Version and distribution status

| Surface | Actual current value | Proposed, not yet implemented/released |
| --- | --- | --- |
| Desktop / Windows PE / installer | `0.3.0` | `1.0.0` / numeric PE `1.0.0.0` |
| Android pubspec | `0.4.0+1` | `1.0.0+2`, subject to monotonic build-code verification |
| Backend OpenAPI version | `0.2.0` | Remains independently versioned |
| Application Alembic head | `0002` | Unchanged |
| Portfolio candidate | No Version 1.0 tag/release/artifacts created by this checkpoint | `v1.0.0-rc.1`, **development/demo release candidate** |

The RC strategy is approved for planning/progression; only documentation Task A
is currently authorized. Version values and existing package identities are
unchanged. No Version 1.0 binaries, signing keys, tag, release, PR or publication
are created in this checkpoint. Existing Windows outputs are unsigned candidates;
Android debug output uses development signing, not production release signing.

No project license has been selected in the repository. Do not claim an OSS
license or redistribute binaries on the assumption that a public repository
grants permission. Ownership/branding/distribution terms and dependency notices
require an operator decision before public binary distribution.

## Verification evidence

Baseline: PR #11 merged into main at
`dfe5789a23e9ef73bb2b87d688e782c4b8e661ed`. The following are **historical measured
results**, not reruns of Phase 5 documentation changes:

| Evidence | Result | Source |
| --- | --- | --- |
| Phase 4B Flutter | 217 passed, 0 skipped, 0 failed; formatting 51 files unchanged; analysis clean | [Checkpoint 6](ANDROID_PHASE4B_VERIFICATION.md) |
| Phase 4B default Python | 549 passed, 60 skipped, 0 failed | [Checkpoint 6](ANDROID_PHASE4B_VERIFICATION.md) |
| Phase 4B isolated MySQL | 553 passed, 56 skipped, 0 failed | [Checkpoint 6](ANDROID_PHASE4B_VERIFICATION.md) |
| Phase 4B native Windows desktop | 247 passed, 0 skipped, 0 failed | [Checkpoint 6](ANDROID_PHASE4B_VERIFICATION.md) |
| Real API/fault injection | 35 HTTP demo/mutation cases and three history serialization cases included in Python totals | [Checkpoint 6](ANDROID_PHASE4B_VERIFICATION.md) |
| Native Android | Three business scenarios on API36 plus eight ordinary-main privacy checks; compact320dp/200% text and normal360dp, themes/landscape | [Checkpoint 6](ANDROID_PHASE4B_VERIFICATION.md) |
| Actual Windows frozen client | Fictional authentication, CRUD/history/export and trusted test TLS; installer preservation/reinstall tests at Phase 3E | [Phase 3E](WINDOWS_DESKTOP_PHASE3E_VERIFICATION.md) |
| Excel compatibility | Excel16.0 opened a fictional61-record workbook; text identifiers/Unicode/formula protection verified | [Phase 3D](WINDOWS_DESKTOP_PHASE3D_VERIFICATION.md#microsoft-excel-and-native-visuals) |

These suites overlap and must not be added into a unique-test count. Default
Python skips are 56 native GUI and four live-MySQL cases. Isolated MySQL skips
are the 56 GUI cases run separately on native Windows. A skip is not a pass.
Older phase totals are retained in their original reports with their own scope.

### Post-merge hosted CI

All five jobs completed successfully on main `dfe5789`:

| Job | Result | Workflow |
| --- | --- | --- |
| Android / Flutter | PASS | [Android run 40853445787](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40853445787) |
| Python / SQLite | PASS | [Backend run 40853445652](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40853445652) |
| Disposable MySQL | PASS | [Backend run 40853445652](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40853445652) |
| Windows Desktop | PASS | [Backend run 40853445652](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40853445652) |
| Windows Packaging / Installer | PASS | [Backend run 40853445652](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40853445652) |

The Android hosted job does formatting, analysis, unit/widget tests and debug
build; it does not run emulator acceptance. The frozen Windows launch smoke
does not prove interactive authentication. Hosted clean-runner installer evidence
is separate from the deliberately unperformed latest local roundtrip.

### Operator acceptance

Before Phase 4B publication the operator reported hands-on acceptance of create/edit,
AUDITOR ownership restrictions, ADMIN archiving/archived history, concurrent
Windows/Android editing, per-field conflict choices preserving unrelated changes,
history/attribution, search/filter/sort/pagination, background privacy and
force-stop/session restart. This is distinct from automated emulator checks and
does not establish physical-device or production HTTPS acceptance.

## Development checks

No complete application regression suite was rerun for this prose-only checkpoint.
Link/anchor, Markdown, command-contract and independent documentation/accuracy
checks verify the changes. Final candidate suites belong to Checkpoint B.

Checkpoint A checks passed: 13 in-scope Markdown files, 99 relative links/anchors,
both README screenshot paths, and syntax parsing of 17 PowerShell blocks. The
embedded selective-test-configuration Python parses; it was not executed against
MySQL. CLI help for desktop/packaged-demo and source inspection of the interactive
demo entrypoints confirm the documented commands without opening prompts. An
isolated sentinel test verifies the `.env` copy guard preserves existing content.
GitHub GFM rendering and a local browser layout preview passed; no repository
publication occurred. Selected SQLAlchemy, Alembic, Argon2 and FastAPI reference
pages were reachable. Independent documentation/technical accuracy review found
no confirmed correction required. These checks do not substitute for candidate
application or target-device testing.

For a fresh default-test PowerShell terminal with installed test dependencies,
use process-local isolation; this does not modify `.env` or connect to MySQL:

```powershell
Set-Location C:\BHLI-Audit
$env:PYTHON_DOTENV_DISABLED = '1'
$env:DATABASE_URL = ''
$env:DAMS_PROD_RUNTIME_URL = ''
$env:DAMS_TEST_DATABASE_URL = ''
$env:DAMS_TEST_RUNTIME_URL = ''
$env:DAMS_DESKTOP_GUI_TESTS = '0'
& .\.venv\Scripts\python.exe -m pytest -q -rs
```

MySQL verification instead requires the empty isolated database and dedicated
migration/runtime accounts; [select only the test configuration](DATABASE_SETUP.md#loading-ignored-local-configuration-for-tests).
Never run destructive tests against `driver_audit_db` or load all server settings
into tests. Tests read their URLs from the process, not automatically from `.env`.
Native Windows checks are documented in [desktop testing](WINDOWS_DESKTOP.md#testing-and-visual-evidence);
Flutter commands and tool pins are in [Android development](ANDROID_DEVELOPMENT.md).

## Known development/demo limitations

- Physical-device, API24 and actual TalkBack acceptance remain unverified; no
  blanket Android device/accessibility certification is claimed.
- Production HTTPS/networking is not deployed/verified. The ordinary default
  Android APK rejects HTTP; source-run explicit debug-loopback acceptance does not
  establish authenticated HTTPS acceptance of the exact default artifact.
- Latest local installer roundtrip was held to preserve an existing installation.
  Historical Phase 3E and current hosted disposable roundtrips passed. Clean
  end-user Windows VM/reboot, mixed-monitor and all display-scale coverage remain
  incomplete; CI and developer PATH isolation do not replace target-PC acceptance.
- Windows candidates are unsigned; Android is internal/debug. No signed production
  distribution, automatic update service or license grant is supplied.
- Offset pagination can shift during concurrent writes, including export. RAM-only
  uncertain creation state is lost on process death; inspect before recreating.
- Cancellation cannot retract a server commit or saved export. Reports are
  unencrypted, require safe operator storage and no-clobber filesystem support.
- Login throttling is process-local, not distributed. Account activity excludes
  ordinary login/logout and rejected attempts; append-only grants do not stop DBAs.

## Production deployment is separate

Supplied production MySQL state is revision0001; application head is0002. This
documentation work does not query or change production. Real employee operation
requires separately approved backup and tested restore, additive migration0002,
restricted activity-table grants, administrator provisioning/recovery, trusted
HTTPS and firewall/proxy/gateway limits, service supervision, maintenance/incident
ownership and intended-device acceptance. MySQL DDL can partially commit; follow
[reviewed activity recovery](ADMIN_ACTIVITY.md#explicitly-authorized-deployment-only),
not a blind retry/downgrade/stamp. Neither client installer performs this work.

## Remaining Phase 5 work

**Checkpoint B:** approved version coordination and description metadata, version
contracts, exact-source build provenance/notice inventory/checksums, stale-installer
exclusion, retained ordinary Android debug artifact, final serial regressions and
artifact/native acceptance with explicit coverage limits.

**Checkpoint C:** independently reviewed final evidence and separately authorized
draft PR/publication. Tag/release, public binary redistribution and any merge need
their explicit approval; a stable Version1.0 or production release is not implied.

See the [approved plan](superpowers/plans/2026-10-29-phase5-v1-release-preparation.md),
[design](superpowers/specs/2026-10-29-phase5-v1-release-preparation-design.md),
[readiness checklist](PHASE5_RELEASE_CHECKLIST.md) and [changelog](../CHANGELOG.md).
