# MySQL setup

## Disposable GitHub Actions MySQL

The mysql-tests job starts mysql:8.0 using Docker with an ephemeral port bound only
to runner loopback. scripts/ci_mysql.py refuses non-GitHub-hosted environments,
generates separate temporary administrator/migration/runtime passwords, masks
them and both test URLs, and exports only the test URLs through GITHUB_ENV.
It creates driver_audit_test_phase1 and the two test accounts, grants migration
rights only on that exact database (escaping underscores), and applies the same
table-specific runtime grants documented in database/README.md. No runtime DELETE,
DDL or audit-event UPDATE rights are granted. A migration roundtrip establishes
the grants and leaves the schema empty before the complete pytest --mysql suite.
The container is removed even after test failure; no production secrets are used.

Docker bridge clients authenticate as dams_test_app@%; the host assertion accepts
that exact configured identity only in GitHub Actions. Local verification still
requires dams_test_app@localhost. Cross-database denial probes mysql.user, which
exists on both disposable and local servers, avoiding a production-named database.
The existing credential-free SQLite job remains unchanged. Hosted execution is
verified only after this branch is published; local Docker is not required.

Use MySQL 8.0.16 or newer (enforced CHECK constraints). Live Phase 1 verification completed on MySQL 8.0.46 with MySQL80 running.
Both dedicated databases and all four accounts are provisioned; see
[LIVE_MYSQL_REVIEW.md](LIVE_MYSQL_REVIEW.md) for the execution record.
The MySQL client is outside PATH; Python scripts use PyMySQL directly.

## Administrator provisioning

Run from `C:\BHLI-Audit` after installing requirements:

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
upgrade again and check Alembic drift. Successful runs remove their own Alembic
version table and leave the test database empty for another run. If a run fails,
inspect only the dedicated test database before cleaning up partial test state.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs
.\.venv\Scripts\python.exe -m pytest -m mysql -q -rs
# Also execute the model, relationship, UTC, version and transaction tests on MySQL:
.\.venv\Scripts\python.exe -m pytest --mysql -q -rs
```

Without this configuration MySQL tests skip; SQLite migration and unit tests
still execute without any MySQL access. Do not point tests at the development
database or any unrelated project database.

Database-wide migration grants escape underscore wildcard characters when
`partial_revokes` is disabled; when enabled, the literal database name is used.
This prevents access to similarly named databases without changing server settings.
See [MySQL GRANT semantics](https://dev.mysql.com/doc/refman/8.0/en/grant.html).

## Loading ignored local configuration for tests

Tests read their URLs from process environment variables. To load the ignored
`.env` into only the test process without exposing credentials in arguments:

```powershell
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest; raise SystemExit(pytest.main(['--mysql', '-q', '-rs']))"
```

`DAMS_TEST_RUNTIME_URL` additionally supplies the dedicated `dams_test_app` URL
for live runtime grant checks. It must target the same host/port/test database
as `DAMS_TEST_DATABASE_URL`. Keep it in the ignored, access-restricted `.env` or
process environment. The runtime test checks allowed writes/rollback, denied
DELETE and DDL, append-only events, and denial of production database access.
The live isolation test checks uncommitted-write isolation and a stable
REPEATABLE READ snapshot across two independent connections.
