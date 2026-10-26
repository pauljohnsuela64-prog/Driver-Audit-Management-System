# Administrator Activity Implementation Plan

Goal: append-only, atomic account activity records with ADMIN-only history.
Architecture: dedicated admin_activity_events table (revision 0002), explicit
safe metadata, existing request transactions and account locking, no production DDL.
Spec: administrator-activity assignment attached in this session.

- [x] Model/migration: actor/target RESTRICT FKs, action/time indexes and check;
  prove populated 0001 upgrade and isolated downgrade preserve existing records.
- [x] Writer and integration: server-owned actor IDs; allowlist safe before/after
  fields; CREATE, PROFILE_UPDATE, ROLE_CHANGE, ACTIVATED, DEACTIVATED,
  PASSWORD_RESET, PASSWORD_CHANGE. No-op profile/access requests add no event.
  Combined role/status changes add two events in the same transaction.
- [x] History: GET /admin-activity, ADMIN only; bounded ID-desc pagination and
  action/actor/target filters; no edit/delete API.
- [x] Regression/permissions: all actions, rejection/no-op behavior, failure
  rollback including sessions, concurrency, safe metadata; SELECT/INSERT-only
  test runtime grant, CI provisioning and documented production rollout.
- [ ] Complete default/MySQL suites, independent diff review, credential scan,
  normal push to existing PR #4, and verify both hosted jobs at final HEAD.

Review focus: stale actors, password metadata, late event failure, migration data
preservation, and runtime privileges retained after test schema roundtrips.
Production remains at 0001 until separate explicit migration/grant authorization.
Ruling: activity tracks authenticated API account actions; offline bootstrap and
recovery remain separate operator procedures without a session-attributed actor.

Independent review found no new blockers. Existing in-flight create/profile authorization
semantics remain documented. Production was checked read-only at 0001 with its original
four application tables, empty data and no activity-table grant. Hosted results will
be recorded on the existing PR #4 after the final push.
