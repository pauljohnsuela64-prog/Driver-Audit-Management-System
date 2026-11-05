# Phase 6B Android Offline Foundation Implementation Plan

> For agentic workers: use Superpowers TDD and task-scoped independent review. Source of truth: the operator's approved Phase 6A review and Phase 6B authorization.

Goal: a separately installable Android development app with zero-network profile setup, SQLite CRUD/archive/history, no seeded data and durable restarts.
Architecture: preserve online entry point, screens and API contracts. Offline composition uses a typed local repository, sqflite transactions, separate UUID models and existing visual primitives.
Tech stack: retained Flutter/Dart/Android toolchain; sqflite 2.4.5 candidate, sqflite_common_ffi 2.4.5 for real host SQLite tests; pin/lock compatible resolution.

## Global constraints
- Existing main baseline d2b9ed9fca9ade40829b89e328d8681ef2d15bfc and release v1.0.0-rc.1 remain unchanged.
- Offline package com.bhli.audit.offline; label BHLI Audit Offline; separate entry lib/main_offline.dart. Original package com.bhli.audit.mobile remains buildable.
- Four tables only: app_meta, local_profile, audit_records, audit_events. No real records, seeded data, auth/account tables, imports, reports or backups.
- Six editable fields with existing limits 200/200/150/30/10000, calendar dates 1000..9999; seventh Audited By captured from local profile and immutable. Local profile is self-declared.
- UUID record/profile/event/installation identities; timestamps UTC; revision >=1; archive preserves data/history. Profile rename affects future creations only.
- Record and event commit atomically. UUID create retry compares original CREATE content even after edits; mismatch conflicts. Edits/archive check expected revision. No silent overwrite.
- Local profile changes and operations serialized through SQLite transactions. Application startup empty. No transport/session objects in offline composition; no internet permission in offline merged manifest.
- No existing app uninstall, data wipe, production operation, signing changes, push, PR or release. Development/fictional data only until later backup and release phases.

## Review focus
- Process death after commit before UI completion: same UUID retry must not duplicate; UI never describes cancellation as rollback.
- Profile rename concurrent with creation and historic name preservation.
- Failure inserting history or committing must roll back the associated record; disk/locking errors sanitized without dropping data.
- Stale form/archive and screen disposal while local operations complete.
- Empty fresh install, upgrade/newer-schema handling, separate identity and no accidental networking.

## Task 1: domain and SQLite repository
Files: mobile/lib/offline/models.dart, repository.dart, sqlite_repository.dart; mobile/test/offline/models_test.dart, repository_test.dart.
Interface (fixed for UI):
- LocalProfile(id,name); LocalAudit(id,values,auditedByName,profileId,createdAt,updatedAt,revision,archivedAt), archived getter.
- AuditValues(driverName,helperName?,auditDate,station,plateNumber,remarks?), toJson(), fromJson(), normalized exact six values, validation throws OfflineFailure.
- AuditFilter(driver='',plate='',station='',dateFrom?,dateTo?,includeArchived=false,sort='-created',page=1,pageSize=25).
- AuditPage(items,total,page,pageSize); LocalEvent(id,auditId,revision,action,actorName,createdAt,before?,after?).
- abstract OfflineRepository: profile(), saveProfile(String), list(AuditFilter), read(String), create(String id,AuditValues), update(String id,int revision,AuditValues), archive(String id,int revision), history(String id,{int page=1,int pageSize=10}), close().
- history returns List<LocalEvent> with page-size+1 fetch permitted at UI for next detection; no user/session tokens.
- SqliteOfflineRepository.open(path,{DatabaseFactory? factory}); default app path uses getDatabasesPath()/bhli_offline.db. Static UUID generator newUuid() in models; OfflineFailure(code,message), codes validation/conflict/not_found/storage/closed/schema/profile_required.
Storage: SQLite explicit FK on configure; schema version1, metadata app ID + installUUID; no on-downgrade deletion. Local integer sequence may order records while portable IDs UUID. before/after JSON includes seven fields+identity/revision/timestamps/archive. UTC strings. Native worker transaction serialization; close drains admitted operations/rejects new ones.
Steps:
- [ ] Write tests for profile/validation/UUIDs and repository outcomes before implementing; record RED.
- [ ] Implement models and store; record GREEN on real temporary SQLite via FFI.
- [ ] Cover create replay after edit, stale edits/archive, invalid filters, FK/migration/newer schema, reopen, historic name, rollback with real trigger faults and read-only/closed DB errors.
- [ ] Task-scoped independent review and coherent local checkpoint commit.

## Task 2: offline UI and navigation
Files: mobile/lib/offline/app.dart, form.dart, details.dart; mobile/lib/main_offline.dart; mobile/test/offline/ui_test.dart.
Consume Task1 interface; inject repository into OfflineApp. Reuse auditTheme, ContentWidth, StatusMessage and existing form/date/filter/history presentation. Extract focused shared visual widgets only when this prevents real duplication; preserve online tests.
Steps:
- [ ] Widget RED: empty profile setup, profile name validation, clean empty list, create/edit/archive/history, immutable original auditor, settings rename, filter/pagination, save latch/disposal and compact large-text layouts.
- [ ] Implement local-only UI: visible labels, six-field form plus read-only auditor, date picker/manual entry, actionable sanitized errors, conflict reload without resubmission, dirty cancel, no auth/connection screen. Profile settings include development/no-backup warning.
- [ ] Save success distinct from refresh failure; stable create UUID retained after uncertain storage failure. No cancellation of dispatched write; disable leaving while commit pending with clear guidance.
- [ ] Format/analyze and full Flutter tests, independent task review, checkpoint commit.

## Task 3: isolated Android packaging and native verification
Files: mobile/android/app/build.gradle.kts; Android offline flavor manifests; offline integration test; docs/ANDROID_OFFLINE.md and dependency notices as required.
Use online/offline product flavors preserving online ID/entry. Offline debug no INTERNET merged permission even when debug manifests request it; backup and device-transfer rules exclude database; retain secure window behavior. Offline versionName suffix -offline-dev, code2 for separate identity; no production signing.
Steps:
- [ ] Add failing packaging/entrypoint contract and native integration assertions.
- [ ] Configure compatible locked dependencies and two flavor builds; adapt ordinary candidate builder to explicit online flavor without changing public candidate identity.
- [ ] Native isolated emulator: record installed online package identity without uninstall; install offline package only; empty first profile, CRUD/history/reopen, airplane-mode evidence, force-stop/relaunch persistence, failed-write tests where applicable. Preserve emulator settings and record exact evidence.
- [ ] Build development offline APK after verification; inspect manifest, version, signer, bundled notices and absence of user DB/fixture values. Verify online build/contract where affected.
- [ ] Full Flutter format/analyze/tests, focused Python build/license regressions. No Windows/MySQL full-suite repetition for Android-only changes unless a finding warrants it.
- [ ] Independent whole-branch engineering/security/UX review, focused corrections, final docs/checkpoint commit and clean tree.

## Deferred milestones
6C Windows local SQLite; 6D versioned manual transfer/receipts; 6E reports, backup/restore; 6F full offline release acceptance; 6G employee-ready cleanup/packaging. Phase6B only uses fictional test data and is not employee-ready.
