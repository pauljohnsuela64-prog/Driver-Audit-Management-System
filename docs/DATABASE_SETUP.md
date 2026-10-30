# MySQL setup

For a fictional demonstration, use the [desktop](WINDOWS_DESKTOP_DEMO.md) or
[Android](ANDROID_PHASE4B_ACCEPTANCE.md) demo instead. Those own disposable
SQLite/API fixtures and require neither `.env` nor production MySQL preparation.
The production procedures below require separate explicit approval, backup/restore
readiness and a reviewed migration/grant plan. See [release boundaries](RELEASE_READINESS.md#production-deployment-is-separate).

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
The credential-free SQLite job is separate. All five jobs, including disposable
MySQL, passed after the Phase 4B merge at `dfe5789`; see
[dated hosted evidence](RELEASE_READINESS.md#verification-evidence).
Local Docker is not required to use the existing dedicated local test database.

Use MySQL 8.0.16 or newer (enforced CHECK constraints). Live Phase 1 verification completed on MySQL 8.0.46 with MySQL80 running.
Both dedicated databases and all four accounts were provisioned in that historical
execution; see
[LIVE_MYSQL_REVIEW.md](LIVE_MYSQL_REVIEW.md) for the execution record.
The MySQL client is outside PATH; Python scripts use PyMySQL directly.

## Administrator provisioning

Separately authorized database maintenance only: inspect existing targets before
using setup; do not reprovision the existing environment merely to run a demo.

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
| Production-named application database (not a test target) | driver_audit_db | dams_prod_migrate | dams_prod_app |
| Isolated tests | driver_audit_test_phase1 | dams_test_migrate | dams_test_app |

Migration rights are limited to their database. Runtime accounts initially have
no privileges. After upgrading, apply the table-specific grants in
[database/README.md](../database/README.md) as an administrator.

## Connection and migration

Preserve any existing `.env`. If approved maintenance needs a new local config,
copy only when absent:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

Set `DATABASE_URL` to a `mysql+pymysql` URL containing
the dedicated migration account, its URL-encoded password, localhost, database
`driver_audit_db`, and `?charset=utf8mb4`. No real credential belongs in source,
commands committed to Git, logs, or screenshots. The API uses `DAMS_PROD_RUNTIME_URL`
with the runtime account; use the migration account only for maintenance. Use
SQLAlchemy URL utilities for special characters; never print a complete URL.
The next commands connect to the configured database: execute them only as part
of an explicitly approved migration, never from the fictional-demo quick start.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m scripts.verify_database
.\.venv\Scripts\python.exe -m alembic check
```

Current application head is `0002`. The supplied production state is `0001`, not
re-queried by this documentation checkpoint. Upgrade and restricted activity grants
require separate approval; see [partial-DDL recovery](ADMIN_ACTIVITY.md#explicitly-authorized-deployment-only).
Verification connects, checks the recorded head and
compares schema metadata. Autogeneration comparison does not detect every CHECK
or server-default change; review revisions and integration behavior as well.
Downgrading from head to base drops all five application tables and their data:
use only an empty
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

Tests read URLs from their process environment, not automatically from `.env`.
For the approved local test database only, the following child process reads just
the two test settings, validates their identities and keeps production URLs blank.
It neither echoes credentials nor passes them as command arguments. The fixtures
still enforce an empty test schema and runtime grants. Do not replace these guards
with an unconditional `load_dotenv` of the entire server configuration.

```powershell
@'
import os
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
values = dotenv_values('.env')
for name in ('DATABASE_URL', 'DAMS_PROD_RUNTIME_URL',
             'DAMS_TEST_DATABASE_URL', 'DAMS_TEST_RUNTIME_URL'):
    os.environ[name] = ''
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
urls = []
for name, account in (('DAMS_TEST_DATABASE_URL', 'dams_test_migrate'),
                      ('DAMS_TEST_RUNTIME_URL', 'dams_test_app')):
    raw = values.get(name)
    if not raw:
        raise SystemExit('Both dedicated test settings are required')
    try:
        url = make_url(raw)
    except Exception:
        raise SystemExit('Invalid dedicated test connection setting') from None
    if not (url.drivername == 'mysql+pymysql'
            and url.database == 'driver_audit_test_phase1'
            and url.username == account and url.password
            and url.host in ('localhost', '127.0.0.1')
            and set(url.query) <= {'charset'}
            and url.query.get('charset', 'utf8mb4') == 'utf8mb4'):
        raise SystemExit('Refusing an unsafe test connection')
    urls.append(url)
    os.environ[name] = raw
if ((urls[0].host, urls[0].port or 3306, urls[0].database)
        != (urls[1].host, urls[1].port or 3306, urls[1].database)
        or urls[0].password == urls[1].password):
    raise SystemExit('Test accounts must share a target and use separate passwords')
import pytest
raise SystemExit(pytest.main(['--mysql', '-q', '-rs']))
'@ | & .\.venv\Scripts\python.exe -
```

`DAMS_TEST_RUNTIME_URL` additionally supplies the dedicated `dams_test_app` URL
for live runtime grant checks. It must target the same host/port/test database
as `DAMS_TEST_DATABASE_URL`. Keep it in the ignored, access-restricted `.env` or
process environment. The runtime test checks allowed writes/rollback, denied
DELETE and DDL, append-only events, and denial of production database access.
The live isolation test checks uncommitted-write isolation and a stable
REPEATABLE READ snapshot across two independent connections.
