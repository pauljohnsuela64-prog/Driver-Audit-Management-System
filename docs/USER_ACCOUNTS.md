# Employee accounts: Assignment 1A

All three routes require a valid bearer session and current ADMIN role. AUDITOR
receives 403; missing/invalid sessions receive 401. No account edits, role changes,
activation/deactivation or password resets are implemented.

| Route | Result |
| --- | --- |
| POST /users | 201 with newly created active account |
| GET /users | Paginated accounts, including inactive accounts |
| GET /users/{id} | Safe details, or 404 when absent |

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
