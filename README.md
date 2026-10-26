# Driver Audit Management System (DAMS)

Phase 1 provides the Python foundation, MySQL schema, Alembic migration and tests.
Phase 2A adds the FastAPI application, bearer-session authentication, role
dependencies and secure local administrator bootstrap/recovery. See
[authentication setup and API](docs/AUTHENTICATION.md).
Phase 2B adds the [audit records REST API](docs/AUDIT_API.md), atomic history,
version preconditions and idempotent creation. Official directory: `C:\BHLI-Audit`.
Desktop GUI, Android application and reporting remain future work.

## Setup (PowerShell)

```powershell
Set-Location 'C:\BHLI-Audit'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Tested with Python 3.14.3 on Windows; all direct and transitive dependencies are
pinned in requirements.txt. Keep `.env` local and fill in dedicated DAMS credentials.
Follow [database setup](docs/DATABASE_SETUP.md) before running migrations.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.verify_database
.\.venv\Scripts\python.exe -m pytest -q -rs
.\.venv\Scripts\python.exe -m pip check
```

MySQL integration is opt-in through `DAMS_TEST_DATABASE_URL`; missing credentials
produce an explicit skip. SQLite checks do not establish MySQL compatibility.
See [architecture](docs/ARCHITECTURE.md) and [verification record](docs/VERIFICATION.md).

## Layout

`backend/core` owns configuration, connection and transaction lifecycle;
`backend/models` contains the four tables; `backend/schemas` validates the seven
business fields; `backend/repositories` contains authentication persistence, and `backend/services`
contains authentication and audit transaction rules.
`database`, `migrations`, `scripts`, `tests`, and `docs` contain setup, versioned
DDL, operator tools, checks, and documentation. `desktop` and `mobile` document
future clients without implementing them.

Phases 1 and 2A are merged. Phase 2B is developed on `feat/dams-audit-records`
for a draft PR and engineering review.
