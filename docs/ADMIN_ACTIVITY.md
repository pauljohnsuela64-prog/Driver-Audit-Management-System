# Administrator activity history

Revision 0002 adds admin_activity_events; revision 0001 and the original four
tables are unchanged. Driver audit_events remains a separate history domain.

Authenticated API account actions write CREATE, PROFILE_UPDATE, ROLE_CHANGE,
ACTIVATED, DEACTIVATED, PASSWORD_RESET or PASSWORD_CHANGE. The event stores an
integer ID, immutable actor/target user IDs (RESTRICT foreign keys), UTC creation
time and minimal changes. Name changes never change these identity references.
Self-service changes are included even when the actor is an AUDITOR.

Changes contain only changed username, full_name, role or is_active values as
{"field":{"before":...,"after":...}}. Creation includes initial safe fields;
password events have null metadata. Passwords/hashes, sessions/tokens, URLs and
client-supplied actor IDs are never copied into events. Historical account names
are visible only to administrators through this API.

No-op profile/access requests return their existing success response without an
event. A combined role/status change emits separate ROLE_CHANGE and activation
events in one transaction. Rejected requests produce no success event. Account
mutation, session revocation and event inserts share the existing transaction;
an event/storage/commit failure rolls back all of them. Profile snapshots are
captured under the shared account guard and row lock, so concurrent updates have
accurate before/after values. Existing session and last-active-admin guards remain.

GET /admin-activity requires an active ADMIN session. It supports page 1..10000,
page_size 1..100 (default 50), an exact action filter, and positive actor_user_id
and target_user_id filters. Results order by descending event ID, with the usual
items/total/page/page_size envelope. Invalid filters return 422; missing/invalid
authentication 401; AUDITOR access 403. No create/edit/delete history API exists.

## Explicitly authorized deployment only

Production has NOT been migrated or granted new permissions by this assignment.
The new code requires revision 0002 and the following additional runtime grant;
an operator must obtain separate production approval and use the dedicated
migration/admin accounts before deploying the new code:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade 0002
.\.venv\Scripts\python.exe -m scripts.verify_database
```

```sql
GRANT SELECT, INSERT ON driver_audit_db.admin_activity_events TO 'dams_prod_app'@'localhost';
```

Verify grants without exposing credentials. No UPDATE, DELETE, DDL, grant option
or unrelated database access is required for this table. For dedicated local
tests the equivalent grant uses driver_audit_test_phase1 and dams_test_app.
CI provisions this grant on its disposable server and starts tests with an empty
schema. Fixture migration credentials handle upgrade/downgrade; API requests use
the restricted runtime account.

Migration 0002 is additive. Its downgrade drops only activity history and loses
those events; use it only in isolated tests or a separately reviewed recovery
plan. Normal deployment must preserve records, not downgrade production.

MySQL DDL auto-commits: failure after CREATE TABLE or an index can leave a partial
activity table while alembic_version still says 0001. Stop deployment and keep the
old application running; do not blindly retry, downgrade, stamp, or delete history.
Inspect alembic_version, SHOW CREATE TABLE, indexes/FKs and the event count with
authorized maintenance credentials. Back up and obtain operator approval for a
recovery plan. If the new table is demonstrably empty and no new application wrote
to it, a reviewed removal of only that partial table followed by upgrade is one
option. If it contains events, preserve/export them and reconcile missing DDL
instead; stamp 0002 only after independently confirming the exact full schema.
Re-run schema/grant checks before switching application versions. Isolated
fault-injection tests exercise the empty-table recovery without touching old data.

Offline bootstrap/recovery remain operator procedures, outside authenticated API
activity capture. Existing records are not backfilled, rejected attempts are not
security-attempt logs, and ordinary logins/logouts are not activity events. Runtime
grants enforce append-only access; database administrators/migrators can still
alter data. Retention, external tamper evidence, HTTPS, trusted networking, rate
limits, protected client storage and deployment supervision remain operator work.
