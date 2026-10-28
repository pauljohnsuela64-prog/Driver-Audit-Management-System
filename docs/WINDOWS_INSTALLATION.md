# BHLI Audit for Windows

Phase 3E produces an **unsigned test candidate** for Windows 11 x64. It packages the desktop only: a working API and database remain necessary. Production deployment, server credentials, migration 0002 and its restricted runtime grants require separate approval. This installer never performs them.

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

Use CPython 3.14.10 x64 and a separate build environment:

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install --require-hashes -r requirements-build.lock
python -m scripts.acquire_windows_tools
.\.venv-build\Scripts\python.exe -m scripts.build_windows --iscc build/tools/inno710/ISCC.exe
.\.venv\Scripts\python.exe -m scripts.packaged_demo
```

The last command requires existing developer backend dependencies, prompts for two hidden fictional ADMIN passwords and launches the actual EXE against a temporary loopback API/SQLite database with 60 fictional active audits. Accounts are `demo_admin` and `demo_admin2`; enter the chosen passwords at normal login. Closing the EXE removes the fixture database. It does not load production connection configuration, provision MySQL or add an authentication bypass. Demo passwords can be changed/reset normally without affecting real accounts.

CI also builds the folder and installer, checks bundle exclusions, records dependency licenses, source/runtime provenance and checksums, launches the actual frozen client, and tests native install/uninstall/reinstall. Its noninteractive launch smoke does not claim authenticated GUI workflow coverage. See the Phase 3E verification document for actual acceptance results and remaining release gates.

## Deployment boundaries

For two HR clients, prefer one managed always-on API/database host with trusted HTTPS and limited network access. Both desktop clients share records through that API. A combined desktop/server PC is simpler initially but sleep, shutdown and maintenance interrupt both users. This installer configures neither architecture. Server ownership, backups/restore, DNS/TLS, firewall policy, signing, administrator provisioning and production 0001-to-0002 rollout remain operator decisions.
