# Phase 1 live MySQL final gate

Verified October 25, 2026 (Asia/Manila), in `C:\BHLI-Audit`.
Verdict: **PASS** for the Phase 1 engineering gate. PR #1 is ready to leave draft
and undergo final independent merge review; it has not been merged or marked ready.

## Environment and provisioning

Started from clean `feat/dams-foundation` at
`e799435685305db24a7311a6c798c232c0cb28cd`. Python 3.14.3 runs in the project
virtual environment. MySQL80 is running MySQL 8.0.46.

The administrator entered credentials in a local console with hidden password
input. An ignored local helper inspected the exact DAMS database/account names
before invoking the existing `scripts.setup_database` for both absent targets.
Four distinct random 36-byte URL-safe passwords were generated. SQLAlchemy
`URL.create` encoded all connection URLs. Administrator credentials stayed in
memory. Dedicated account credentials are in ignored `.env`, whose Windows ACL
grants access only to the executing user; no credentials are in this record.

Both `driver_audit_db` and `driver_audit_test_phase1` are provisioned, with their
respective `dams_prod_migrate`, `dams_prod_app`, `dams_test_migrate` and
`dams_test_app` localhost accounts. All four accounts connect successfully.
No MySQL credential reset or unrelated database change was performed.

Provisioning initially stopped during test downgrade after creating both schemas
and applying runtime grants. Inspection confirmed the state; the verified-empty
isolated test schema was reconciled after fixing the downgrade. Subsequent failed
test data was confined to that newly created disposable database and cleaned up.
Production was never downgraded and its four business tables remain empty.

## Defects found and fixed

1. Revision 0001 downgraded by dropping indexes individually before tables. MySQL
   requires indexes supporting foreign keys, so this interrupted the downgrade.
   It now drops tables in dependency order; their indexes and constraints are
   removed with them. Upgrade DDL and the deployed schema are unchanged. An offline
   regression protects the downgrade order, and actual MySQL roundtrips pass.
2. Constraint tests assumed CHECK violations always raise SQLAlchemy IntegrityError.
   PyMySQL reports MySQL error 3819 as OperationalError. A shared test assertion
   accepts that specific code, with regression coverage ensuring unrelated
   operational failures are rejected. Database constraints were working correctly.

New live checks cover repeatable-read snapshots, isolation from uncommitted writes,
rollback, runtime writes, denied deletes/DDL, append-only audit events and denied
cross-database access. No business fields or application features were added.

## Production schema and privileges

`alembic upgrade head`, `alembic current`, `alembic check` and
`scripts.verify_database` pass using the production migration account. Revision is
`0001`, with no pending upgrade operations or metadata differences.

Read-only inspection confirms all four tables plus Alembic's version table,
primary keys, six restrictive foreign keys, expected indexes/unique keys and
all sixteen named CHECK constraints with enforcement enabled. All business tables
use InnoDB and utf8mb4. The database default collation is utf8mb4_unicode_ci;
actual tables use MySQL's utf8mb4_0900_ai_ci because revision 0001 specifies the
charset without an explicit collation. Both are case-insensitive; no collation
change was required or applied. Sessions initialize time_zone to +00:00.

Independent SHOW GRANTS checks confirm migration accounts have only the documented
DDL/DML rights on their escaped database names, without GRANT OPTION. Runtime
accounts have SELECT/INSERT/UPDATE on users, audit_records and auth_sessions, and
SELECT/INSERT only on audit_events. Neither runtime has DELETE or DDL grants.
All four accounts are denied access to the other DAMS database. Runtime behavior
was exercised only in the isolated test database; production grants were inspected
without writing business data.

## Executed checks

| Check | Result |
| --- | --- |
| `pytest --mysql -q -rs` | 62 passed, zero skipped; model/transaction fixtures use real MySQL |
| `pytest -m mysql -q -rs` | 3 passed, 59 deselected |
| `pytest -q -rs` with local credentials loaded | 62 passed, zero skipped; default unit fixtures remain SQLite, marked live checks use MySQL |
| `pip check` | No broken requirements |
| Production Alembic upgrade/current/check and schema verification | Passed, revision 0001 |
| Required/optional fields, duplicate plates, foreign keys, CHECKs, uniqueness | Passed on MySQL |
| Inserts, updates, rollback, optimistic versioning, aware UTC timestamps | Passed on MySQL |
| Migration upgrade/downgrade/re-upgrade, schema comparison | Passed on isolated MySQL |
| Isolation, runtime permissions and cross-database denial | Passed on MySQL |
| Final database state | Production empty at 0001; isolated test database has no tables |

The seven approved fields remain Driver Name, Helper Name, Audit Date, Station,
Plate Number, Remarks and Audited By. Existing field-set assertions pass.

## Review and publication

Changes are confined to the migration downgrade, test portability, focused live
regressions and documentation. The published history and author attribution are
preserved. Local scripts, schema reports and connection configuration remain ignored.
The staged content is checked against local credentials before commit. Only a
fast-forward update to the existing feature branch and existing PR #1 is used.
Final commit/remote identifiers and GitHub checks are recorded in PR #1 and the
final report after publication. There are no engineering blockers; independent
merge approval remains the next checkpoint. No Phase 2 work is included.
