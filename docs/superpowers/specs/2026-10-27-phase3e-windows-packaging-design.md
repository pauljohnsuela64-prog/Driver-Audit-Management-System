# Phase 3E: Windows packaging and deployment design

**Status:** proposed; design approval required before implementation. No installer, executable or production deployment has been created by this assignment.

## 1. Verified baseline and scope

PR #8 is merged at `32e4d07f5009d02a9c948682a6d0423d1c617ab4`. Its [post-merge run](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/actions/runs/40505012149) passed Windows, SQLite and disposable MySQL jobs. Local main was fast-forwarded to that exact SHA from a clean checkout; design branch is `feat/dams-windows-packaging`. Existing feature branches and ignored local configuration remain intact.

Deliver a Windows desktop installer for one or two HR administrators, preserving the current interface, three destinations, 38-logical-pixel tables, ADMIN-only admission, seven audit fields, ownership/history, CRUD, session safeguards and Excel export. End users need neither Python nor VS Code. The desktop continues to use authenticated REST exclusively.

Excluded: production rollout, automatic database setup/migration/grants, business features, PDF, Android, auto-update service and a bundled MySQL server. This document designs server deployment boundaries; it does not authorize deploying a backend.

## 2. Packaging recommendation and alternatives

| Option | Assessment for DAMS |
| --- | --- |
| **PyInstaller onedir + Inno Setup** | Recommended. Bundles the existing interpreter/Tk application and assets without changing the GUI stack. A single installer delivers the complete internal folder; users launch one executable. Easier resource inspection and startup diagnosis than self-extraction. |
| PyInstaller onefile | Technically supports bundled data, but adds extraction/startup and temporary-directory behavior. No useful advantage once an installer is provided; defer. |
| Nuitka standalone | Viable Python 3.14 candidate, but adds a compiler/toolchain and build maintenance without a measured need. |
| Briefcase / WiX MSI | Briefcase's documented Windows tkinter omission makes it a poor fit. WiX is an installer alternative if IT requires MSI management/repair; its build complexity and current OSMF terms need evaluation. |

Candidate build stack, checked against current official documentation: ordinary GIL-enabled **CPython 3.14.10 x64**, **PyInstaller 6.22.3**, **Inno Setup 7.1.0**. These are proposed build versions, not installed tools or proven artifact compatibility. Resolve/pin the complete tested build dependency set and hashes during implementation; retain current desktop runtime dependency pins unless a verified packaging blocker requires a narrowly reviewed correction. Build on Windows x64; no cross-compilation or free-threaded interpreter variant.

Initial supported client target: **Windows 11 x64**. Windows 10/ESU, ARM64, 32-bit Windows and Windows Server clients are not promised without explicit scope and native acceptance. The current development machine is Windows 11 x64 with Python 3.14.3; that is not a clean-machine packaged-app test.

Official evidence and trade-offs are captured in the [packaging research](../research/2026-10-27-phase3e-windows-packaging.md). In particular, CustomTkinter recommends onedir with explicit theme/font assets; packager compatibility alone does not prove a working GUI.

## 3. Distribution and installer

- Product **BHLI Audit**; executable `BHLIAudit.exe`; installer `BHLI-Audit-Setup-<version>-x64.exe`. Release tag/version metadata and publisher identity are explicit build inputs, not inferred from the backend API version.
- Per-Windows-user installation under `%LOCALAPPDATA%\Programs\BHLI Audit`, with no elevation. Stable installer application identity, Start Menu entry and optional desktop shortcut, initially unchecked. Machine-wide installation/MSI is a separate operator choice.
- Reuse the existing BHLI monogram/colors for a local multi-resolution `.ico` (16–256 px), installer branding, window/taskbar icon and stable Windows app identity. Preserve themes, typography and keyboard behavior; no rebrand or network-fetched assets.
- Bundle only desktop modules, Python runtime, Tcl/Tk, CustomTkinter JSON/fonts, Pillow extensions, XlsxWriter and required standard-library SSL/runtime files. Use explicit resource collection and inspect the bundle inventory. Exclude backend/database/migrations/scripts/tests, `.env`, local configuration, credentials, demos, screenshots, signing keys and repository contents.
- Build from a clean desktop-only environment and checked-in spec, not the developer's mixed backend virtual environment. No UPX, runtime dependency downloads, elevated application execution or client-side database driver installation.
- Installer verifies supported architecture/OS, destination permissions and available space. Upgrade/reinstall detects a running app and asks the user to close it normally; never force-kill pending mutations or exports. Test interrupted/in-use-file failures and recovery with the previous retained installer; do not claim transactional rollback without evidence.
- Uninstall removes only owned program files and shortcuts. Preserve endpoint settings by default; documented explicit settings removal is optional. Never remove user-selected Excel exports, MySQL, backend services or database records. Reinstall preserves settings; an operator can explicitly reset them. No wildcard removal of user-data folders.

## 4. Configuration and startup UX

Current code supports `--api-url`, `DAMS_DESKTOP_API_URL` and default loopback, but no persisted endpoint setting or visible windowless startup-error handling. Packaging needs these small integration changes, not new business screens.

**Proposed first run:** launch the branded login window; if the packaged client has no configured endpoint, show a compact **API connection** dialog with an operator-provided HTTPS origin, **Test connection**, **Save** and **Cancel**. Do not silently assume a local backend exists. Show the configured service host on login and provide connection settings while signed out. Endpoint changes require sign-out; tokens must never be reused or forwarded to another origin.

Precedence: explicit CLI override, existing environment override, then `%LOCALAPPDATA%\BHLI Audit\settings.json`. Preserve source-mode loopback default for developers; a fresh packaged production client asks for configuration. The settings file contains only a versioned API origin, not passwords, tokens or database URLs. Validate with existing `Config`, bound file size, write atomically, and show a recoverable error for invalid/unwritable settings. If an operator override is active, identify its source and explain that it takes precedence over saved settings.

Reuse existing `/health` for an off-thread connection check with bounded timeouts. A valid response means **API reachable**, not database/schema/grant readiness: the current health handler does not query MySQL. Login and actual authorized operations remain necessary acceptance checks. No new health endpoint or API contract is required.

No console window. Early configuration/import/Tk-startup failures need a native visible error with a stable support code; later connection/authentication errors stay in the existing UI with Retry/settings/contact-operator guidance. Do not display raw exceptions, environment variables, tokens, credentials, request/response bodies or audit data. No general diagnostic dump or new telemetry. Never auto-start a database or migrate production in response to an error.

## 5. Deployment architecture

```text
Windows HR client 1 ── trusted HTTPS ──┐
                                     ├─ TLS gateway → loopback FastAPI → local MySQL
Windows HR client 2 ── trusted HTTPS ──┘                 shared managed host
```

| Concern | A: one PC hosts desktop + API + MySQL | B: two clients + one managed API/MySQL host |
| --- | --- | --- |
| Setup | Fewest machines for one user; local API may use loopback HTTP | Same client installer on both PCs; one supervised service stack |
| Shared records | A second client still needs that PC online plus trusted HTTPS | Both clients use the same central database through the API |
| Availability | Sleep, shutdown and maintenance on the HR PC stop service | Host remains powered on; client restarts do not stop shared service |
| Security | Server credentials stay with a restricted server identity on that PC | Clients receive no DB credentials; MySQL stays local to host; only restricted HTTPS is reachable |
| Backup | PC owner must protect backup schedule and off-device copies | One centrally owned backup/restore process and protected retention |
| Maintenance | Desktop and server failures affect the same workstation | Client installer updates are separate from server/database maintenance |

**Recommendation:** B for two users: one existing IT-managed always-on host (or small managed VM) with API and MySQL co-located, plus one or two thin Windows clients. Avoid Kubernetes, per-client databases, file-share databases or direct remote MySQL. If no suitable host exists, an always-on designated HR PC is a transitional co-hosted arrangement with the same server responsibilities and availability trade-off; its selection remains an operator decision.

The desktop installer installs **only the client**. The server is a separately maintained, pinned Python environment running FastAPI under service supervision, with automatic restart, defined working directory and restricted service identity. Backend administrators may need Python/tooling on that host; HR client users do not. Select the actual Windows/Linux service wrapper and TLS gateway with IT when the host is known. For this small deployment, one API worker is the initial operational proposal; gateway rate controls are still required because the existing login limiter is process-local.

Remote clients use a stable DNS name and a trusted certificate, never plain LAN HTTP. A TLS gateway fronts a loopback-bound API; MySQL listens locally and client firewall rules expose only the approved HTTPS route to HR machines/trusted VPN. Do not open MySQL or raw Uvicorn to client networks. No certificate-verification bypass, arbitrary root-certificate import or public internet exposure by default. Test the actual packaged standard-library SSL client against the intended certificate chain; successful pip access is not proof of application TLS trust.

## 6. Production gate: distinct from packaging approval

Treat production revision **0001** as the supplied operational state; no production query was made for this design. Current backend requires **0002** and restricted activity-table permissions. Installing a desktop EXE does not solve this mismatch, and `/health` cannot certify it.

Before any separately approved production startup, operators must approve and execute a maintenance plan: identify the target host/database; take an application-consistent MySQL backup and prove restore to an isolated target; preserve existing records/accounts; perform the reviewed additive 0001→0002 migration with the dedicated migration account; independently verify schema/revision and table-specific runtime permissions; provision/recover individual ADMIN accounts with secure local prompts; then start the compatible backend and perform controlled acceptance. Backup retention, owner, recovery objectives and protected off-host storage must be chosen. Excel exports are not database backups.

Keep runtime and migration credentials separate, only on the server in service-account-accessible configuration. Runtime remains `dams_prod_app`, without DELETE/DDL and with append-only history, including SELECT/INSERT on `admin_activity_events` after approval. Do not copy the current `.env` into installers, client profiles, build outputs or CI. Production credentials never enter ordinary client or build processes.

MySQL DDL auto-commits: partial 0002 failure requires inspection and an approved recovery plan, not automatic retry, downgrade, stamp or deletion. Preserve added history and existing data. Follow [activity rollout/recovery](../../ADMIN_ACTIVITY.md) and [database setup](../../DATABASE_SETUP.md). Packaging/installer code must contain no production migration or grant action, including uninstall hooks.

## 7. Signing, supply chain and release

Prefer Authenticode-signing the application executable, installer and uninstaller with an approved publisher identity, protected key access and trusted timestamps; verify final signatures after assembly. Certificate purchase, provider access and signing credentials require operator authorization. Signing does not guarantee SmartScreen reputation; never prescribe disabling Defender/Smart App Control. Unsigned CI builds are **test artifacts**, not automatically approved production installers. Production distribution requires a trusted signed release or a separately approved managed-app trust policy.

Inno supports per-user install, shortcuts, signed uninstallers and dark setup styling. Its official license permits commercial use subject to its conditions and requests commercial licensing; have the operator confirm organizational policy/support choice. WiX's current OSMF obligations must be checked if MSI is selected. No purchase or acceptance of paid terms is authorized here.

Pin and verify build tools/downloads, retain dependency/license inventory, scan bundle contents and artifacts for secrets, and record source SHA, Python/tool versions, build command and SHA-256 checksums. Aim for a repeatable, auditable process; do not promise byte-identical signed builds. No signing secrets or privileged release steps on untrusted pull requests. Signed distribution is a protected/manual release step after review, not an automatic deployment.

## 8. Implementation checkpoints after approval

1. **Frozen desktop prototype:** TDD resource-path/entry-point/failure contracts; clean Windows desktop-only build environment; checked-in PyInstaller spec and version/icon resources; native one-directory launch. Verify Tcl/Tk/fonts/themes/Pillow/SSL/XlsxWriter inclusion, no backend imports/secrets, and no Python dependency on the test PC. Stop to diagnose incompatibility; no GUI-framework rewrite.
2. **Configuration and startup:** test precedence, bounded atomic endpoint settings, invalid configuration, off-thread health/timeouts, unknown/untrusted certificates, signed-out endpoint changes, visible early failures and normal auth/session behavior. Preserve all existing audit and export tests. Commit a coherent verified milestone.
3. **Installer:** pinned Inno build script, stable app identity, per-user standard-account install, optional shortcut, branding/version metadata, in-use-file handling, upgrade/uninstall/reinstall and settings/output preservation. Build/signature plumbing accepts no production secrets. Commit tested installer work.
4. **Native acceptance and CI:** independent engineering/UI review; full SQLite, isolated MySQL and Windows regressions; packaged-process tests against disposable fictional fixtures; clean Windows 11 x64 VM without Python, VS Code, project checkout or developer PATH. Test paths with spaces/Unicode, non-admin account, reboot, TLS trust/failure, ADMIN login/legacy AUDITOR rejection, CRUD/history, session expiry/logout, Excel export/cancel/locked/unsupported destinations, light/dark, compact/maximized and actual 100/125/150/200% DPI/mixed-monitor checks where available. Open a packaged export in Excel/compatible software and label unavailable cases unverified.
5. **Release checkpoint:** CI builds pinned Windows artifacts, performs unpacked/installed process smoke tests, inventories/checksums, and retains evidence with finite retention. GitHub-hosted Windows tests do not substitute for a clean Windows 11 acceptance VM or signing checks. Review the final artifact and licensing, publish a draft PR, verify hosted Windows/SQLite/MySQL/build jobs, and keep it unmerged unless separately instructed. No production deployment.

Planned files concentrate packaging in `packaging/windows/` (spec, launcher, icon/version resources, installer script), build dependencies in `requirements-build.txt`, minimal endpoint/startup changes in `desktop/`, and focused packaging tests/docs. Resource access belongs in a small Tk-independent module; dialogs adapt that interface without spreading frozen-path logic through feature screens. CI output remains ignored under `build/`, `dist/` and `artifacts/`.

## 9. Approval decisions

Design approval should confirm the recommended onedir/Inno, Windows 11 x64 and per-user scope; minimal first-launch endpoint settings; and separate shared-server architecture. The builder may choose internal resource paths and test helpers within these constraints.

Before production release/deployment, the operator must separately identify the service host/owner and DNS/TLS/network policy; signing/publisher and license decisions; backup/restore plan; administrator provisioning; and an approved 0002 migration/grant/startup window. If MSI, machine-wide installation, additional OS/architectures or turnkey backend provisioning is required, revise this scope first.
