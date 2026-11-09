"""Guard actual offline candidate metadata and reject bundled user databases."""
import zipfile

import pytest


BADGING = """package: name='com.bhli.audit.offline' versionCode='2' versionName='1.0.0-offline-dev'
sdkVersion:'24'
targetSdkVersion:'36'
application-debuggable
"""


def test_online_builder_selects_online_flavor_explicitly():
    from scripts.android_candidate import BUILD_ARGS
    assert BUILD_ARGS == ['build', 'apk', '--debug', '--flavor', 'online', '--target', 'lib/main.dart']


def test_offline_import_graph_rejects_transitive_transport(tmp_path):
    from scripts.offline_android import inspect_source
    lib = tmp_path / 'lib'
    lib.mkdir()
    (lib / 'main_offline.dart').write_text("import 'app.dart';")
    (lib / 'app.dart').write_text("import 'package:flutter/material.dart';")
    assert len(inspect_source(lib / 'main_offline.dart', lib)) == 2
    (lib / 'app.dart').write_text("import 'package:http/http.dart';")
    with pytest.raises(ValueError, match='transport'):
        inspect_source(lib / 'main_offline.dart', lib)


def test_offline_candidate_accepts_only_its_separate_identity(tmp_path):
    from scripts.offline_android import inspect_candidate
    apk = tmp_path / 'offline.apk'
    with zipfile.ZipFile(apk, 'w') as archive:
        archive.writestr('assets/flutter_assets/ordinary-asset', 'client only')
    assert inspect_candidate(apk, BADGING)['application_id'] == 'com.bhli.audit.offline'
    for old, new in [('com.bhli.audit.offline', 'com.bhli.audit.mobile'),
                     ('1.0.0-offline-dev', '1.0.0'), ('application-debuggable', '')]:
        with pytest.raises(ValueError, match='identity'):
            inspect_candidate(apk, BADGING.replace(old, new))


@pytest.mark.parametrize('permission', ['INTERNET', 'ACCESS_NETWORK_STATE', 'ACCESS_WIFI_STATE'])
def test_offline_candidate_rejects_network_permissions(tmp_path, permission):
    from scripts.offline_android import inspect_candidate
    apk = tmp_path / 'offline.apk'
    with zipfile.ZipFile(apk, 'w') as archive:
        archive.writestr('ordinary', '')
    with pytest.raises(ValueError, match='network'):
        inspect_candidate(apk, BADGING + f"uses-permission: name='android.permission.{permission}'\n")


@pytest.mark.parametrize('name', ['assets/demo.db', 'assets/user.sqlite', 'assets/data.sqlite3',
                                 'assets/server.env', 'assets/.env', 'secret.jks', '../private',
                                 'assets/copy.bhlibackup', 'assets/copy.bhlitransfer',
                                 'assets/flutter_assets/fixtures/backup/vector.json'])
def test_offline_candidate_rejects_private_or_populated_payload(tmp_path, name):
    from scripts.offline_android import inspect_candidate
    apk = tmp_path / 'offline.apk'
    with zipfile.ZipFile(apk, 'w') as archive:
        archive.writestr(name, 'not for distribution')
    with pytest.raises(ValueError, match='payload'):
        inspect_candidate(apk, BADGING)


RELEASE_BADGING = BADGING.replace("versionCode='2'", "versionCode='3'").replace(
    "versionName='1.0.0-offline-dev'", "versionName='1.0.0'").replace('application-debuggable', '')


def test_release_inspection_is_explicit_and_does_not_imply_signature_acceptance(tmp_path):
    from scripts.offline_android import inspect_candidate
    apk = tmp_path / 'offline-release.apk'
    with zipfile.ZipFile(apk, 'w') as archive:
        archive.writestr('assets/ordinary', 'no user data')
    result = inspect_candidate(apk, RELEASE_BADGING, release=True)
    assert result['version_code'] == 3 and result['version'] == '1.0.0'
    assert result['build_type'] == 'release'
    assert result['production_ready'] is False
    assert result['signature_verified'] is False
    with pytest.raises(ValueError, match='identity'):
        inspect_candidate(apk, RELEASE_BADGING)


@pytest.mark.parametrize('badging', [BADGING, RELEASE_BADGING + 'application-debuggable',
    RELEASE_BADGING.replace("versionCode='3'", "versionCode='2'"),
    RELEASE_BADGING.replace('com.bhli.audit.offline', 'com.bhli.audit.mobile')])
def test_release_inspection_rejects_debug_stale_or_online_metadata(tmp_path, badging):
    from scripts.offline_android import inspect_candidate
    apk = tmp_path / 'candidate.apk'
    with zipfile.ZipFile(apk, 'w'):
        pass
    with pytest.raises(ValueError, match='identity'):
        inspect_candidate(apk, badging, release=True)


@pytest.mark.parametrize('extra', ['network', 'database'])
def test_release_inspection_preserves_network_and_private_data_rejection(tmp_path, extra):
    from scripts.offline_android import inspect_candidate
    apk = tmp_path / 'candidate.apk'
    with zipfile.ZipFile(apk, 'w') as archive:
        if extra == 'database':
            archive.writestr('assets/user.db', 'never distribute')
    badging = RELEASE_BADGING + ("uses-permission: name='android.permission.INTERNET'" if extra == 'network' else '')
    with pytest.raises(ValueError, match='network|payload'):
        inspect_candidate(apk, badging, release=True)
