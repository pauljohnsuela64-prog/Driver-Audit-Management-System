# BHLI Audit for Windows

Phase 3E produces an **unsigned test candidate** for Windows 11 x64. It packages the desktop only: a working API and database remain necessary. Production deployment, server credentials, migration 0002 and its restricted runtime grants require separate approval. This installer never performs them.

Current desktop/installer metadata is `0.3.0`. Version `1.0.0` and the
`v1.0.0-rc.1` development/demo milestone are proposed, not built or released.
See [current readiness and evidence](RELEASE_READINESS.md); retain source/version
provenance when selecting a reviewed artifact rather than assuming the filename
alone identifies its contents.

## Install and connect

1. Obtain `BHLI-Audit-Setup-0.3.0-x64.exe` and checksums from the reviewed CI artifact or `dist/installer/`. Verify its source commit and SHA-256 before use. Unsigned candidates can produce Windows reputation warnings; do not disable security controls. Production distribution needs operator-approved signing.
2. Close any running BHLI Audit. Run the installer as your Windows user. It installs under `%LOCALAPPDATA%\Programs\BHLI Audit`, adds a Start Menu shortcut and offers an optional desktop shortcut. Python and VS Code are not required by the installed client.
3. At first launch, open Connection settings, enter the approved API origin, select Test connection and Save. Remote connections require a trusted HTTPS certificate and restricted networking. HTTP is accepted only for explicit loopback development. No certificate-verification bypass is provided.
4. Sign in with your individual ADMIN account. Tokens stay in memory. Use normal Create/Edit/Delete/History, My Account and Export to Excel workflows.

The only saved connection data is version and API origin in `%LOCALAPPDATA%\BHLI Audit\settings.json`. Credentials are never stored there. Change connection settings only while signed out. Explicit `--api-url` or `DAMS_DESKTOP_API_URL` overrides saved settings and locks editing for that launch; source development alone retains its loopback default. A missing frozen-client configuration never silently selects a server.

Connection errors, invalid certificates and unreachable servers require correcting the origin, network or server trust configuration. Do not copy database URLs, passwords or server `.env` files onto the client.

## Upgrade, uninstall and reinstall

Close the client before upgrading or uninstalling; the installer refuses in-use changes rather than killing work. Uninstall through Windows Installed apps or the Start Menu uninstall entry. Application-owned files and shortcuts are removed; connection settings and exported workbooks remain. Reinstall uses the same identity and settings. Delete saved settings manually only when intentionally resetting this Windows user's connection. Exports remain wherever you selected them.

For portable inspection, retain the **entire** `dist/BHLIAudit` folder; copying only the EXE does not work.

## Developer build and fictional demonstration

These are existing developer build instructions, not a requirement for demo
onboarding or approval to build a Version 1.0 candidate in Checkpoint A. Use
CPython 3.14.10 x64, prepared developer dependencies and a separate client-only
build environment. Reuse environments if present; never replace a developer's
installed application to test the installer. Use fresh isolated build outputs to
avoid mixing old installer candidates with a later build:

```powershell
if (-not (Test-Path -LiteralPath .venv-build\Scripts\python.exe)) {
    py -3.14 -m venv .venv-build
}
.\.venv-build\Scripts\python.exe -m pip install --require-hashes -r requirements-build.lock
.\.venv\Scripts\python.exe -m scripts.acquire_windows_tools
.\.venv-build\Scripts\python.exe -m scripts.build_windows --iscc build/tools/inno710/ISCC.exe
.\.venv\Scripts\python.exe -m scripts.packaged_demo
```

The last command requires existing developer backend dependencies, prompts for two hidden fictional ADMIN passwords and launches the actual EXE against a temporary loopback API/SQLite database with 60 fictional active audits. Accounts are `demo_admin` and `demo_admin2`; enter the chosen passwords at normal login. Closing the EXE removes the fixture database. It does not load production connection configuration, provision MySQL or add an authentication bypass. Demo passwords can be changed/reset normally without affecting real accounts.

CI also builds the folder and installer, checks bundle exclusions, records dependency licenses, source/runtime provenance and checksums, launches the actual frozen client, and tests native install/uninstall/reinstall. Its noninteractive launch smoke does not claim authenticated GUI workflow coverage. See the [Phase 3E verification](WINDOWS_DESKTOP_PHASE3E_VERIFICATION.md) for historical acceptance and [release readiness](RELEASE_READINESS.md) for current coverage limits, including the deliberately unperformed latest local installer roundtrip.

## Deployment boundaries

For two HR clients, prefer one managed always-on API/database host with trusted HTTPS and limited network access. Both desktop clients share records through that API. A combined desktop/server PC is simpler initially but sleep, shutdown and maintenance interrupt both users. This installer configures neither architecture. Server ownership, backups/restore, DNS/TLS, firewall policy, signing, administrator provisioning and production 0001-to-0002 rollout remain operator decisions.
