# Phase 6C Windows Offline Foundation Implementation Plan

> For agentic workers: use Superpowers TDD, task-scoped implementation/review and final verification. Follow the operator's implementation authorization; no publication or later phases.

Goal: separately launchable BHLI Audit Offline on Windows, with zero-network local SQLite audits and durable writes, preserving the online app/release.
Architecture: a small local repository owns domain rules and transactions; a dedicated non-daemon worker creates/uses/closes its SQLite connection on one thread. Existing CustomTkinter shell/screens/form/table/theme are reused through explicit offline presentation hooks, not fake ADMIN sessions or a REST connection-string substitution.
Tech: Python 3.14 built-in sqlite3, existing CustomTkinter/PyInstaller/Inno toolchain and dependencies only.
Spec: docs/superpowers/specs/2026-11-05-phase6c-windows-offline-foundation.md.

## Global constraints
- Baseline81d0439d96c0578cb68d8130ef91e2dfd2629533; taskbranchfeat/dams-windows-offline-foundation, local commits only.
- Preserve original online entries, API/MySQL/migrations, Android functionality, original installation/user data and v1.0.0-rc.1. No push/PR/release/tag/deployment.
- Six editable fields, immutable seventh Audited By snapshot. Match actual Phase6B normalization (including NEL/BOM/control-separator distinctions), limits and YYYY-MM-DD years1000..9999.
- Local self-declared profile UUID; original auditor names never rewritten. No password/account/server-session objects.
- App_meta/local_profile/audit_records/audit_events, schema1, UTC timestamps, UUIDv4 IDs/revisions, archive not delete; future import receipts deferred to6D.
- Runtime path LOCALAPPDATA/BHLI Audit Offline/bhli_offline.db. No live DB in binaries/build output. No reset/downgrade on failure; new/unsupported/foreign/corrupt schemas refused safely.
- Distinct entry desktop.offline, exeBHLIAuditOffline, installerGUID, installfolder/shortcuts/AppUserModelID/mutex. Development/fictional data only, no backup yet.
- Keep Excel source unchanged; offline reporting controls explicitly deferred to6E. No transfer/report/backup implementation.

## Task1 domain and repository
Files desktop/offline/{__init__,models,repository}.py; tests/desktop/offline/test_{models,repository}.py; shared cross-platform JSON contract under mobile/test/fixtures/offline_contract.json and mobile/test/offline/windows_contract_test.dart (vectors consumed by Python and Dart; no Android product behavior changes).
Interface: OfflineError(code,message); normalize_values(mapping)->dict exactly six fields; normalize_name; new_uuid; AuditValues normalized immutable six fields or normalized mapping frozen internally. LocalProfile(id,name); LocalAudit(id, six business attributes, audited_by_name,profile_id,revision,created_at,updated_at,archived_at); LocalEvent(id,audit_id,revision,action,actor_name,actor_profile_id,created_at,before,after). Immutable returned values/snapshots.
AuditFilter(driver='',plate='',station='',date_from=None,date_to=None,include_archived=False,sort='-created',page=1,page_size=25); LocalPage(items,total,page,page_size).
SqliteRepository(path,timeout=0.25) creates connection on caller thread. Methods profile(),save_profile(name),list(filter),read(id),create(id,values),update(id,expected_revision,values),archive(id,expected_revision),history(id,page=1,page_size=25)->LocalPage,close(). Every operation checks owner thread; BEGIN IMMEDIATE for mutations, atomic audit/event, parameterized SQL/allowlisted sort; no-op update creates no event; create replay compares original CREATE payload after later edits, conflicts on mismatch/archive. Read consistent transactions. Typed sanitized storage/busy/full/corrupt/schema failures; errors never reset DB. Tight compatibility checks plus FK validation. App ID is Windows-specific; logical snapshot/schema columns match Android, raw DB transfer not supported.
- [ ] RED tests first, then real SQLite GREEN: empty/create/profile rename/history, UUID replay, revisions, search wildcard escaping/paging/order/date/Unicode, reopen, migration/newer/foreign/corrupt, FK, concurrent connections/lock, rollback on event trigger/commit/full/read-only errors.
- [ ] Cross-platform fixture tests executed by both Python and Flutter.
- [ ] Independent review; coherent local commit.

## Task2 durable worker and offline presentation
Files desktop/offline/{worker,app,views,__main__,identity}.py and targeted shared desktop/screens/{shell,dashboard,audits,details,audit_history,audit_form}.py / components/table.py hooks, tests/desktop/offline/test_{worker,gui}.py.
Worker interface DatabaseWorker(factory): submit(work(repo),done(result,error),key=None,write=False)->bool; drain() UI-thread only; invalidate_reads() never cancels admitted writes; close() stops admission and appends sentinel after admitted work; stopped event, join(timeout) for tests/explicit lifecycle. Connection factory and close run worker thread. One bounded queue/non-daemon thread. No Tk calls or Tk-owned closures executed from worker; release completion callbacks only from GUI drain.
OfflineApplication owns worker, UiCollector, poll timer, profile, query, draft and dialogs. No online Application/SessionState/ApiClient construction. Bootstrap failures offer Retry without deletion. Shared shell gets explicit local profile mode; shared audit views get explicit offline read/action hooks and UUID-preserving table selection. Default online behavior unchanged.
Reuse six-field AuditForm layout; offline subclass owns validation/save/conflict/attribution behavior (no server text). Stable frozen create UUID/payload on uncertain failures; definitive validation does not freeze draft. Confirmed success separate from refresh failure; page1 refresh retains filters. Failures keep navigation/display query consistent. Dirty cancel warns; pending writes block form departure; close disables new work, shows waiting state, drains admitted writes, closes DB, destroys GUI only after worker stopped. No forced discard during a live write.
Profile setup/settings with self-declared name + permanent loss/no-backup warning. Local archive confirmation/history actor snapshot; archived read-only. Light/dark, compact/high-DPI, keyboard/focus, zero data startup.
- [ ] RED/GREEN worker thread/lifecycle tests, and native GUI tests covering complete fictional workflow, pending-close, SQLite failures, callbacks/timer cleanup, no network and original UI regressions.
- [ ] Independent source/UX review; coherent local checkpoint.

## Task3 isolated packaging and final acceptance
Files packaging/windows/{offline_entry.py,BHLIAuditOffline.spec,offline_installer.iss,offline_version_info.txt}, scripts/build_windows_offline.py; docs/WINDOWS_OFFLINE.md; tests/desktop/offline/test_packaging.py and native isolated acceptance helper.
Reuse existing client-only dependency pins/resources/notices. Separate installer GUID, LOCALAPPDATA/Programs/BHLI Audit Offline, BHLIAuditOffline.exe, shortcuts, AppUserModelID/mutex. Uninstaller never removes data folder; no existing install/uninstall is run in6C. Build only fresh isolated dist/phase6c output; inspect bundle excludes backend/auth/session/HTTP execution, secrets and DBs. Existing online build scripts/spec/installer unchanged. Frozen smoke uses a child-process LOCALAPPDATA override to a task-owned temporary empty profile, never developer settings; close uses application lifecycle, no forced termination of writes.
- [ ] Packaging RED/GREEN contracts; build unsigned development folder/ZIP/installer if retained environment supports it; inspect metadata/notices/absence of DBs, dependencies and identity, hash artifacts.
- [ ] Default Python regression, native offline+online desktop regression, Flutter cross-contract and unchanged Android regressions, pipcheck/syntax. Serialize heavyweight suites/build/native acceptance; no production DB operations.
- [ ] Native fictional source/frozen launch/restart/no-network and light/dark/compact visual evidence if supported; do not claim installation or OS-reboot acceptance without execution. No user installation changed.
- [ ] Final independent whole-branch engineering/security/UX review, focused corrections, final local commits and clean tree; stop for operator review.

## Review focus / future phases
Worker close/admission race and rollback; separate connections' stale revisions; unknown commit outcome and frozen retries; profile rename/history snapshot; DB initialization failure preserving files; GUI callbacks after destruction; offline bundle data/network/auth exclusions and path identity.6D transfer/receipts,6E reports/backups,6F install/release acceptance and6G employee cleanup remain deferred.
