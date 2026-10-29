# Database schema and restricted grants

These are operator-maintenance instructions, not fictional-demo setup.
Production provisioning/migration/grants require separate explicit approval and
backup/recovery readiness. Use the [desktop](../docs/WINDOWS_DESKTOP_DEMO.md) or
[Android](../docs/ANDROID_PHASE4B_ACCEPTANCE.md) demo without touching MySQL.

Provision new approved targets only with `python -m scripts.setup_database` (administrator credentials
are prompted and never persisted). Use `--test` for the isolated test database.
The setup refuses existing databases/accounts and never resets credentials.

After migration, an administrator grants table-specific runtime access:

```sql
GRANT SELECT, INSERT, UPDATE ON driver_audit_db.users TO 'dams_prod_app'@'localhost';
GRANT SELECT, INSERT, UPDATE ON driver_audit_db.audit_records TO 'dams_prod_app'@'localhost';
GRANT SELECT, INSERT, UPDATE ON driver_audit_db.auth_sessions TO 'dams_prod_app'@'localhost';
GRANT SELECT, INSERT ON driver_audit_db.audit_events TO 'dams_prod_app'@'localhost';
-- Additional grant after explicitly approved revision 0002 deployment:
GRANT SELECT, INSERT ON driver_audit_db.admin_activity_events TO 'dams_prod_app'@'localhost';
```

The runtime account has no rights until these grants are applied, and never has
DELETE or DDL rights. Audit events are append-only for this account. Do not use
the migration account for API runtime. No passwords appear in the SQL.
Use equivalent grants against the fixed test names only if testing runtime
permissions; migration roundtrip tests require the dedicated test migration account.

The new activity-table grant must not be applied to production without explicit
approval. See [activity rollout](../docs/ADMIN_ACTIVITY.md). Local tests and CI use
the equivalent SELECT/INSERT-only grant on driver_audit_test_phase1; neither runtime
account may update/delete history or perform DDL.

Application revision0002 has five tables: `users`, `audit_records`, `audit_events`,
`auth_sessions` and `admin_activity_events`; `alembic_version` is bookkeeping.
Supplied production state remains0001 until the separately approved additive
upgrade. See [safe configuration and test isolation](../docs/DATABASE_SETUP.md)
and [current release readiness](../docs/RELEASE_READINESS.md).
