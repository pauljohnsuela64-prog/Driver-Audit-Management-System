Provision only with `python -m scripts.setup_database` (administrator credentials
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
the migration account in the future application. No passwords appear in the SQL.
Use equivalent grants against the fixed test names only if testing runtime
permissions; migration roundtrip tests require the dedicated test migration account.

The new activity-table grant must not be applied to production without explicit
approval. See [activity rollout](../docs/ADMIN_ACTIVITY.md). Local tests and CI use
the equivalent SELECT/INSERT-only grant on driver_audit_test_phase1; neither runtime
account may update/delete history or perform DDL.
