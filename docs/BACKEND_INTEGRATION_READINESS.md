# Backend and native-client integration guide

The backend supports the implemented [Windows](WINDOWS_DESKTOP.md) and
[Android](ANDROID_DEVELOPMENT.md) clients through the same REST contracts.
Windows admission is ADMIN-only; Android supports ADMIN and AUDITOR ownership
rules. This is not production deployment approval. Activity logging adds revision
0002; production upgrade/grants require separate approval. Seven audit fields are
unchanged. See [current release evidence](RELEASE_READINESS.md).

## Start and connect

For fictional inspection first use the [desktop demo](WINDOWS_DESKTOP_DEMO.md)
or [Android demo](ANDROID_PHASE4B_ACCEPTANCE.md); neither needs production setup.
For an already approved backend, from `C:\BHLI-Audit` with its virtual environment,
migrated database, restricted grants and protected server configuration prepared:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

Server configuration uses DAMS_PROD_RUNTIME_URL with dams_prod_app; migration
credentials are for maintenance only. An operator must provision the first ADMIN
using the secure CLI in [AUTHENTICATION.md](AUTHENTICATION.md). Integration tests
do not provision production users or modify production records. GET /health is
liveness only; /docs and /openapi.json describe the current API.

The existing clients configure an API origin, bound HTTP requests, parse JSON and
retain ETags. Network work stays off the Tk UI thread; Flutter uses asynchronous
transport. Neither connects to MySQL or reads server `.env` credentials. Source
loopback demos are distinct from default Android HTTPS-only connection policy.
Failures omit request bodies and Authorization headers. No browser/CORS setup is
required for these native clients.

## Implemented client contract

| Area | Routes / behavior |
| --- | --- |
| Authentication | POST /auth/login; GET /auth/me; POST /auth/logout; POST /auth/change-password |
| Accounts (ADMIN) | POST/GET /users; GET/PATCH /users/{id}; PATCH /users/{id}/access; POST /users/{id}/reset-password |
| Audits | POST/GET /audits; GET/PATCH/DELETE /audits/{id}; GET /audits/{id}/history |
| Account activity (ADMIN) | GET /admin-activity; paginated action/actor/target filters |

Login sends JSON username/password and receives access_token, token_type=bearer
and expires_at. Send Authorization: Bearer <token> on protected requests. ADMIN
manages accounts and all audits; AUDITOR reads active audits and edits only their
own by immutable user ID. Deletion is ADMIN-only. Server authorization is final;
hiding client buttons is not a security boundary.

Account responses contain id, username, full_name, role and is_active. /auth/me
omits is_active. Account creation includes password; profile PATCH accepts only
username/full_name; access PATCH accepts only role/is_active. Admin reset requires
admin_password/new_password; self-change requires current_password/new_password
and no target ID. Password mutations return 204 with no JSON body. Self-change
revokes the current token too. Self-demotion, self-deactivation and admin self-reset
are rejected. See [account contracts](USER_ACCOUNTS.md).

Audit creation accepts driver_name, helper_name, audit_date (YYYY-MM-DD), station,
plate_number and remarks. Helper/remarks are optional; audited_by_name is supplied
by the server and preserved historically. Responses add identity/version/timestamp
metadata. Duplicate plates are allowed. Unknown fields are rejected. Send only
changed fields on PATCH; do not send the entire response as an update payload.
UTC timestamps include an offset; clients should display them appropriately while
keeping the calendar audit_date separate. See [audit contracts](AUDIT_API.md).

List envelopes contain items, total, page and page_size. Page bounds are 1..10000;
page_size is 1..100 (default 50). Accounts support search across username/full_name
and sort by ID. Audits support driver_name, plate_number, station, date_from,
date_to and audited_by_user_id, with sort id/-id/audit_date/-audit_date. History
uses the same pagination, in ascending event order. Search is literal substring
matching with database-dependent case/accent rules. Offset pages may shift during
concurrent writes.

Keep each audit response's quoted ETag (for example, "2"). Send it unchanged in
If-Match for PATCH/DELETE. On 412, reload the current record and let the user resolve
the edit; do not blindly overwrite. Missing If-Match returns 428. Account profile
edits have no ETag and use documented same-field last-writer-wins semantics;
overlapping access changes may return 409 and require reloading.

Generate one UUID Idempotency-Key per intended audit creation and retain it with
the normalized request for retries. New creation returns 201; a matching replay
returns 200 with the same record ID (current record state). Different original
payload/creator or a deleted original returns 409. Reuse the key only for that
creation. There is no general idempotency contract for other mutation routes.

Soft-deleted audits are hidden by default; ADMIN may request include_deleted=true
on audit read/list/history. Historical snapshots include actors, CREATE/UPDATE/DELETE
events and before/after state. There is no restore/hard-delete endpoint.

Sessions expire after eight hours without refresh or sliding renewal. Clear the
local token and reauthenticate on 401. Logout invalidates that token; access/password
changes revoke affected sessions. Disabled accounts cannot log in; reactivation
permits a new login but does not restore old tokens. A timed-out password change
may already have committed: prompt for fresh login rather than blindly retrying.

Errors use {"error":{"code":"...","message":"..."}}. Handle 403 as denied,
404 as absent/deleted, 409 as a conflict/reuse/self-protection condition, 422 as
invalid input, 429 with Retry-After, and 500/503 or network errors as service
failures. 204 responses have no body. No client should display raw exceptions,
connection URLs or credentials. UI-specific field hints must follow the documented
schema; server validation messages intentionally omit submitted data.

## Historical backend integration evidence

tests/test_backend_integration.py exercises one continuous API-only workflow:
ADMIN login and creation of two AUDITOR accounts; employee login, idempotent audit
creation, own read/edit, peer edit rejection, admin read/edit/soft deletion and
event continuity; employee renaming, deactivation/access loss/reactivation; admin
password reset and self-service password change with fresh login. Stable ownership
and original auditor-name snapshots remain intact throughout.

Assignment 3B execution: **1 passed in default SQLite mode; 1 passed in isolated
MySQL mode; no skips/failures.** This adds missing cross-feature coverage rather
than repeating Assignment 3A's 99 security checks. MySQL API traffic uses
dams_test_app; migration credentials only set up/clean driver_audit_test_phase1.
These are the original Phase 2C Assignment 3B measurements, not current release
totals. Later complete suites and five-job post-merge CI are indexed in
[release readiness](RELEASE_READINESS.md#verification-evidence).

## Deployment requirements and outstanding limitations

- **Administrator activity logging: implemented.** Account API mutations use the
  separate append-only activity store and ADMIN-only GET /admin-activity. See
  [ADMIN_ACTIVITY.md](ADMIN_ACTIVITY.md); production migration/grants are pending approval.
- **Deployment security: outstanding configuration/validation.** Establish an
  operator-managed ADMIN, protected server secrets, service supervision, backups,
  host/firewall policy, trusted proxy settings, log redaction and request limits.
- **HTTPS/trusted networking: required beyond loopback development.** Configure a
  trusted TLS reverse proxy, certificate verification and restricted network access.
  No deployed HTTPS endpoint or production network policy has been verified.
- **Rate limits: limited.** Login throttling is process-local (10 attempts/minute
  per client IP), not distributed. Deployment gateway limits remain necessary;
  password-management routes do not have a separate reauthentication limiter.
- **Client session storage: implemented in memory only.** Both clients discard
  tokens on logout/401 and require re-login after restart. No persistent token,
  credential file, registry token or remember-me feature exists. Android also
  conceals interrupted screens and verifies identity before revealing them.
- **Hosted CI:** Android/Flutter, SQLite, disposable MySQL, Windows Desktop and
  Windows Packaging/Installer passed after Phase 4B merge at `dfe5789`. See the
  current release index for URLs; the old two-job/PR #4 evidence is historical.
- Account mutations revalidate authorization under lock; other already-authorized
  in-flight requests are not retroactively canceled. History
  is append-only for runtime accounts, not tamper-proof against database admins.

Local client functionality is implemented and tested. Deployment configuration,
production activity rollout and final Version 1.0 candidate verification remain
separate gates; this guide does not approve production operation.
