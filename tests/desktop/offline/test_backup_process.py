"""Abrupt helper-process termination is not a physical power-cut guarantee."""
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
from concurrent.futures import ThreadPoolExecutor

import pytest

from desktop.offline.backup_state import capture_state
from desktop.offline.repository import SqliteRepository
from desktop.offline.store_lease import StoreLease


SCRIPT = r'''
import json, os, sqlite3, sys
from pathlib import Path
from desktop.offline.backup_jobs import BackupJobs
from desktop.offline.backup_store import BackupStore
from desktop.offline import backup_jobs, backup_store
from desktop.offline.backup_state import capture_state
from desktop.offline.repository import SqliteRepository
from desktop.offline.store_lease import StoreLease
from desktop.offline.models import new_uuid
root=Path(sys.argv[1]); stage=sys.argv[2]; journal=sys.argv[3]
password='fictional unique passphrase 123'
repo=SqliteRepository(root/'fictional.db',lease=StoreLease.acquire(root))
repo._connection.execute('PRAGMA journal_mode='+journal)
repo.save_profile('Incoming fictional auditor')
repo.create(new_uuid(),dict(driver_name='Fictional Driver',helper_name=None,audit_date='2026-11-06',station='Test',plate_number='0001',remarks=None))
jobs=BackupJobs(repo,root/'backup-recovery'); store=BackupStore(jobs)
source=root/'source.bhlibackup'; artifact=jobs.create(password); jobs.publish(artifact.id,source)
incoming=capture_state(repo).digest
repo.save_profile('Current fictional auditor'); original=capture_state(repo).digest
(root/'expected.json').write_text(json.dumps(dict(original=original,incoming=incoming)),encoding='utf-8')
def stop():
    print('checkpoint '+str(os.getpid()),flush=True)
    sys.stdin.read()
    raise RuntimeError('parent must terminate this helper')
preview=store.inspect_restore(source,password)
if stage=='plaintext-memory':
    backup_jobs.seal_backup=lambda *a,**kw: stop()
if stage=='recovery-published':
    publish=jobs.publish
    def publication(*a,**kw):
        result=publish(*a,**kw); stop(); return result
    jobs.publish=publication
ticket=store.prepare_restore(preview.id,password,root/'recovery.bhlibackup')
class Observed(sqlite3.Connection):
    def execute(self,sql,*args,**kwargs):
        if stage=='before-begin' and sql=='BEGIN IMMEDIATE': stop()
        result=super().execute(sql,*args,**kwargs)
        if stage=='after-deletes' and sql=='DELETE FROM app_meta': stop()
        if stage=='mid-insert' and sql.startswith('INSERT INTO audit_records '): stop()
        return result
repo._connection.close()
repo._connection=sqlite3.connect(root/'fictional.db',isolation_level=None,factory=Observed)
repo._connection.row_factory=sqlite3.Row
commit=backup_store._commit
def committing(db):
    if stage=='before-commit': stop()
    commit(db)
    if stage=='after-commit': stop()
backup_store._commit=committing
if stage=='before-marker-resolution': backup_store._resolve_marker=lambda *a: stop()
store.apply_restore(ticket)
raise RuntimeError('checkpoint was not reached')
'''


@pytest.mark.parametrize('journal', ['delete', 'wal'])
@pytest.mark.parametrize('stage,restored', [('plaintext-memory', False), ('recovery-published', False),
    ('before-begin', False), ('after-deletes', False), ('mid-insert', False), ('before-commit', False),
    ('after-commit', True), ('before-marker-resolution', True)])
def test_process_death_retains_exact_old_or_new_state_and_evidence(tmp_path, journal, stage, restored):
    from desktop.offline.backup_store import bootstrap_check, reconcile_startup
    process = subprocess.Popen([sys.executable, '-c', SCRIPT, str(tmp_path), stage, journal],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            line = executor.submit(process.stdout.readline).result(timeout=45)
        assert line.startswith('checkpoint '), process.stderr.read()
        # Windows venv python.exe is a launcher. Kill the actual lock-owning
        # interpreter announced by the helper, then wait for its launcher.
        os.kill(int(line.split()[1]), signal.SIGTERM)
        process.wait(timeout=15)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=15)
    expected = json.loads((tmp_path / 'expected.json').read_text(encoding='utf-8'))
    lease = StoreLease.acquire(tmp_path)
    directory = tmp_path / 'backup-recovery'
    bootstrap_check(tmp_path / 'fictional.db', directory)
    repo = SqliteRepository(tmp_path / 'fictional.db', lease=lease)
    try:
        result = reconcile_startup(repo, directory)
        if stage in ('plaintext-memory', 'recovery-published'):
            assert result is None
        else:
            assert result.outcome == ('RESTORED' if restored else 'ORIGINAL')
            assert len(list(directory.glob('backup-*.bhlibackup'))) >= 3
        assert capture_state(repo).digest == expected['incoming' if restored else 'original']
        assert repo._connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not repo._connection.execute('PRAGMA foreign_key_check').fetchall()
    finally:
        repo.close()
