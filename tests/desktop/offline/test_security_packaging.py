"""Offline dependency closure and rejection of generated backup payloads."""
from pathlib import Path

import pytest


def test_security_overlay_preserves_online_build_closure():
    security = Path('requirements-offline-security.lock').read_text()
    assert 'cryptography==50.0.2 --hash=sha256:7afa5a' in security
    assert 'cffi==2.1.1 --hash=sha256:3222ba' in security
    assert 'pycparser==3.12 --hash=sha256:a076f3' in security
    assert Path('requirements-offline-build.lock').read_text().splitlines()[-2:] == [
        '-r requirements-build.lock', '-r requirements-offline-security.lock']
    assert 'cryptography' not in Path('requirements-build.lock').read_text()


@pytest.mark.parametrize('name', ['saved.bhlibackup', 'copy.bhlitransfer',
                                'fixtures/backup/vector.json'])
def test_windows_inspector_rejects_backup_transfer_and_fixture_assets(tmp_path, name):
    from scripts.build_windows_offline import inspect_payload_files
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'fictional')
    with pytest.raises(RuntimeError, match='payload'):
        inspect_payload_files(tmp_path)


def test_security_inventory_records_installed_native_binary_and_both_sboms():
    from scripts.offline_security import security_inventory
    inventory = security_inventory()
    assert inventory['openssl'] == 'OpenSSL 4.0.3 29 Sep 2026'
    assert inventory['cryptography'] == '50.0.2'
    assert len(inventory['sboms']) == 2
    assert len(inventory['native_binary_sha256']) == 64


def test_offline_native_notices_cover_wheel_sbom_and_are_copied(tmp_path):
    from scripts.license_notices import copy_verified_notices
    records = copy_verified_notices('windows-offline-security', tmp_path)
    paths = {record['path'] for record in records}
    assert 'openssl-4.0.3/LICENSE.txt' in paths
    assert 'unicode-ident-1.0.24/LICENSE-UNICODE' in paths
    assert 'self_cell-1.3.0/LICENSE-APACHE' in paths
    assert any(name.startswith('cffi-2.1.1-native/') for name in paths)
    assert (tmp_path / 'NOTICE-PROVENANCE.json').is_file()


def test_offline_native_notices_reject_unreviewed_extra_file(tmp_path, monkeypatch):
    import hashlib
    import json
    from scripts import license_notices
    root = tmp_path / 'windows-offline-security'
    root.mkdir()
    (root / 'LICENSE').write_bytes(b'fictional license')
    (root / 'manifest.json').write_text(json.dumps({'files': [dict(
        path='LICENSE', sha256=hashlib.sha256(b'fictional license').hexdigest())]}))
    (root / 'unreviewed.txt').write_text('unexpected')
    monkeypatch.setattr(license_notices, 'NOTICE_ROOT', tmp_path)
    with pytest.raises(ValueError, match='Unreviewed'):
        license_notices.verified_notices('windows-offline-security')
