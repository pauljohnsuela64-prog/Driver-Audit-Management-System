"""Populated legacy files must migrate atomically without changing history."""
import json
import sqlite3
import pytest
from desktop.offline.models import OfflineError, new_uuid
from desktop.offline.repository import SqliteRepository

V1 = {'app_meta': 'CREATE TABLE app_meta (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)', 'local_profile': 'CREATE TABLE local_profile (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), id TEXT UNIQUE NOT NULL, name TEXT NOT NULL)', 'audit_records': 'CREATE TABLE audit_records (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, profile_id TEXT NOT NULL REFERENCES local_profile(id), driver_name TEXT NOT NULL, helper_name TEXT, audit_date TEXT NOT NULL, station TEXT NOT NULL, plate_number TEXT NOT NULL, remarks TEXT, audited_by_name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision >= 1), archived_at TEXT)', 'audit_events': "CREATE TABLE audit_events (id TEXT PRIMARY KEY NOT NULL, audit_id TEXT NOT NULL REFERENCES audit_records(id), revision INTEGER NOT NULL CHECK(revision >= 1), action TEXT NOT NULL CHECK(action IN ('CREATE','UPDATE','ARCHIVE')), actor_name TEXT NOT NULL, actor_profile_id TEXT NOT NULL, created_at TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL, UNIQUE(audit_id, revision))"}
PROFILE = "11111111-1111-4111-8111-111111111111"
AUDIT = "22222222-2222-4222-8222-222222222222"
ACTOR = "33333333-3333-4333-8333-333333333333"
STAMP = "2026-01-01T00:00:00+00:00"

def legacy(path):
    db = sqlite3.connect(path)
    for sql in V1.values(): db.execute(sql)
    for name, fields in (("date", "audit_date, seq"), ("archive", "archived_at, seq"), ("station", "station, seq")):
        db.execute(f"CREATE INDEX audit_records_{name} ON audit_records({fields})")
    db.executemany("INSERT INTO app_meta VALUES (?,?)", [("app_id", "com.bhli.audit.offline.windows"), ("installation_id", PROFILE)])
    db.execute("INSERT INTO local_profile VALUES (1,?,?)", (PROFILE, "Renamed Auditor"))
    original = dict(id=AUDIT, profile_id=PROFILE, driver_name="Driver", helper_name=None, audit_date="2026-01-01", station="Station", plate_number="001", remarks=None, audited_by_name="Original Auditor", created_at=STAMP, updated_at=STAMP, revision=1, archived_at=None)
    final = dict(original, revision=2, archived_at=STAMP)
    db.execute("INSERT INTO audit_records (seq,"+",".join(final)+") VALUES (41,"+",".join("?" for _ in final)+")", tuple(final.values()))
    for revision, action, before, after in [(1,"CREATE",None,original),(2,"ARCHIVE",original,final)]:
        db.execute("INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)", (new_uuid(),AUDIT,revision,action,"Original Auditor" if revision == 1 else "Historical Auditor",PROFILE if revision == 1 else ACTOR,STAMP,None if before is None else json.dumps(before),json.dumps(after)))
    db.execute("UPDATE sqlite_sequence SET seq=90 WHERE name='audit_records'")
    db.execute("PRAGMA user_version=1")
    db.commit(); db.close()

def dump(path):
    with sqlite3.connect(path) as db: return tuple(db.iterdump())

def test_populated_v1_preserves_history_sequence_metadata_and_restart(tmp_path):
    path=tmp_path/'legacy.db'; legacy(path)
    with sqlite3.connect(path) as db:
        events=db.execute('SELECT * FROM audit_events ORDER BY revision').fetchall()
        records=db.execute('SELECT * FROM audit_records').fetchall()
    repo=SqliteRepository(path)
    db=repo._connection
    assert db.execute('PRAGMA user_version').fetchone()[0] == 2
    assert db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    assert set(r[0] for r in db.execute('SELECT id FROM auditor_identities')) == {PROFILE,ACTOR}
    assert tuple(map(tuple,db.execute('SELECT * FROM audit_records'))) == tuple(records)
    assert tuple(map(tuple,db.execute('SELECT * FROM audit_events ORDER BY revision'))) == tuple(events)
    assert db.execute("SELECT seq FROM sqlite_sequence WHERE name='audit_records'").fetchone()[0] == 90
    assert repo.profile().name == 'Renamed Auditor'
    assert repo.read(AUDIT).archived
    assert repo.history(AUDIT).total == 2
    with pytest.raises(sqlite3.IntegrityError): db.execute("UPDATE audit_events SET actor_profile_id='missing'")
    repo.close(); SqliteRepository(path).close()

@pytest.mark.parametrize('damage', ['index','actor','chain','foreign','constraint'])
def test_invalid_legacy_is_unchanged(tmp_path,damage):
    path=tmp_path/'legacy.db'; legacy(path)
    with sqlite3.connect(path) as db:
        if damage=='index': db.execute('DROP INDEX audit_records_date')
        if damage=='actor': db.execute("UPDATE audit_events SET actor_profile_id='bad'")
        if damage=='chain': db.execute('UPDATE audit_events SET before_json=NULL WHERE revision=2')
        if damage=='foreign': db.execute("UPDATE app_meta SET value='foreign' WHERE key='app_id'")
        if damage=='constraint': db.execute('CREATE INDEX foreign_index ON audit_events(action)')
    before=dump(path)
    with pytest.raises(OfflineError): SqliteRepository(path)
    assert dump(path)==before

@pytest.mark.parametrize('failure', ['full', 'commit', 'locked'])
def test_migration_failure_rolls_back_and_restart_succeeds(tmp_path, monkeypatch, failure):
    path=tmp_path/'legacy.db'; legacy(path); before=dump(path)
    original_connect=sqlite3.connect
    blocker=None
    if failure=='locked':
        blocker=original_connect(path)
        blocker.execute('BEGIN')
        blocker.execute('SELECT * FROM audit_records').fetchall()
    class FailingConnection(sqlite3.Connection):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            if failure=='full':
                pages=self.execute('PRAGMA page_count').fetchone()[0]
                self.execute(f'PRAGMA max_page_count={pages}')
            if failure=='commit':
                self.execute('CREATE TEMP TABLE guard (id INTEGER PRIMARY KEY, parent INTEGER REFERENCES guard(id) DEFERRABLE INITIALLY DEFERRED)')
        def execute(self,sql,*args):
            result=super().execute(sql,*args)
            if failure=='commit' and sql.startswith('CREATE TABLE auditor_identities'):
                super().execute('CREATE TEMP TRIGGER fail_commit AFTER INSERT ON main.auditor_identities BEGIN INSERT OR IGNORE INTO guard VALUES (1,2); END')
            return result
    def connect(*args,**kwargs):
        return original_connect(*args,**kwargs,factory=FailingConnection)
    monkeypatch.setattr(sqlite3,'connect',connect)
    try:
        with pytest.raises(OfflineError) as caught: SqliteRepository(path,timeout=.01)
        assert caught.value.code == {'full':'full','commit':'storage','locked':'busy'}[failure]
    finally:
        if blocker is not None: blocker.rollback(); blocker.close()
    monkeypatch.setattr(sqlite3,'connect',original_connect)
    assert dump(path)==before
    SqliteRepository(path).close()
    with sqlite3.connect(path) as db: assert db.execute('PRAGMA user_version').fetchone()[0]==2

def test_fresh_profile_registers_identity_and_receipt_count_constraint(tmp_path):
    repo=SqliteRepository(tmp_path/'fresh.db')
    profile=repo.save_profile('Auditor')
    assert repo._connection.execute('SELECT id FROM auditor_identities').fetchone()[0]==profile.id
    with pytest.raises(sqlite3.IntegrityError):
        repo._connection.execute('INSERT INTO transfer_receipts VALUES (?,?,?,?,?)',(new_uuid(),'a'*64,new_uuid(),STAMP,-1))
    repo.close()

def test_legacy_offset_timestamps_keep_original_json(tmp_path):
    path=tmp_path/'offset.db'; legacy(path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE audit_records SET created_at=replace(created_at,'00:00:00+00:00','08:00:00+08:00'), updated_at=replace(updated_at,'00:00:00+00:00','08:00:00+08:00'), archived_at=replace(archived_at,'00:00:00+00:00','08:00:00+08:00')")
        db.execute("UPDATE audit_events SET before_json=replace(before_json,'00:00:00+00:00','08:00:00+08:00'), after_json=replace(after_json,'00:00:00+00:00','08:00:00+08:00')")
        snapshots=db.execute('SELECT before_json,after_json FROM audit_events ORDER BY revision').fetchall()
    repo=SqliteRepository(path)
    assert tuple(map(tuple,repo._connection.execute('SELECT before_json,after_json FROM audit_events ORDER BY revision')))==tuple(snapshots)
    repo.close()

@pytest.mark.parametrize('field,value', [('actor_profile_id',ACTOR),('actor_name','Incorrect origin')])
def test_migration_rejects_create_actor_mismatch_without_changes(tmp_path,field,value):
    path=tmp_path/'actor.db'; legacy(path)
    with sqlite3.connect(path) as db: db.execute(f'UPDATE audit_events SET {field}=? WHERE revision=1',(value,))
    before=dump(path)
    with pytest.raises(OfflineError): SqliteRepository(path)
    assert dump(path)==before


@pytest.mark.parametrize('damage',['noop','record','profile'])
def test_migration_rejects_invalid_normalization_and_noop_history(tmp_path,damage):
    path=tmp_path/'invalid.db'; legacy(path)
    with sqlite3.connect(path) as db:
        if damage=='record': db.execute("UPDATE audit_records SET driver_name=' Driver '")
        elif damage=='profile': db.execute("UPDATE local_profile SET name=' Renamed Auditor '")
        else:
            after=json.loads(db.execute('SELECT after_json FROM audit_events WHERE revision=2').fetchone()[0])
            after['archived_at']=None
            db.execute("UPDATE audit_events SET action='UPDATE',after_json=? WHERE revision=2",(json.dumps(after),))
            db.execute('UPDATE audit_records SET archived_at=NULL')
    before=dump(path)
    with pytest.raises(OfflineError): SqliteRepository(path)
    assert dump(path)==before


def test_migration_rejects_noncanonical_history_actor_without_changes(tmp_path):
    path = tmp_path/'actor-name.db'
    legacy(path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE audit_events SET actor_name=' Historical Auditor ' WHERE revision=2")
    before = dump(path)

    with pytest.raises(OfflineError) as caught:
        SqliteRepository(path)

    assert caught.value.code == 'corrupt'
    assert dump(path) == before
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert db.execute('SELECT actor_name FROM audit_events WHERE revision=2').fetchone()[0] == ' Historical Auditor '
