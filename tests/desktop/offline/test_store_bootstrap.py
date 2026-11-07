"""Application opens SQLite only after acquiring lifetime directory ownership."""
import pytest

from desktop.offline.app import _repository
from desktop.offline.models import OfflineError
from desktop.offline.store_lease import StoreLease


def test_bootstrap_refuses_second_owner_and_releases_after_drained_close(tmp_path):
    path = tmp_path / 'fictional' / 'offline.db'
    first = _repository(path)
    try:
        with pytest.raises(OfflineError, match='other offline app'):
            _repository(path)
    finally:
        first.close()
    second = _repository(path)
    second.close()


def test_failed_bootstrap_preserves_corrupt_bytes_and_releases_owner(tmp_path):
    path = tmp_path / 'offline.db'
    damaged = b'fictional corrupt database - preserve for assisted recovery'
    path.write_bytes(damaged)
    with pytest.raises(OfflineError):
        _repository(path)
    assert path.read_bytes() == damaged
    lease = StoreLease.acquire(tmp_path)
    lease.release()


def test_pending_restore_never_initializes_a_missing_database(tmp_path):
    evidence = tmp_path / 'backup-recovery'
    evidence.mkdir()
    marker = evidence / 'restore-pending.json'
    marker.write_bytes(b'{}\n')
    path = tmp_path / 'offline.db'
    with pytest.raises(OfflineError):
        _repository(path)
    assert not path.exists()
    assert marker.read_bytes() == b'{}\n'
