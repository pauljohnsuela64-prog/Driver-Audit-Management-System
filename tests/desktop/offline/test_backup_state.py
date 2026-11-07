"""Complete fictional SQLite state, including raw historical strings."""
from dataclasses import replace
import json
import pytest
from desktop.offline.models import OfflineError,new_uuid
from desktop.offline.repository import SqliteRepository
from desktop.offline.backup_state import capture_state,encode_state,decode_state

VALUES=dict(driver_name='Fictional Driver',helper_name=None,audit_date='2026-11-06',station='Test',plate_number='00123',remarks='日本語 😀')

def test_empty_and_populated_state_roundtrip_preserves_every_owned_row(tmp_path):
    repo=SqliteRepository(tmp_path/'fictional.db')
    empty=capture_state(repo)
    assert empty.sequence is None and not empty.rows['audit_records']
    profile=repo.save_profile('Original fictional auditor')
    record=repo.create(new_uuid(),VALUES)
    repo.update(record.id,1,dict(VALUES,remarks='Changed fictional remark'))
    repo.archive(record.id,2)
    repo.save_profile('Current fictional auditor')
    repo._connection.execute('INSERT INTO auditor_identities VALUES (?)',(new_uuid(),))
    repo._connection.execute('INSERT INTO transfer_receipts VALUES (?,?,?,?,?)',(new_uuid(),'a'*64,new_uuid(),'2026-11-06T00:00:00.000000Z',1))
    repo._connection.execute("UPDATE sqlite_sequence SET seq=90 WHERE name='audit_records'")
    state=capture_state(repo)
    raw=encode_state(state.rows,platform='windows',sequence=state.sequence,backup_id=new_uuid(),created_at='2026-11-06T00:00:00.000000Z',source_version='test')
    decoded=decode_state(raw,platform='windows')
    assert decoded.digest==state.digest and decoded.sequence==90
    assert decoded.rows==state.rows
    assert decoded.rows['local_profile'][0]['id']==profile.id
    assert decoded.rows['audit_records'][0]['audited_by_name']=='Original fictional auditor'
    assert len(decoded.rows['audit_events'])==3 and len(decoded.rows['transfer_receipts'])==1
    assert len(decoded.rows['auditor_identities'])==2
    with pytest.raises(OfflineError): decode_state(raw,platform='android')
    repo.close()

def test_state_digest_ignores_backup_creation_metadata(tmp_path):
    repo=SqliteRepository(tmp_path/'fictional.db'); state=capture_state(repo)
    first=encode_state(state.rows,platform='windows',sequence=None,backup_id=new_uuid(),created_at='2026-11-06T00:00:00.000000Z',source_version='one')
    second=encode_state(state.rows,platform='windows',sequence=None,backup_id=new_uuid(),created_at='2026-11-07T00:00:00.000000Z',source_version='two')
    assert first!=second and decode_state(first,platform='windows').digest==decode_state(second,platform='windows').digest
    with pytest.raises(OfflineError): decode_state(first+b'{}\n',platform='windows')
    repo.close()

def test_invalid_history_and_unowned_schema_are_refused(tmp_path):
    repo=SqliteRepository(tmp_path/'fictional.db'); repo.save_profile('Fictional Auditor')
    repo.create(new_uuid(),VALUES)
    repo._connection.execute("UPDATE audit_events SET actor_name=' Invalid '")
    with pytest.raises(OfflineError): capture_state(repo)
    repo._connection.execute("UPDATE audit_events SET actor_name='Fictional Auditor'")
    repo._connection.execute('CREATE TABLE foreign_data(value TEXT)')
    with pytest.raises(OfflineError): capture_state(repo)
    repo.close()

@pytest.mark.parametrize('table,column,value', [('local_profile','name',123),('audit_records','driver_name',123),('audit_events','revision','1')])
def test_sqlite_coercion_does_not_accept_wrong_backup_column_types(tmp_path,table,column,value):
    repo=SqliteRepository(tmp_path/'fictional.db'); repo.save_profile('Fictional Auditor'); repo.create(new_uuid(),VALUES)
    state=capture_state(repo)
    rows={key:[dict(row) for row in items] for key,items in state.rows.items()}
    rows[table][0][column]=value
    with pytest.raises(OfflineError):
        encode_state(rows,platform='windows',sequence=state.sequence,backup_id=new_uuid(),created_at='2026-11-06T00:00:00.000000Z',source_version='test')
    repo.close()

def test_excessive_line_count_rejected_before_json_allocation(monkeypatch):
    from desktop.offline import backup_state
    def forbidden(*args,**kwargs): pytest.fail('Excessive row count reached JSON parsing')
    monkeypatch.setattr(backup_state,'_json',forbidden)
    with pytest.raises(OfflineError): decode_state(b'\n'*(sum(backup_state.CAPS.values())+3),platform='windows')

def test_accepted_legacy_offset_spellings_survive_complete_backup(tmp_path):
    from tests.desktop.offline.test_migration import legacy
    from contextlib import closing
    import sqlite3
    path=tmp_path/'legacy.db'; legacy(path)
    with closing(sqlite3.connect(path)) as db, db:
        for field in ('created_at','updated_at','archived_at'):
            db.execute('UPDATE audit_records SET '+field+'=replace('+field+",'00:00:00+00:00','08:00:00+08:00')")
    repo=SqliteRepository(path)  # Existing v1 migration accepts equal UTC instants.
    state=capture_state(repo)
    raw=encode_state(state.rows,platform='windows',sequence=state.sequence,backup_id=new_uuid(),created_at='2026-11-06T00:00:00.000000Z',source_version='test')
    restored=decode_state(raw,platform='windows')
    assert restored.rows==state.rows
    assert restored.rows['audit_records'][0]['created_at'].endswith('+08:00')
    assert '+00:00' in restored.rows['audit_events'][-1]['after_json']
    repo.close()

@pytest.mark.parametrize('version',['version\nspoof','version\u0085spoof'])
def test_source_version_cannot_inject_control_characters(tmp_path,version):
    repo=SqliteRepository(tmp_path/'fictional.db'); state=capture_state(repo)
    with pytest.raises(OfflineError):
        encode_state(state.rows,platform='windows',sequence=None,backup_id=new_uuid(),created_at='2026-11-06T00:00:00.000000Z',source_version=version)
    repo.close()

def test_decoded_rows_and_metadata_counts_are_immutable(tmp_path):
    repo=SqliteRepository(tmp_path/'fictional.db'); state=capture_state(repo)
    raw=encode_state(state.rows,platform='windows',sequence=None,backup_id=new_uuid(),created_at='2026-11-06T00:00:00.000000Z',source_version='test')
    decoded=decode_state(raw,platform='windows')
    with pytest.raises(TypeError): decoded.rows['app_meta'][0]['value']='changed'
    with pytest.raises(TypeError): decoded.metadata['counts']['audit_records']=99
    repo.close()

def test_malformed_row_kind_is_a_sanitized_state_failure(tmp_path):
    from desktop.offline.backup_state import canonical
    repo=SqliteRepository(tmp_path/'fictional.db'); state=capture_state(repo)
    raw=encode_state(state.rows,platform='windows',sequence=None,backup_id=new_uuid(),created_at='2026-11-06T00:00:00.000000Z',source_version='test')
    lines=raw.splitlines(keepends=True)
    row=json.loads(lines[1]); row['kind']=[]; lines[1]=canonical(row)+b'\n'
    with pytest.raises(OfflineError): decode_state(b''.join(lines),platform='windows')
    repo.close()
