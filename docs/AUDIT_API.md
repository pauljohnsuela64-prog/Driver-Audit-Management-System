# Audit records API (Phase 2B)

Run from `C:\BHLI-Audit` using the existing [authentication setup](AUTHENTICATION.md).
Every audit endpoint requires `Authorization: Bearer <opaque session token>`.
Production connections continue to use `dams_prod_app`; revision `0001` is unchanged.

| Method | Path | Behavior |
| --- | --- | --- |
| POST | /audits | Create; optional UUID Idempotency-Key |
| GET | /audits | Filtered, paginated active records |
| GET | /audits/{id} | Read record and ETag |
| PATCH | /audits/{id} | Partial edit, required If-Match |
| DELETE | /audits/{id} | ADMIN soft deletion, required If-Match |
| GET | /audits/{id}/history | Paginated chronological events |

ADMIN can create/read/edit all records and soft-delete. AUDITOR can create/read
all active records and their history, but edit only records owned by their account
ID. Matching display names do not grant ownership. AUDITOR cannot delete.
Account administration is documented in [USER_ACCOUNTS.md](USER_ACCOUNTS.md).

## Payload and identity

Example POST body (fictional data):

```json
{"driver_name":"Example Driver","helper_name":null,"audit_date":"2026-10-26",
 "station":"Example Station","plate_number":"EXAMPLE-1","remarks":"Example only"}
```

Exactly seven business fields remain: those six inputs plus `audited_by_name`.
The service supplies the authenticated account's full name and account ID at
creation. The original name snapshot and ownership never change during edits.
Clients cannot supply identity, IDs, version, timestamps, deletion flags or other
unknown payload fields. Plate numbers are deliberately nonunique.

Required names/station/plate are trimmed, nonblank strings bounded to 200/150/30
characters respectively. Helper is optional, at most 200 characters; remarks
are optional, at most 10,000 characters (safe for utf8mb4 TEXT). Both are trimmed;
blank becomes null. Dates must be real calendar dates in MySQL's 1000..9999 year range, spelled
YYYY-MM-DD; numeric
epochs and datetimes are rejected. PATCH requires at least one field, validates
only supplied fields, permits clearing helper/remarks with null, and rejects null
for required fields. Server fields never become writable through PATCH.

Responses contain the seven business fields and lifecycle metadata: id, version,
audited_by_user_id, updated_by_user_id, deleted_by_user_id, deleted_at, created_at,
updated_at. UTC timestamps have a UTC offset; no password hashes, session tokens,
or idempotency keys are returned. Create returns 201, replay 200, edit/read 200,
and deletion 204. Record responses carry a quoted numeric ETag, e.g. `"1"`.

## Listing and history

`GET /audits?station=Example&date_from=2026-01-01&page=1&page_size=50&sort=-id`
returns `{ "items": [...], "total": 1, "page": 1, "page_size": 50 }`.
Supported filters: driver_name, plate_number, station (literal substring matching),
date_from/date_to (inclusive), and audited_by_user_id (positive account ID).
Percent and underscore are escaped as literal characters, and SQL is parameterized.
Case/accent matching follows the database collation; SQLite and MySQL may differ.
Date ranges must be ordered. Sort allowlist: id, -id, audit_date, -audit_date;
ID breaks date ties deterministically. Defaults: -id, page 1, size 50.
Page is bounded to 1..10000 and size to 1..100. Offset pagination is not a snapshot
across separate requests; concurrent changes may shift pages.

History uses the same page bounds, orders by event ID ascending, and returns
items/total/page/page_size. Each event includes ID, audit ID, actor user ID, action,
before_data, after_data and UTC created_at. CREATE before_data is null; snapshots
contain audit fields and lifecycle metadata only. Record mutation and event insert
commit together. Runtime grants forbid event updates/deletes and physical record
deletion. Failed history insertion or request commit rolls back the record change.

## Versions, deletion and retries

Send the last record ETag in `If-Match: "1"` for PATCH or DELETE. Missing precondition
returns 428; malformed, weak, wildcard or multi-value tags return 422; a stale
version returns 412. Database optimistic conflicts return 409. A successful PATCH,
including a no-op, advances the version and appends an event. MySQL locking reads
serialize competing mutations; ORM version checks remain a second safeguard.

Soft-deleted records are excluded from ordinary reads/list/history. ADMIN may set
`include_deleted=true` on these GET routes; AUDITOR receives 403 for that option.
Edits and repeated deletion of deleted records return 404. No restore/hard-delete
endpoint exists. Deletion preserves original ownership and history.

POST optionally accepts a UUID `Idempotency-Key`, canonicalized before storage.
Without it, repeated POSTs intentionally create separate records. With it, the
unique index allows only one creation. A replay must match the original creator
ID and normalized original six-field payload, including omitted/null optional
fields. The original CREATE snapshot is used even after later edits. Matching
replays return the current record with 200 and do not create another event. A key
owned by another creator, a different original payload, or a deleted original
returns generic 409 without returning the other record. Keys have no expiry and
are globally unique. Savepoints recover duplicate inserts; locking reads see a
concurrent winner even under MySQL REPEATABLE READ. Transient database failures
return 503; a client can retry creation safely with the same key and body.

## Errors and verification

Errors use `{ "error": { "code": "...", "message": "..." } }` without input,
SQL, connection details or stack traces. Authentication failure is 401, forbidden
access 403, missing/deleted record 404, invalid input 422, and unexpected failure
500. Responses use no-store caching. Existing process-local login throttling and
its deployment limitations remain as documented for Phase 2A.

Run the complete suite with `python -m pytest -q -rs` and
`python -m pytest --mysql -q -rs`. Load DAMS_TEST_DATABASE_URL and
DAMS_TEST_RUNTIME_URL securely into the process environment first; tests do not
automatically read them from .env. The isolated driver_audit_test_phase1 database
must start empty. Migration credentials create/clean the test schema; API traffic
uses dams_test_app. Never run downgrade/cleanup tests on driver_audit_db.

SQLite is a local test mode. Audit writes explicitly start a transaction before
SAVEPOINT to avoid sqlite3 legacy-mode early commits, documented by
[SQLAlchemy](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html).
Live MySQL tests establish the production transaction/concurrency behavior.
