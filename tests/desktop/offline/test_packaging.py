"""Separate offline identity and development-only packaging; no installations."""
import importlib.util
from pathlib import Path

import pytest


def test_offline_data_path_is_separate_absolute_and_does_not_create_data(tmp_path):
    from desktop.offline.identity import database_path
    expected = tmp_path / 'BHLI Audit Offline' / 'bhli_offline.db'
    assert database_path({'LOCALAPPDATA': str(tmp_path)}) == expected
    assert not expected.parent.exists()
    assert 'BHLI Audit/settings.json' not in str(expected)


@pytest.mark.parametrize('env', [{}, {'LOCALAPPDATA': ''}, {'LOCALAPPDATA': 'relative'}])
def test_missing_or_relative_data_location_never_falls_back_to_install_folder(env):
    from desktop.offline.identity import database_path
    with pytest.raises(ValueError, match='data folder'):
        database_path(env)


def test_offline_installation_identity_cannot_replace_online_edition():
    from desktop.offline.identity import APP_ID, MUTEX, INSTALLER_GUID, PRODUCT
    from desktop.version import APP_ID as ONLINE_APP_ID
    assert PRODUCT == 'BHLI Audit Offline' and APP_ID != ONLINE_APP_ID
    assert MUTEX == 'Local\\BHLI.Audit.Offline.Desktop.Running'
    script = Path('packaging/windows/offline_installer.iss').read_text()
    assert INSTALLER_GUID in script and 'C9470975-3249-43C2-A410-80972C956B05' not in script
    assert 'Programs\\BHLI Audit Offline' in script and 'BHLIAuditOffline.exe' in script
    assert '[UninstallDelete]' not in script and 'bhli_offline.db' not in script
    assert 'PrivilegesRequired=lowest' in script and 'CloseApplications=no' in script
    assert 'BHLI Audit Offline' in script and MUTEX in script


def test_offline_build_has_separate_entry_and_excludes_server_and_fixture_modules():
    spec = Path('packaging/windows/BHLIAuditOffline.spec').read_text()
    assert 'offline_entry.py' in spec and "name='BHLIAuditOffline'" in spec
    assert 'console=False' in spec and 'upx=False' in spec and 'uac_admin=False' in spec
    assert 'collect_data_files' in spec and 'desktop.api' in spec and 'desktop.session' in spec
    assert 'backend' in spec and 'tests' in spec and 'desktop.reports' in spec
    assert 'bhli_offline.db' not in spec


def test_bundle_inspector_rejects_database_and_signing_files(tmp_path):
    from scripts.build_windows_offline import inspect_payload_files
    (tmp_path / 'bhli_offline.db').write_bytes(b'SQLite format 3')
    with pytest.raises(RuntimeError, match='Private|database'):
        inspect_payload_files(tmp_path)
    (tmp_path / 'bhli_offline.db').unlink()
    (tmp_path / 'signing.keystore').write_text('fixture only')
    with pytest.raises(RuntimeError, match='Private|database'):
        inspect_payload_files(tmp_path)


def test_bundle_inspector_accepts_no_preloaded_data(tmp_path):
    from scripts.build_windows_offline import inspect_payload_files
    (tmp_path / 'BHLIAuditOffline.exe').write_bytes(b'fictional contract fixture')
    inspect_payload_files(tmp_path)


def test_frozen_offline_failure_is_sanitized_and_distinct(monkeypatch):
    spec = importlib.util.spec_from_file_location('offline_frozen_entry', 'packaging/windows/offline_entry.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    seen = []
    monkeypatch.setattr(module, 'start', lambda: (_ for _ in ()).throw(ValueError('private fixture path')))
    monkeypatch.setattr(module, 'show_error', lambda: seen.append(True))
    assert module.run() == 1 and seen == [True]

