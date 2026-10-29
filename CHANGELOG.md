# Changelog

This records merged functionality and planned release preparation, not production
deployments or retroactively published versions. See
[release readiness](docs/RELEASE_READINESS.md) for evidence and limitations.

## Unreleased — proposed Version 1.0 development/demo candidate

Target label: `v1.0.0-rc.1`. Strategy approved; version changes, candidate builds
and publication remain later checkpoints, not completed release work.

### Documentation — Phase 5 Checkpoint A

- Current portfolio README with genuine fictional Windows/Android screenshots,
  permission summary, REST architecture and demo-first onboarding.
- Updated current architecture, desktop/mobile and backend guides; five-table
  schema and unchanged seven business fields documented.
- Production migration/bootstrap/grants separated from disposable demonstrations;
  local configuration preserved and test-only environment guidance clarified.
- Dated release evidence index, proposed version mapping and known coverage limits;
  original historical verification reports retained unchanged.

### Still pending

- Coordinated proposed Windows1.0.0 and Android1.0.0+2 metadata; backend API0.2.0
  stays independent. Current values are Windows0.3.0 and Android0.4.0+1.
- Final-source candidate builds, manifests/notices/checksums, serial regressions,
  native artifact acceptance and hosted CI on the eventual publication HEAD.
- Explicit publication/distribution/license decisions. No Version1.0 tag, release
  or public binary distribution is created by documentation cleanup.

## Merged development baseline — through Phase 4B

Main `dfe5789a23e9ef73bb2b87d688e782c4b8e661ed`, merged 2026-10-29 through
[PR #11](https://github.com/pauljohnsuela64-prog/Driver-Audit-Management-System/pull/11).
This is a source milestone, not an assertion of a tagged release.

- **Backend:** FastAPI, MySQL schema/Alembic, Argon2id and opaque sessions,
  account administration, atomic revocation and separate account-activity history.
- **Audit integrity:** six editable fields plus server-owned historical Audited By,
  stable-ID ownership, idempotent creation, optimistic version preconditions,
  atomic create/update/archive events and ADMIN-only archived visibility.
- **Windows:** ADMIN-only Dashboard/Driver Audits/My Account, CRUD/conflict/history,
  minimal administrator tools, compact themed tables and bounded genuine XLSX export.
- **Windows packaging:** client-only PyInstaller folder and per-user Inno Setup
  unsigned candidate, first-launch API setup, shortcuts and data-preserving uninstall.
- **Android:** Flutter ADMIN/AUDITOR shared browsing/create/authorized edit, explicit
  conflict choices, ADMIN archive/browse, paginated history and memory-only privacy.
- **Verification:** five hosted jobs, disposable SQLite/MySQL/API fixtures, native
  Windows/Android acceptance and operator acceptance. Results have separate scopes;
  no unique combined test total or production-readiness certification is claimed.

No project license is declared here. Production migrations/grants, real data,
server infrastructure, production signing and deployment remain separately approved.
