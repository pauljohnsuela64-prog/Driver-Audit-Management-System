# MySQL setup

Use MySQL 8.0.16 or newer (enforced CHECK constraints). The local MySQL80 service
was observed running, but no DAMS account/database has been provisioned or tested.
The MySQL client is outside PATH; Python scripts use PyMySQL directly.

## Administrator provisioning

Run from `C:\BHLI Audit` after installing requirements:

```powershell
.\.venv\Scripts\python.exe -m scripts.setup_database
.\.venv\Scripts\python.exe -m scripts.setup_database --test
```

These commands require a MySQL administrator with CREATE DATABASE, CREATE USER,
GRANT and account-inspection permissions, not Windows service changes. They prompt
for administrator and fresh dedicated application/migration passwords without
echoing or saving them. Never reuse other projects' credentials. No root password
reset is performed. The scripts create only the fixed DAMS database and localhost
accounts, and refuse existing targets/accounts. MySQL DDL auto-commits: if setup
partially fails, an administrator must inspect the DAMS objects before retrying;
do not drop databases or reset accounts to bypass errors.

| Target | Database | Migration account | Runtime account |
| --- | --- | --- | --- |
| Development | driver_audit_db | dams_prod_migrate | dams_prod_app |
| Isolated tests | driver_audit_test_phase1 | dams_test_migrate | dams_test_app |

Migration rights are limited to their database. Runtime accounts initially have
no privileges. After upgrading, apply the table-specific grants in
[database/README.md](../database/README.md) as an administrator.

## Connection and migration

Copy `.env.example` to `.env`. Set `DATABASE_URL` to a `mysql+pymysql` URL containing
the dedicated migration account, its URL-encoded password, localhost, database
`driver_audit_db`, and `?charset=utf8mb4`. No real credential belongs in source,
commands committed to Git, logs, or screenshots. The runtime account is for the
future service; use the migration account only for maintenance.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m scripts.verify_database
.\.venv\Scripts\python.exe -m alembic check
```

Expected revision is `0001`. Verification connects, checks the recorded head and
compares schema metadata. Autogeneration comparison does not detect every CHECK
or server-default change; review revisions and integration behavior as well.
Downgrading to base drops the four DAMS tables and their data: use only an empty
disposable database for roundtrip tests. Never downgrade a populated deployment
without an explicitly reviewed backup/recovery plan.

## Tests

Set `DAMS_TEST_DATABASE_URL` in the current process to the dedicated test migration
account URL (same driver, `driver_audit_test_phase1`). Tests deliberately read this
variable from the environment, not `.env`. The database must already exist and
contain no tables. Tests refuse root, non-test database names and nonempty targets.
They upgrade, insert duplicate plates, compare metadata, check version, downgrade,
upgrade again and check Alembic drift. They leave only the Alembic version table;
an administrator must prepare an empty test database before another run.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs
.\.venv\Scripts\python.exe -m pytest -m mysql -q -rs
```

Without this configuration MySQL tests skip; SQLite migration and unit tests
still execute without any MySQL access. Do not point tests at the development
database or Company Operations ERP, Basic Hauling, or IT Help Desk databases.
