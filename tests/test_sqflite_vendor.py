"""Offline preservation patch provenance; no toolchain or device required."""
import json
from pathlib import Path
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/sqflite_android'


def test_reviewed_same_version_sqlite_source_is_present():
    assert VENDOR.is_dir(), 'The reviewed preservation patch must be vendored, never applied to the SDK cache'
    from scripts.sqflite_vendor import verify_vendor
    result = verify_vendor()
    assert result['upstream']['version'] == '2.4.5'
    assert result['upstream']['archive_sha256'] == '3986f4cbdde19ca538aae877981c5a53400dcc4601499df18e7ed9e848a0bdd4'
    assert len(result['files']) == 61
    assert [entry['path'] for entry in result['files'] if entry['sha256'] != entry['upstream_sha256']] == [
        'android/src/main/java/com/tekartik/sqflite/Database.java'
    ]


@pytest.mark.parametrize('damage', ['changed_source', 'changed_license', 'missing', 'extra', 'traversal', 'duplicate', 'wrong_origin'])
def test_vendor_provenance_rejects_damaged_or_unreviewed_source(tmp_path, damage):
    from scripts.sqflite_vendor import verify_vendor
    target = tmp_path / 'vendor'
    shutil.copytree(VENDOR, target)
    manifest_path = target / 'BHLI-PROVENANCE.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if damage == 'changed_source':
        (target / 'lib/sqflite_android.dart').write_text('unreviewed', encoding='utf-8')
    elif damage == 'changed_license':
        (target / 'LICENSE').write_text('truncated', encoding='utf-8')
    elif damage == 'missing':
        (target / 'README.md').unlink()
    elif damage == 'extra':
        (target / 'unreviewed.java').write_text('new source', encoding='utf-8')
    elif damage == 'traversal':
        manifest['files'][0]['path'] = '../outside'
    elif damage == 'duplicate':
        manifest['files'].append(dict(manifest['files'][0]))
    else:
        manifest['upstream']['archive_sha256'] = '0' * 64
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='vendor|Vendor'):
        verify_vendor(target)


def test_embedded_patch_notice_matches_reviewed_vendor_notice():
    from scripts.license_notices import verified_notices
    _, entries = verified_notices('android')
    notices = dict(entries)
    assert notices['assets/compliance/NOTICE-SQFLITE-ANDROID-BHLI-PATCH.txt'] == (
        VENDOR / 'NOTICE-BHLI-SAFETY-PATCH.txt'
    ).read_bytes()
