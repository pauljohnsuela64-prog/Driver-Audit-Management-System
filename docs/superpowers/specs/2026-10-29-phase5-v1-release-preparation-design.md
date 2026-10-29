# Phase 5: Version 1.0 development/demo release design

Status: **proposed; planning only, awaiting operator approval**. Reviewed on
2026-10-29 (Asia/Manila). No cleanup, version bump, build, release or deployment
is authorized by this planning commit.

## Verified starting point

- Repository: `pauljohnsuela64-prog/Driver-Audit-Management-System`.
- Main and origin/main: `dfe5789a23e9ef73bb2b87d688e782c4b8e661ed`.
- [PR #11](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/pull/11)
  merged with all seven Phase 4B design/implementation commits preserved.
- All five post-merge jobs succeeded at that SHA:
  [backend, SQLite/MySQL/Windows/installer](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40853445652),
  [Android/Flutter](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40853445787).
- Local main was fast-forwarded, then `feat/dams-v1-release-preparation` was
  created from that exact commit. Original worktree was clean; local configuration
  and historical branches were preserved.

## Intent and scope

Present the completed application accurately, make the fictional demo easy to
reproduce, and prepare traceable Version 1.0 candidate artifacts. This is a
development/portfolio milestone for DAMS / BHLI Audit, not approval to operate on
real employee data. Preserve the navy/teal clients, current architecture and all
seven audit fields. No new business features, client redesign, dependency upgrade,
database change, production signing, server deployment or automatic updater.

### Approaches considered

1. **Documentation only:** lowest change risk, but leaves inconsistent client
   versions and no durable Android candidate/checksum. Useful as the first
   checkpoint, insufficient for the requested release candidate.
2. **Documentation plus controlled development/demo RC — recommended:** retain
   current build tools and package identities, align client versions, extend
   existing artifact evidence minimally, verify final source, then request
   publication authorization. Avoid a new reporting/build framework.
3. **Production rollout/store-ready release:** requires independent deployment,
   TLS, data migration, signing, operational ownership and device acceptance.
   Excluded from Phase 5; these are not conditions to claim a limited demo RC.

Option 2 is the proposal, not an assertion of operator design approval.

## Actual functional inventory

| Module | Implemented interface and evidence | Boundary |
| --- | --- | --- |
| FastAPI backend | Factory `backend.main:create_app`, strict schemas, sanitized errors, request transactions | Backend alone connects to MySQL; `/health` is liveness, not database readiness |
| Database | SQLAlchemy models; revisions 0001 and additive 0002; five application tables plus Alembic bookkeeping | Production state supplied as 0001; not queried here; no automatic migrations |
| Authentication/accounts | Argon2id, digest-only opaque sessions, current role/status checks, ADMIN account CRUD subsets, reset/self-change, last-active-ADMIN locks | Eight-hour sessions; process-local login limiter; no email recovery |
| Audits/history | Create/read/update/soft-delete, stable-ID ownership, immutable name snapshot, atomic events, UUID idempotency and ETags | Six editable fields plus server-controlled Audited By; no restore/hard-delete |
| Account activity | Transactional activity events and ADMIN-only history API | Separate from driver-audit history; runtime append-only, not DBA tamper-proof |
| Windows client | CustomTkinter; Dashboard, Driver Audits, My Account; ADMIN-only admission; CRUD/conflict/history/account safeguards | Legacy AUDITOR accounts remain in backend; clients never connect to MySQL |
| Excel export | Genuine XLSX, applied filters/all pages, nine columns, text-safe identifiers/formula protection, bounded background work | No PDF; no-overwrite publication requires supported filesystem; offset consistency limits |
| Windows distribution | Client-only PyInstaller folder, per-user Inno Setup installer, branding, API setup, retained user settings | Unsigned candidate; API/database not bundled; entire folder required |
| Android | Flutter Material 3; ADMIN/AUDITOR browse/create, authorized edit, explicit conflicts, ADMIN archive/browse, history | No account administration, Excel/PDF export or offline sync; RAM-only sessions/drafts |
| CI and demos | Five jobs; disposable restricted MySQL; native Windows/installer checks; generated fictional demo credentials | Android hosted job does unit/widget/analyze/build, not emulator acceptance |

Historical Phase 4B final local evidence: Flutter **217 passed/0 skipped**;
default Python **549 passed/60 skipped**; isolated MySQL **553 passed/56 skipped**;
native Windows desktop **247 passed/0 skipped**. Suites overlap and must not be
summed. Default skips: 56 GUI plus four live-MySQL tests; MySQL skips: 56 GUI.
Native API 36 business/fault scenarios and ordinary-main privacy checks passed.
Operator subsequently accepted the Android/Windows conflict and session workflows.
These are baseline evidence, not fresh Phase 5 implementation results.

## Documentation and portfolio changes proposed

The implementation will change current entry points, leaving historical phase
specifications and measured verification reports intact. Add a current release
index so old counts and roadmap language are not mistaken for present status.

| File | Confirmed correction |
| --- | --- |
| `README.md` | Replace future Android/reporting and Phase 3C status; demo-first setup; guard `.env` copy; move migration commands behind separate approval; link current evidence |
| `docs/ARCHITECTURE.md` | Implemented REST clients, five-table schema including `admin_activity_events`, actual session/concurrency/export architecture |
| `mobile/README.md`, `mobile/pubspec.yaml` description | Replace read-only Phase 4A description; retain historical Phase 4A verification |
| `docs/WINDOWS_DESKTOP.md` | Replace current Phase 3C/packaging/reporting exclusions; preserve detailed lifecycle and security contracts |
| `docs/BACKEND_INTEGRATION_READINESS.md` | Mark Phase 2C measurements historical; update read-only client/token-storage/two-job/PR #4 claims with current pointers |
| `docs/AUTHENTICATION.md` | Replace future-tense ownership paragraph; distinguish actual memory-only clients from hypothetical secure persistence |
| `docs/DATABASE_SETUP.md`, `database/README.md` | Remove future-service wording; explain five tables at head; explicit 0001-to-0002 approval, no production commands in casual demo path |
| `docs/WINDOWS_INSTALLATION.md`, `docs/ANDROID_DEVELOPMENT.md` | Versioned candidate, exact source/build commands, artifact selection and safety; no new installation technology |
| `docs/WINDOWS_DESKTOP_EXPORT.md` | Packaging is implemented; PDF/analytics remain deferred; preserve export limits and consistency caveats |
| New `docs/RELEASE_READINESS.md`, `CHANGELOG.md` | Current status, reproducible verification matrix, release notes and blocked production gates |

Planning audit: 51 tracked Markdown files, 112 relative local path links checked,
zero broken paths. Anchors, external URLs, image content/privacy and command
semantics require the implementation-stage checks; a path check is not enough.
Archive docs are labeled historical through the current index, not rewritten.

### README presentation

Order: title and development/demo status; two genuine platform screenshots;
feature/role summary; stack; small REST-only architecture diagram; quick fictional
demo; detailed developer/install links; evidence/CI; security; limitations; release
and licensing status. Use short sections, native GitHub formatting and useful
image alt text. Avoid galleries of near-identical screenshots or invented badges.

Use existing fictional images, for example
`docs/images/desktop-phase3e/dashboard.png`,
`docs/images/desktop-phase3e/export-light.png`,
`docs/images/android-phase4b/phase4b-auditor-create.png` and
`docs/images/android-phase4b/phase4b-auditor-conflict.png`.
Label their source phase; do not imply screenshots show the future 1.0 build.
Inspect at GitHub reading widths; avoid forcing wide Windows and tall Android
images into an unreadable equal-width row. Captions must disclose fictional data.

## Proposed version and artifact strategy

| Surface | Actual baseline | Proposed after approval |
| --- | --- | --- |
| Portfolio milestone / future prerelease | No tags or GitHub releases found | `v1.0.0-rc.1`, title **Version 1.0 development/demo release candidate** |
| Desktop `desktop/version.py` | `0.3.0` | Numeric `1.0.0`; product still BHLI Audit |
| Windows PE metadata / installer | 0.3.0 tuples, strings and AppVersion | `1.0.0`, numeric `(1,0,0,0)`; `BHLI-Audit-Setup-1.0.0-x64.exe` |
| Android pubspec | `0.4.0+1` | `1.0.0+2`; build number must exceed any previously distributed code |
| Backend OpenAPI metadata | `0.2.0` | Retain as independently versioned API; explain this explicitly |
| Alembic | Head 0002, supplied production 0001 | Unchanged; never equate migrations with client release versions |

The RC label lives in release notes/artifact labels; numeric client metadata does
not claim production readiness. A stable `v1.0.0` tag is not part of the proposed
candidate publication. Immutable published candidates use a new RC if replaced.
This uses [SemVer prerelease naming](https://semver.org/spec/v2.0.0.html) and
[Android versionName/versionCode separation](https://developer.android.com/studio/publish/versioning).

Preserve Windows AppId `{C9470975-3249-43C2-A410-80972C956B05}`, app identity
`BHLI.Audit.Desktop`, install/settings paths and mutex; Android package/namespace
`com.bhli.audit.mobile`, minSdk 24 and saved public-origin format. Do not add a
new universal version/configuration framework for this small coordination task.

Existing Windows build records source SHA, dependency/module/license inventory,
unsigned state and SHA-256. Its installer glob can include old outputs: use a
fresh isolated output/clean hosted runner and assert exactly the expected candidate.
Never delete the developer's existing installation to obtain a clean run.

Android CI currently builds but does not upload the APK. Propose a minimal
retained internal-debug artifact containing the ordinary `lib/main.dart` APK,
SHA-256, source SHA, versions/build number/toolchain and third-party notice
inventory. Normal debug signing is not production signing. No production signing
keys are generated/exported; standard ephemeral toolchain debug signing is allowed
and its keystore is never uploaded. No integration-test APK, capture relaxation, embedded demo
passwords, fixture data or private define file is distributable. Default candidate
requires HTTPS; loopback demo is source-run with the documented explicit debug
flag, unless a separately labeled demo build is later approved.
Default-APK launch/settings/HTTP-rejection checks are distinct from loopback
functional acceptance. Authenticated acceptance of the exact default artifact
requires isolated trusted test HTTPS; if unavailable, disclose that artifact-level
gap rather than treating the source-run loopback variant as equivalent evidence.

## Security and operational classification

Read-only planning scan of 649 all-reachable-history blobs found no matches for
local credential values or the selected private-key/provider-token patterns.
Current tracked private/generated path scan found none. This is bounded evidence,
not a complete confidential-information or high-entropy audit. Retain `.env`,
toolchains, credential defines, databases, logs, EXEs/APKs and keys outside Git.
If an actual exposure is found later, stop publication and obtain remediation
approval; do not rewrite public history or strip author attribution.

**Candidate blockers until implementation:** inaccurate onboarding/docs; inconsistent
client metadata; missing final-head verification and artifact provenance/checksums;
undecided redistribution/license/branding position. No project LICENSE is tracked:
do not invent an OSS license or claim open-source. Operator confirmation of rights
and chosen distribution terms is needed before public binary redistribution;
documentation/source review can proceed without choosing a license for the owner.

**Acceptable only when explicitly disclosed for a demo RC:** unsigned Windows
candidate; Android internal/debug build; physical-device/API24/TalkBack acceptance
not performed; real production HTTPS not verified; current local installer
roundtrip held to preserve installed copy (hosted disposable roundtrip passed);
clean end-user VM/reboot/mixed-DPI coverage incomplete; offset pagination and
RAM-only uncertain-create state; process-local throttling; no automatic updates.
These are not evidence of production readiness or an accessibility certification.

**Production deployment blockers, out of scope:** backup and tested restore;
separately approved additive migration 0002 and SELECT/INSERT-only activity grants;
partial MySQL DDL failure/recovery plan; restricted runtime account verification;
ADMIN provisioning; trusted HTTPS/network/proxy/rate limits; service supervision,
maintenance and incident ownership; signing/distribution and real-device acceptance.
Migration downgrade is not a safe production rollback: preserve history and follow
the existing [activity rollout recovery](../../ADMIN_ACTIVITY.md). No production
query, credential copy, grant, certificate or server operation occurs in Phase 5.

## Approval and completion

Proposed checkpoints are A documentation/portfolio, B versioned candidate integrity
and serial regression, C final release evidence and publication. Details and exact
file/test ownership are in the [implementation plan](../plans/2026-10-29-phase5-v1-release-preparation.md);
the [readiness checklist](../../PHASE5_RELEASE_CHECKLIST.md) is the acceptance gate.

Approval requested: accept this development/demo RC scope and proposed versions;
authorize A/B execution and define whether C includes draft PR only or a draft
prerelease/tag. Binary redistribution terms require an owner decision before any
public release. No push/tag/release/PR is authorized by the current planning task.
