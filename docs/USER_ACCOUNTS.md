# Employee accounts: Assignments 1A through 1D

All account routes require a valid bearer session and current ADMIN role. AUDITOR
receives 403; missing/invalid sessions receive 401. Profile editing and dedicated role/status management are supported.
Administrator password resets require current-password reauthentication.

| Route | Result |
| --- | --- |
| POST /users | 201 with newly created active account |
| GET /users | Paginated accounts, including inactive accounts |
| GET /users/{id} | Safe details, or 404 when absent |
| PATCH /users/{id} | ADMIN-only partial username/full_name edit |
| PATCH /users/{id}/access | ADMIN-only role/status changes |
| POST /users/{id}/reset-password | Reauthenticated ADMIN reset, 204 |

Creation body (fictional example):

```json
{"username":"example.employee","full_name":"Example Employee",
 "role":"AUDITOR","password":"example-only long passphrase"}
```

All four fields are required; role must be ADMIN or AUDITOR. Username and full
name are trimmed, nonblank, and limited to 100 and 200 characters. Passwords use
the existing 15..128-character passphrase policy, reject all-whitespace values,
and are preserved exactly (not trimmed). Existing bounded Argon2id hashing is
reused. Extra fields, including id, password_hash and is_active, are rejected.
New accounts are always active. The database unique username index arbitrates
concurrent creates; duplicate usernames return generic 409 username_exists.
Username uniqueness and search case/accent behavior follow database collation
(MySQL is case-insensitive; SQLite test behavior may differ).

Responses contain only id, username, full_name, role and is_active. Neither
passwords, hashes nor session tokens are returned. Existing /auth/me is unchanged.

GET /users supports page (1..10000, default 1), page_size (1..100, default 50), and
optional search (trimmed nonblank, maximum 200 characters). Search matches literal
substrings in username OR full_name; percent/underscore are escaped and queries
are parameterized. Results sort by ascending ID. The envelope contains items,
total, page and page_size. Offset pages may shift with concurrent insertions.

Validation failures return sanitized 422; database failures return sanitized 503.
Creation commits before success is sent and rolls back on insert/commit failures.
Existing runtime SELECT/INSERT grants suffice; no migrations or production writes
are needed. All seven audit business fields and existing schema remain unchanged.

Focused checks: `python -m pytest tests/test_user_schemas.py tests/test_users.py
 tests/test_auth.py -q -rs` (put the command on one line). Add --mysql after loading
ignored local test configuration securely into the process environment to verify
with dams_test_app on the isolated driver_audit_test_phase1 database. Fixtures use
migration credentials only for setup/cleanup. Never target production for tests.

Full regression and final Phase 2C PR publication are deferred to that assignment.


## Limited profile editing (Assignment 1B)

PATCH /users/{id} accepts username, full_name, or both, with the same trimming and
length rules as creation. Empty bodies, null/blank values and all other fields
(including role, is_active, password, password_hash, IDs and timestamps) return 422.
ADMIN may edit their own profile or another employee. Missing accounts return 404;
duplicate usernames return 409, including concurrent uniqueness conflicts.
The response contains only the existing five safe account fields.

Writes update only supplied fields in the existing request transaction. Database
row locks serialize overlapping writes: different-field edits are preserved;
same-field edits use last-writer-wins ordering, without a version/If-Match contract.
A successful no-op edit returns 200. Failed updates/commits roll back completely.
No schema change or additional runtime permissions are needed.

Account IDs, roles, active status and password hashes remain unchanged. Existing
sessions continue by stable account ID and recheck permissions on each request.
Login subsequently uses the new username. Renaming never rewrites historical audit
name snapshots or ownership. The normal updated_at timestamp is maintained by the
ORM update expression; clients cannot supply timestamps.

Profile checks are in tests/test_user_profiles.py. Run them with the existing
user, schema and authentication tests in default and isolated --mysql modes.


## Role and account-status management (Assignment 1C)

PATCH /users/{id}/access accepts role (exactly ADMIN or AUDITOR), is_active (JSON
true/false), or both. Empty/null payload fields, string/integer booleans and all
other fields return 422. Responses use the same five safe account fields. Missing
accounts return 404. The profile endpoint still rejects role and status changes.

Administrators cannot demote or deactivate themselves (409). The last active
ADMIN is protected. Access transactions first lock the lowest user ID as a common
guard; accounts cannot be physically deleted. SQLite tests use BEGIN IMMEDIATE.
After acquiring the guard, current locking reads revalidate the caller's session,
active status and role, then the target and active-admin count. This prevents two
administrators from removing each other using authority cached before waiting.
An already-revoked caller gets 401; a caller without ADMIN permission gets 403.

Requests capture target role/status before waiting; if either changed while they
waited, return 409 access_conflict and require a reload before retrying. Access
changes therefore do not silently overwrite overlapping changes. This is not an
If-Match API: a new request observes the state when it starts. No-op requests return
200 without revoking sessions.

An actual role/status change revokes all unrevoked, unexpired sessions for that
account in the same transaction. Insert/update/commit failures roll back both
account and session changes. Disabled accounts cannot log in; reactivation permits
login with the existing password, but never restores old sessions. Account IDs,
password hashes and historical audit attribution are preserved. Runtime grants
suffice; no migration or production data change is required.

Access-specific tests are in tests/test_user_access.py, including forced concurrent
cross-administrator changes, same-target conflicts and session-revocation failures.

## Administrator password reset (Assignment 1D)

POST /users/{id}/reset-password requires a valid active ADMIN session and exactly
two fields: admin_password (the acting administrator's current password) and
new_password. Both use secret request types. The replacement must be 15..128
characters and nonblank; its exact characters are preserved. Reauthentication is
bounded to 1..128 characters for compatibility with existing credentials.

Success returns 204 with no body. Missing/invalid sessions or incorrect current
password return generic 401; AUDITOR access returns 403. Missing targets return
404 after reauthentication; self-reset returns 409. Missing fields, unexpected
fields and invalid passwords return sanitized 422. Database errors return 503.
No passwords, hashes or tokens are returned, generated for delivery, or emailed.

Reset shares the access-management transaction guard, revalidates the caller under
locking reads, and locks the target user row. Argon2id hash replacement and
revocation of every unrevoked target session (including expired sessions) commit
atomically. Any write/revocation/commit failure rolls back both changes. Role,
active status, account ID and historical audit attribution remain unchanged.
A disabled account stays disabled; authorized reactivation permits login with
the replacement password, but never restores old sessions.

MySQL login locks the same user row before password verification/session creation.
SQLite login uses BEGIN IMMEDIATE for equivalent serialization. A login with the
old password that completes first has its token revoked by reset; one following
reset fails password verification. Existing bootstrap/recovery is unchanged.
Self-service password changes and email recovery are outside this assignment.

Focused tests: tests/test_password_reset.py in default and isolated --mysql modes,
followed by the affected authentication, bootstrap and user-management regressions.
Full-suite publication testing remains deferred to the final Phase 2C assignment.
