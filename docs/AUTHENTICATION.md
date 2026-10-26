# Phase 2A: FastAPI foundation and authentication

The application factory is `backend.main:create_app`. Routes call services and
repositories. Revision 0001 is preserved; revision 0002 adds account activity history.
Deploy the new revision and runtime grant only after explicit production approval.
Audit CRUD and account-management APIs are now available; see
[backend integration readiness](BACKEND_INTEGRATION_READINESS.md). GUI, mobile
screens and exports remain outside the implemented backend scope.

## Local configuration and launch

Install the pinned `requirements.txt` in the Python 3.14 virtual environment.
Set `DAMS_PROD_RUNTIME_URL` in ignored `.env` to the dedicated `dams_prod_app`
mysql+pymysql URL for `driver_audit_db`. Use SQLAlchemy `URL.create` and
`render_as_string(hide_password=False)` only when writing protected local
configuration, never to terminal output. Keep the existing Windows ACL restricting
`.env` to its owner. The API never falls back to `DATABASE_URL`: that variable
is reserved for migration maintenance. Migration/root/test account URLs are refused
by normal application startup. Only the optional `charset=utf8mb4` query option
is accepted; driver-level identity, host and database overrides are rejected.
Injected engines are a trusted Python testing hook,
not an HTTP feature.

```powershell
Set-Location 'C:\BHLI-Audit'
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

Use HTTPS at a trusted reverse proxy before exposing the API to desktop/Android
clients. Do not enable SQL echo, request-body logging, Authorization-header logging,
or query-string credential transport. Keep server access logs disabled (as above),
or configure external infrastructure to omit credentials. Trust forwarded client
addresses only from explicitly configured proxies. Configure gateway request-size
and distributed rate limits for deployments with multiple workers or instances.
The included limiter permits ten login attempts per client address per minute per
process; it has bounded storage and fails closed at capacity. It is intentionally
not a distributed abuse-prevention service. Argon2 work is capped at four concurrent
operations per process. No external authentication service is required.

`/docs`, `/redoc` and `/openapi.json` expose FastAPI documentation. `/health` is a
liveness endpoint; it does not assert database readiness. Database failures during
API operations return a sanitized 503. Runtime startup creates a lazy engine and
never creates tables, runs migrations or creates an administrator.

## Routes

| Route | Input / result |
| --- | --- |
| GET /health | Public `{ "status": "ok" }` |
| POST /auth/login | JSON username/password; returns access_token, token_type=bearer, expires_at |
| GET /auth/me | Bearer token; returns id, username, full_name, role |
| POST /auth/logout | Bearer token; revokes only that session and returns 204 |
| POST /auth/change-password | Bearer token; current_password/new_password; revokes all own sessions and returns 204 |

Send `Authorization: Bearer <token>` from native clients. Tokens are not cookies,
JWTs or URL parameters. Login rejects additional fields, so clients cannot supply
a role. Password fields use Pydantic SecretStr and are never returned. Each login
creates a new 256-bit random opaque token, returned once; only its SHA-256 digest
is stored in `auth_sessions`. Expiration is fixed at eight hours, with no refresh
endpoint or sliding renewal. Multiple sessions are allowed. Expired/revoked session
rows are retained; an explicitly authorized maintenance policy can archive them later.

Bearer credentials can be replayed while valid: protect client storage with native
OS secure storage and TLS. Every protected request checks the stored session,
expiration, revocation and the current user's active status and role. Disabled
users and revoked tokens are rejected on subsequent requests. Account mutations
recheck the session and role under the account lock before writing; revocation or
demotion that wins that lock prevents the mutation. Other already-authorized
in-flight requests are not retroactively canceled. Recovery revokes every existing
session for that administrator. Logout leaves other sessions valid.

## Self-service password change (Phase 2C, Assignment 1E)

ADMIN and AUDITOR may POST /auth/change-password with exactly current_password and
new_password. The account comes only from the authenticated session; a target ID
or any extra field is rejected. Both fields use SecretStr. Current passwords are
bounded to 1..128 characters; replacements must be nonblank, 15..128 characters,
and different from the verified current password. Password characters are not
trimmed. Missing/invalid fields return sanitized 422; incorrect current passwords
or invalid/disabled sessions return 401; password reuse returns 409.

Success returns 204 with no body and requires a fresh login. Argon2id replacement
and revocation of every unrevoked account session, including the current and expired
sessions, commit atomically. Failures roll back both changes. No credentials or
tokens are returned. Account role/status, ownership IDs and audit history stay intact.

The existing account transaction guard serializes changes with administrator
resets and access changes. Current locking reads revalidate the session after
waiting. Login locks the same account before password verification/session insert
(SQLite uses BEGIN IMMEDIATE). A login using the old password that finishes first
is revoked by the change; one that follows it fails. An administrator reset that
wins first invalidates a waiting change request; one following a completed change
replaces that password and revokes its sessions. Focused coverage is in
tests/test_password_change.py, in SQLite and isolated MySQL modes.

## Roles and authorization

Exactly ADMIN and AUDITOR are accepted. `require_roles(...)` is reusable and
server-enforced. ADMIN-only operations use `require_roles("ADMIN")`; shared audit
operations can allow both roles. Role changes affect existing sessions on the next
request. Role enforcement is tested on routes registered only in tests; those routes
are absent from the production application/OpenAPI.

Phase 2B must additionally enforce record ownership and visibility: AUDITOR may
create/view permitted records and edit their own records, never delete records or
administer users. ADMIN will have full audit/user administration. These policies do
not create audit or user-management endpoints in Phase 2A.

## Transactions and failures

Each request uses a SQLAlchemy transaction that commits before a successful response
is sent (`Depends(..., scope="function")`). Errors roll back changes and close the
session. Login locks the user row while verifying and issuing a session, serializing
against administrator password recovery. Logout updates revocation conditionally.
No raw user input is interpolated into SQL.

Errors use `{ "error": { "code": "...", "message": "..." } }`:

- 401 unauthorized: identical response for unknown username, wrong password,
  disabled account, malformed/unknown/expired/revoked token; includes Bearer challenge.
- 403 forbidden: authenticated user lacks the required role.
- 422 invalid_request: request validation failed; submitted values are omitted.
- 429 rate_limited: retry after 60 seconds.
- 503 service_unavailable: database failure with no SQL/connection diagnostic.
- 500 internal_error: unexpected service failure with no diagnostic content.
- Other HTTP errors use the same envelope with code http_error.

Responses set Cache-Control: no-store and X-Content-Type-Options: nosniff. Passwords,
tokens, database URLs and exception inputs are not logged by application code.
Unknown usernames still incur a real Argon2 verification to reduce timing differences.

## Initial administrator and recovery

Run locally under the Windows account allowed to read `.env`:

```powershell
.\.venv\Scripts\python.exe -m scripts.bootstrap_admin
```

Enter a username, full name and a unique password of 15-128 characters using hidden
password prompts. If the terminal cannot hide input, setup refuses to continue.
There are no default credentials or password command arguments.
Passwords use Argon2id (64 MiB, three iterations, parallelism four, unique salts).
Valid older hashes are upgraded on login. The bootstrap refuses when any user exists.
MySQL advisory locking serializes concurrent bootstrap commands, using only runtime
privileges. Nothing changes the MySQL administrator account or its password.

For an existing application ADMIN only, use:

```powershell
.\.venv\Scripts\python.exe -m scripts.bootstrap_admin --recover
```

Provide the exact username and a new password, and explicitly type RECOVER at the
local confirmation prompt. Recovery re-enables that administrator, changes its hash
and revokes all its sessions atomically. It cannot promote an AUDITOR or silently
create a missing account. If no administrator exists but other users do, stop and
arrange a separately authorized account-recovery procedure. Do not reset MySQL
credentials, bypass the duplicate guard or delete user data.

No production administrator is automatically created during implementation or tests.

## Verification

Default API tests use disposable SQLite files. `--mysql` uses Alembic only to set up
and tear down the empty isolated test database; every API request, bootstrap, recovery
and fixture user insert then uses `dams_test_app`. Runtime URLs must match the
migration test URL's driver, host, port and database. Production is never a test target.

```powershell
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest; raise SystemExit(pytest.main(['-q', '-rs']))"
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest; raise SystemExit(pytest.main(['--mysql', '-q', '-rs']))"
```

The test process needs `DAMS_TEST_DATABASE_URL` and `DAMS_TEST_RUNTIME_URL` in its
environment. The commands above load ignored configuration without exposing URLs.
No new schema revision is needed. The seven approved audit fields are unchanged.

Implementation references: [Argon2-cffi PasswordHasher](https://argon2-cffi.readthedocs.io/en/stable/api.html)
and [FastAPI transaction dependency lifecycle](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/).
