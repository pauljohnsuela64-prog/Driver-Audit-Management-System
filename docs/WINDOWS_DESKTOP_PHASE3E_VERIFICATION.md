# Phase 3E Windows packaging verification

Reviewed on Windows 11 Home Single Language x64, build 26200, with an **unelevated user token** and actual 144-DPI / 150% scaling. Baseline: `32e4d07f5009d02a9c948682a6d0423d1c617ab4`. These are unsigned test candidates, not a production deployment.

## Delivered and reviewed

Client-only PyInstaller folder build; per-user Inno Setup installer; owned multiresolution icon and Windows branding; version metadata; Start Menu and optional desktop shortcut; signed-out first-launch API setup; strict HTTPS for remote origins; atomic, bounded endpoint settings with CLI/environment precedence; no saved bearer tokens or credentials. No backend, schema, migration, grant or audit-business-field changes.

Independent engineering and UI reviews identified and corrected: silent windowless command-line startup errors, editable connection origins during a pending health check, misleading red success feedback, and missing dialog branding. A later build inventory review corrected omission of `COPYING.txt` and collisions between vendor notices. Regression coverage verifies these corrections.

| Local verification | Actual evidence |
| --- | --- |
| Full default/SQLite suite, native GUI enabled | 562 passed, 4 skipped in 284.87 seconds; skips explicitly require live MySQL |
| Build-notice corrections and affected packaging contracts | 8 passed, including output containment; application code unchanged after full default run |
| Full isolated MySQL suite, native GUI enabled | 567 passed, 0 skipped in 577.41 seconds; the subsequent build-only containment guard also passed the focused checks above |
| Frozen client, normal authentication over trusted disposable HTTPS | First-launch health/save, ADMIN login, dashboard, create/edit/history/soft delete, original attribution, logout and exit 0 |
| Actual frozen-client Excel export | 60 active fictional records across REST pages; genuine XLSX with nine columns, no formulas and text identifier `000123` |
| Microsoft Excel compatibility | Excel 16.0 opened the generated workbook read-only, macros disabled, link updates disabled; 61 rows including header and nine columns |
| Native installer | Unicode/space install path, per-user registration, Start Menu, opt-in desktop shortcut, in-use upgrade/uninstall refusal, settings/report preservation, uninstall/reinstall and final removal passed |
| CI-style actual EXE launch | Developer Python/PATH removed; ordinary launch, native window capture and exit 0 passed |
| Dependencies / syntax / workflow | `pip check`, `compileall` and four-job workflow YAML validation passed |
| Hosted compiler-acquisition correction | Initial package job failed because inherited PowerShell 7 module paths prevented Windows PowerShell signature-module loading. The system shell now builds its own module path; checksum/publisher checks remain mandatory. Ten focused packaging/tool tests and actual signed-file verification with a contaminated parent module path passed. Final hosted outcome is recorded on the PR. |
| Hosted acceptance-harness portability/timing | The mocked signature-failure test now supplies its Windows environment explicitly on Linux. Installer acceptance waits for EXE, self-deleting uninstaller, shortcuts and registration to disappear, rather than treating early EXE removal as completion. The old predicate fails the race regression; all 11 focused packaging checks pass. A developer-installed copy detected during the resumed session was preserved by the local preflight guard; hosted clean runners verify the updated native completion check. |
| Security inventory | Changed-file secret-pattern/private-config scan clean; frozen archive excludes backend/database/migrations/tests/demo/SQLAlchemy/PyMySQL/FastAPI; no `.env`, private keys or databases in bundle |

The TLS fixture trusts an ephemeral public test CA only through its process environment. It does not install a Windows root certificate; keys and the fictional SQLite database are temporary. Tests also reject an unknown CA and a hostname mismatch. Installer acceptance temporarily creates a fictional saved setting only if none exists, verifies preservation by hash and removes only its own fixture afterward.

## Native screenshots

All data and identities are fictional. These captures show the **actual frozen executable**, not a replacement UI.

- [First-launch connection](images/desktop-phase3e/connection.png), [login](images/desktop-phase3e/login.png), [dashboard](images/desktop-phase3e/dashboard.png)
- [History](images/desktop-phase3e/history.png), [export/light](images/desktop-phase3e/export-light.png), [dark](images/desktop-phase3e/export-dark.png), [compact/collapsed sidebar](images/desktop-phase3e/compact.png)

Full local logs and JSON reports are ignored under `artifacts/phase3e-*`, `artifacts/desktop-phase3e`, `artifacts/installer-phase3e` and `artifacts/packaged-smoke`. Failed harness attempts are not acceptance evidence. Initial Save As automation failed to wait for queued native keyboard input; application export and overwrite protection behaved safely. The corrected real-input harness completed export.

## Reproduction and artifacts

See [installation and fictional demo instructions](WINDOWS_INSTALLATION.md). The build generates:

- `dist/BHLIAudit/BHLIAudit.exe` and its entire supporting folder.
- `dist/BHLIAudit/BUILD-MANIFEST.json`: source SHA, Python/tool/dependency/module inventory, unsigned status.
- `dist/BHLIAudit/THIRD_PARTY_LICENSES/`: dependency notices without basename collisions.
- `dist/installer/BHLI-Audit-Setup-0.3.0-x64.exe` and `dist/SHA256SUMS.json`.

CI preserves SQLite, disposable MySQL and native Windows regressions and adds a pinned package/installer job. It builds the exact feature SHA, launches the real EXE without developer PATH, runs installation/preservation/reinstall checks and uploads finite-retention unsigned artifacts. That launch smoke deliberately does not claim interactive authenticated workflow coverage. Actual hosted outcomes and run/artifact links are recorded on the draft PR and completion report.

## Release gates and operational limits

- A separate clean Windows 11 VM with no Python, VS Code or checkout, reboot acceptance, actual 100/125/200% DPI and mixed-monitor transitions remain **unverified**. Developer-machine PATH isolation and hosted Windows runners are useful evidence but do not replace that gate.
- Artifacts are unsigned. No signing secrets or fake trusted publisher are introduced. Operator-approved signing, SmartScreen/reputation acceptance, publisher identity and license review remain release work. Do not disable Windows security to install a candidate.
- Production MySQL remains outside this assignment. Supplied production state is revision 0001; the current backend requires separately approved backup/restore readiness, migration 0002, restricted activity-table grants, administrator provisioning and startup. No production verification query or mutation was performed here.
- The installer contains no API/database server. Shared operation needs an approved always-on API/database host, trusted HTTPS, firewall restrictions, backups and maintenance ownership.
- Build-tool setup used verified official installers. The Python 3.14.10 installer reused/upgraded the existing per-user Python 3.14 installation despite a requested private target. Existing virtual environments now use 3.14.10; packages and repository work were preserved. Regression evidence here uses that runtime.
- Existing offset-pagination export consistency limitations remain documented; packaging does not change backend semantics or introduce automatic updates.

Recommendation: suitable for draft/manual acceptance after all hosted checks pass; **hold production distribution** until the release/deployment gates above are completed.
