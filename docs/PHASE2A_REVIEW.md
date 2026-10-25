# Phase 2A engineering verification

Date: October 25, 2026 (Asia/Manila). Project: `C:\BHLI-Audit`.
Verdict: **PASS for Phase 2A draft review**. No Phase 2B implementation or merge.

## Recovery and scope

Resumed existing uncommitted work on `feat/dams-backend-auth`, based on merged
Phase 1 `f2142bdfd1b7035f0d995f2f61710fdb1824affd`. No repository instructions
were present. No work was reset, stashed or discarded.

Already present: application factory, router/service/repository separation,
Argon2id/opaque-session primitives, runtime account configuration, role checks,
transaction dependency, error envelope, limiter and interactive bootstrap/recovery.
Authentication tests and operational documentation were absent at resumption.

Completed: API and bootstrap regression coverage, real MySQL runtime integration,
concurrency and recovery tests, secure terminal fallback handling, bounded rehashing,
connection-option safeguards, dependency compatibility and documentation.

Routes are GET /health, POST /auth/login, POST /auth/logout and GET /auth/me.
Production OpenAPI contains no test authorization routes. No audit CRUD, user
administration routes, GUI, Android UI or reporting was implemented. The reusable
role dependency supports the future operations without implementing them.

## Security and transaction review

- Passwords use salted Argon2id with 64 MiB memory, three iterations and parallelism
  four; hashing/verification/rehash share a four-operation semaphore. New bootstrap
  passwords require 15-128 characters. Existing valid older hashes upgrade on login.
- Tokens contain 256 random bits. Only SHA-256 digests are stored, with eight-hour
  expiration; logout conditionally revokes the current session. No refresh endpoint.
- Unknown user, wrong password and disabled user share one 401 message. Unknown users
  undergo dummy Argon2 verification. Tokens must match the expected bearer format.
- Current active status and role are read for every protected request. Recovery
  revokes every session atomically; AUDITOR cannot use the ADMIN-only dependency.
- Function-scoped SQLAlchemy dependencies commit before successful responses. Tests
  prove login and logout commit failures return 503 and roll back; service failures
  return 500 without diagnostic content. Validation never echoes submitted fields.
- Queries use SQLAlchemy expressions or bound parameters. The API uses only
  `DAMS_PROD_RUNTIME_URL` with the exact production runtime account, never the
  migration URL. Isolated API tests connect as dams_test_app.
- Bootstrap refuses any pre-existing users, serializes MySQL creators using a named
  advisory lock, and requires explicit recovery for an existing ADMIN. It uses
  runtime privileges and never resets MySQL administrator credentials. Password
  input fails closed if getpass cannot hide terminal input.
- No password, bearer token, local database URL or production business record was
  introduced into source. Application code logs neither request inputs nor exception
  diagnostics; documented Uvicorn invocation disables access logs.

## Verified issues corrected during review

1. Password rehashing initially bypassed the Argon2 semaphore. It now shares the
   bounded hashing path, and legacy-hash login upgrades are tested.
2. SQLAlchemy URL query options can override the username/database declared in a
   URL. Confirmed against the installed driver without connecting. API runtime and
   destructive-test guards now allow only optional charset=utf8mb4, rejecting user,
   database, host and other override options before connection. Regression tests
   verify rejection. Existing Phase 1 guard tests are preserved.
3. getpass can warn then fall back to echoed input. Bootstrap treats that warning
   as an error before fallback; a regression verifies it cannot continue.
4. Installed Starlette expects httpx2. Test dependencies now use its supported
   client, pinned with all dependencies; the deprecated temporary httpx dependency
   and unused dependencies introduced with it were removed.

## Execution evidence

| Check | Actual result |
| --- | --- |
| Initial auth tests on SQLite | 34 passed |
| Initial auth tests on MySQL runtime account | 34 passed |
| Final complete default regression with local test URLs loaded | 114 passed, zero skipped |
| Final complete `pytest --mysql` | 114 passed, zero skipped |
| Final auth test collection | 47 tests, all included in both complete runs |
| Live bootstrap race | One creator succeeded, the other refused; exactly one ADMIN |
| Dependency integrity | pip check: no broken requirements |
| Source compilation | backend and scripts compiled successfully |
| Production Alembic check | No new upgrade operations detected |
| Production verification script | Connected, revision 0001, schema compatible |
| Production runtime inspection | dams_prod_app connected; zero users and zero sessions |

The default run uses isolated SQLite files for API tests and includes four explicitly
live MySQL tests when credentials are loaded. The --mysql run switches shared model
fixtures and all API fixtures to MySQL; pure unit tests remain database-independent.
Migration credentials only create/drop the disposable test schema. API setup,
requests, bootstrap and recovery use the dedicated runtime account. The test database
is returned empty after successful tests. Production is inspected read-only.

All original 62 Phase 1 tests remain, plus four new connection-override guard tests,
47 authentication tests and one live bootstrap concurrency test. No new migration,
model or audit-field change is present.

## Files and operational boundaries

Application: backend/main.py, backend/api, backend/services, backend/repositories/auth.py,
backend/schemas/auth.py and core config/errors/security/throttle modules.
Operations: scripts/bootstrap_admin.py, requirements.txt and the empty .env.example.
Tests: tests/test_auth.py, tests/test_auth_mysql.py and strengthened existing test guards.
Documentation: README.md, AUTHENTICATION.md and this execution record.

No production administrator was created. Local bootstrap is an operator action.
Health is liveness only; database operation failures produce 503. Tokens are bearer
credentials and can be replayed until revoked/expired; TLS and OS-secure client
storage are required for deployment. Rate limiting is per process; use a trusted
proxy with distributed limits and body-size limits for multi-worker exposure.
Already-authorized in-flight requests are not retroactively canceled by revocation.
Expired/revoked rows are retained pending an authorized maintenance policy.

Publication uses a normal push and one draft PR targeting main. The final report/PR
records the resulting commit and remote verification. No force-push or main change.
