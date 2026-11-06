"""Native ownership tests use only temporary fictional store directories."""
import os
import subprocess
import sys
import signal

import pytest

from desktop.offline.models import OfflineError


def test_lease_excludes_another_process_and_releases_after_owner_death(tmp_path):
    from desktop.offline.store_lease import StoreLease
    script = "from desktop.offline.store_lease import StoreLease; import os,sys; lease=StoreLease.acquire(sys.argv[1]); print(os.getpid(),flush=True); sys.stdin.read()"
    process = subprocess.Popen([sys.executable, '-c', script, str(tmp_path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        worker = int(process.stdout.readline())
        with pytest.raises(OfflineError) as error:
            StoreLease.acquire(tmp_path)
        assert error.value.code == 'store_owned'
    finally:
        os.kill(worker, signal.SIGTERM)
        process.wait(timeout=10)
    lease = StoreLease.acquire(tmp_path)
    assert lease.held
    lease.release()
    assert not lease.held


def test_lease_is_exclusive_in_same_process_and_keeps_lock_file(tmp_path):
    from desktop.offline.store_lease import StoreLease
    first = StoreLease.acquire(tmp_path)
    try:
        with pytest.raises(OfflineError):
            StoreLease.acquire(tmp_path)
    finally:
        first.release()
    second = StoreLease.acquire(tmp_path)
    second.release()
    second.release()
    assert (tmp_path / 'offline-store.lock').is_file()


def test_symlink_lock_is_refused_without_changing_target(tmp_path):
    from desktop.offline.store_lease import StoreLease
    target = tmp_path / 'fictional-target'
    target.write_bytes(b'preserve')
    try:
        os.symlink(target, tmp_path / 'offline-store.lock')
    except OSError:
        pytest.skip('OS account cannot create symlinks')
    with pytest.raises(OfflineError):
        StoreLease.acquire(tmp_path)
    assert target.read_bytes() == b'preserve'


def test_repository_retains_lease_until_close_and_failed_open_releases(tmp_path):
    from desktop.offline.store_lease import StoreLease
    from desktop.offline.repository import SqliteRepository
    lease = StoreLease.acquire(tmp_path)
    repo = SqliteRepository(tmp_path / 'fictional.db', lease=lease)
    assert lease.held
    repo.close()
    assert not lease.held
    (tmp_path / 'broken.db').write_bytes(b'fictional damaged data')
    lease = StoreLease.acquire(tmp_path)
    with pytest.raises(OfflineError):
        SqliteRepository(tmp_path / 'broken.db', lease=lease)
    assert not lease.held


def test_released_lease_cannot_open_database(tmp_path):
    from desktop.offline.store_lease import StoreLease
    from desktop.offline.repository import SqliteRepository
    lease = StoreLease.acquire(tmp_path)
    lease.release()
    with pytest.raises(OfflineError):
        SqliteRepository(tmp_path / 'must-not-exist.db', lease=lease)
    assert not (tmp_path / 'must-not-exist.db').exists()
