# Architecture

Planned topology: Windows desktop and Android clients communicate over HTTPS
with FastAPI; the backend alone connects to MySQL. Clients must never receive
database credentials. FastAPI is installed, but no routes or authentication
implementation exist in this phase.

The backend separates configuration/transactions, SQLAlchemy entities, Pydantic
schemas, and a reserved repository package. Alembic is the production schema
authority: application startup must not call `create_all`.

## Schema

| Table | Purpose and constraints |
| --- | --- |
| users | Unique username, required name/password hash, ADMIN or AUDITOR, active flag, creation/update timestamps |
| audit_records | Seven business fields plus actor references, timestamps, soft deletion, optimistic version, optional unique idempotency key |
| audit_events | Audit and actor foreign keys, CREATE/UPDATE/DELETE action, optional JSON before/after snapshots, creation timestamp |
| auth_sessions | User foreign key, unique 64-character token hash, creation/expiry/revocation timestamps |

All tables have integer primary keys and use InnoDB/utf8mb4 on MySQL. Foreign keys
restrict deletion to retain attribution. Date, station, plate, actor, deletion,
event creation and session expiry indexes support future queries. Plate numbers
are intentionally nonunique: the same vehicle may appear in multiple audits.
Usernames and idempotency keys follow MySQL's configured case-insensitive collation;
clients should generate normalized opaque idempotency keys (for example UUIDs).

The business fields remain Driver Name, Helper Name, Audit Date, Station, Plate
Number, Remarks, and Audited By. Helper Name and Remarks are optional; the other
five are required and text fields must not be blank. Audited By is a stored name
snapshot (`audited_by_name`) linked to `audited_by_user_id`; future authenticated
services must supply it. No checklists, photos, GPS or pass/fail fields exist.

Timestamps use MySQL DATETIME(6) storing UTC. Connection initialization sets UTC
and strict SQL mode; the custom type rejects naive inputs and returns aware UTC
datetimes. Server defaults supply creation/update timestamps on insert. ORM
updates refresh `updated_at` and enforce optimistic `version`; direct SQL writers
must explicitly maintain these fields. Audit Date is a calendar date.

Deletion uses a paired timestamp/user reference. Idempotency uniqueness is enforced
when a key is supplied. Future services must atomically write an audit and its
event, verify authorization, and hash passwords/tokens; none is implemented here.
Runtime grants prohibit changing/deleting events. Administrators/migrators retain
DDL rights, so this is not tamper-proof storage.

`session_scope` commits on success, rolls back on failure and closes its session.
Engine creation is lazy, uses pool pre-ping, hides SQL parameter values, and does
not connect at import. The caller owns engine disposal. Production configuration
rejects root accounts and databases other than `driver_audit_db`.

References: [SQLAlchemy MySQL dialect](https://docs.sqlalchemy.org/en/21/dialects/mysql.html)
and [Alembic migration/version checks](https://alembic.sqlalchemy.org/en/latest/cookbook.html).
