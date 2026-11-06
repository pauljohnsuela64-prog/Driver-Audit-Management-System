"""Owned SQLite definitions and transactional v1 replacement migration."""
import json
from .models import FIELDS, OfflineError, validate_uuid, normalize_name

V1 = {'app_meta': 'CREATE TABLE app_meta (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)', 'local_profile': 'CREATE TABLE local_profile (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), id TEXT UNIQUE NOT NULL, name TEXT NOT NULL)', 'audit_records': 'CREATE TABLE audit_records (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, profile_id TEXT NOT NULL REFERENCES local_profile(id), driver_name TEXT NOT NULL, helper_name TEXT, audit_date TEXT NOT NULL, station TEXT NOT NULL, plate_number TEXT NOT NULL, remarks TEXT, audited_by_name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision >= 1), archived_at TEXT)', 'audit_events': "CREATE TABLE audit_events (id TEXT PRIMARY KEY NOT NULL, audit_id TEXT NOT NULL REFERENCES audit_records(id), revision INTEGER NOT NULL CHECK(revision >= 1), action TEXT NOT NULL CHECK(action IN ('CREATE','UPDATE','ARCHIVE')), actor_name TEXT NOT NULL, actor_profile_id TEXT NOT NULL, created_at TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL, UNIQUE(audit_id, revision))"}
V2 = dict(V1)
V2['auditor_identities'] = 'CREATE TABLE auditor_identities (id TEXT PRIMARY KEY NOT NULL)'
V2['audit_records'] = V1['audit_records'].replace('REFERENCES local_profile(id)', 'REFERENCES auditor_identities(id)')
V2['audit_events'] = V1['audit_events'].replace('actor_profile_id TEXT NOT NULL,', 'actor_profile_id TEXT NOT NULL REFERENCES auditor_identities(id),')
V2['transfer_receipts'] = 'CREATE TABLE transfer_receipts (package_id TEXT PRIMARY KEY NOT NULL, content_sha256 TEXT NOT NULL, source_installation_id TEXT NOT NULL, imported_at TEXT NOT NULL, imported_count INTEGER NOT NULL CHECK(imported_count>=0))'
INDEXES = {f'audit_records_{name}': f'CREATE INDEX audit_records_{name} ON audit_records({fields})' for name, fields in (('date','audit_date, seq'),('archive','archived_at, seq'),('station','station, seq'))}

def indexes(db):
    for sql in INDEXES.values(): db.execute(sql)

def owned(db, version):
    expected = V1 if version == 1 else V2
    tables = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*'"))
    # SQLite quotes replacement table names and rewrites references on rename.
    if version == 2:
        tables = {name: sql.replace('"audit_records"', 'audit_records').replace('"audit_events"', 'audit_events') for name, sql in tables.items()}
    actual_indexes = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"))
    return tables == expected and actual_indexes == INDEXES

def migrate(db, audit, snapshot, timestamp):
    def invalid():
        raise OfflineError('corrupt', 'The local audit history could not be read. Keep the file for recovery.')
    identities = set()
    try:
        for row in db.execute('SELECT id,name FROM local_profile'):
            validate_uuid(row['id'])
            if normalize_name(row['name']) != row['name']: invalid()
            identities.add(row['id'])
        for row in db.execute('SELECT * FROM audit_records'):
            current = audit(row); identities.add(current.profile_id)
            if any(row[key] != getattr(current, key) for key in (*FIELDS, 'audited_by_name')): invalid()
            previous = None
            events = db.execute('SELECT * FROM audit_events WHERE audit_id=? ORDER BY revision', (current.id,)).fetchall()
            if len(events) != current.revision: invalid()
            for revision, event in enumerate(events, 1):
                validate_uuid(event['id']); validate_uuid(event['actor_profile_id'])
                identities.add(event['actor_profile_id']); normalize_name(event['actor_name'])
                before = None if event['before_json'] is None else json.loads(event['before_json'])
                after = json.loads(event['after_json'])
                parsed = audit(after)
                normalized = snapshot(parsed)
                comparable = dict(after)
                for key in ('created_at', 'updated_at', 'archived_at'):
                    comparable[key] = normalized[key]
                if set(after) != set(normalized) or comparable != normalized: invalid()
                if event['revision'] != revision or parsed.revision != revision or parsed.id != current.id or before != previous: invalid()
                if timestamp(event['created_at']) != parsed.updated_at: invalid()
                if revision == 1:
                    if event['action'] != 'CREATE' or parsed.archived or parsed.created_at != parsed.updated_at: invalid()
                    if event['actor_profile_id'] != parsed.profile_id or event['actor_name'] != parsed.audited_by_name: invalid()
                else:
                    old = audit(previous)
                    for key in ('id','profile_id','audited_by_name','created_at'):
                        if after[key] != previous[key]: invalid()
                    if old.archived: invalid()
                    if event['action'] == 'ARCHIVE':
                        if parsed.archived_at != parsed.updated_at: invalid()
                        if any(after[key] != previous[key] for key in ('driver_name','helper_name','audit_date','station','plate_number','remarks')): invalid()
                    elif event['action'] != 'UPDATE' or parsed.archived: invalid()
                    elif all(after[key] == previous[key] for key in FIELDS): invalid()
                previous = after
            if previous is None or audit(previous) != current: invalid()
    except (ValueError, TypeError, KeyError):
        invalid()
    # All validation precedes mutations; the caller owns BEGIN/COMMIT/rollback.
    sequence = db.execute("SELECT seq FROM sqlite_sequence WHERE name='audit_records'").fetchone()
    db.execute(V2['auditor_identities'])
    db.executemany('INSERT INTO auditor_identities VALUES (?)', ((identity,) for identity in identities))
    db.execute(V2['transfer_receipts'])
    db.execute(V2['audit_records'].replace('CREATE TABLE audit_records ', 'CREATE TABLE audit_records_v2 '))
    db.execute(V2['audit_events'].replace('CREATE TABLE audit_events ', 'CREATE TABLE audit_events_v2 ').replace('REFERENCES audit_records(id)', 'REFERENCES audit_records_v2(id)'))
    for table in ('audit_records', 'audit_events'):
        db.execute(f'INSERT INTO {table}_v2 SELECT * FROM {table}')
        if db.execute(f'SELECT count(*) FROM {table}_v2').fetchone()[0] != db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]: invalid()
    if db.execute('PRAGMA foreign_key_check').fetchall(): invalid()
    db.execute('DROP TABLE audit_events'); db.execute('DROP TABLE audit_records')
    db.execute('ALTER TABLE audit_records_v2 RENAME TO audit_records')
    db.execute('ALTER TABLE audit_events_v2 RENAME TO audit_events')
    if sequence is not None:
        db.execute("UPDATE sqlite_sequence SET seq=? WHERE name='audit_records'", (sequence[0],))
    indexes(db)
    if not owned(db, 2) or db.execute('PRAGMA foreign_key_check').fetchall(): invalid()
    db.execute('PRAGMA user_version=2')
