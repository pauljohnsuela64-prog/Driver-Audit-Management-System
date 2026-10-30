"""Cross-surface release identity and narrow candidate publication contracts."""
from pathlib import Path
import json
import zipfile
import gzip
import hashlib
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_candidate_versions_and_identities_are_consistent():
    from desktop.version import VERSION, APP_ID
    assert VERSION == '1.0.0'
    assert APP_ID == 'BHLI.Audit.Desktop'
    pe = (ROOT/'packaging/windows/version_info.txt').read_text()
    assert 'filevers=(1,0,0,0)' in pe and 'prodvers=(1,0,0,0)' in pe
    assert "'FileVersion','1.0.0'" in pe and "'ProductVersion','1.0.0'" in pe
    installer = (ROOT/'packaging/windows/installer.iss').read_text()
    assert '#define AppVersion "1.0.0"' in installer
    assert 'AppId={{C9470975-3249-43C2-A410-80972C956B05}' in installer
    assert 'Local\\BHLI.Audit.Desktop.Running' in installer
    assert 'version: 1.0.0+2' in (ROOT/'mobile/pubspec.yaml').read_text()
    gradle = (ROOT/'mobile/android/app/build.gradle.kts').read_text()
    assert 'applicationId = "com.bhli.audit.mobile"' in gradle
    assert 'namespace = "com.bhli.audit.mobile"' in gradle and 'minSdk = 24' in gradle
    assert 'version="0.2.0"' in (ROOT/'backend/main.py').read_text()
    assert 'BHLI-Audit-Setup-1.0.0-x64.exe' in (ROOT/'.github/workflows/backend-tests.yml').read_text()


def test_android_candidate_upload_excludes_test_configuration():
    from scripts.android_candidate import BUILD_ARGS
    workflow = (ROOT/'.github/workflows/mobile-tests.yml').read_text()
    assert 'permissions:\n  contents: read' in workflow
    assert BUILD_ARGS == ['build', 'apk', '--debug', '--target', 'lib/main.dart']
    assert 'run: python3 ../scripts/android_candidate.py' in workflow
    upload = workflow.split('- name: Retain internal debug candidate\n', 1)[1]
    assert 'retention-days: 14' in upload
    paths = re.search(r'          path: \|\n((?:            [^\n]+\n)+)', upload)
    assert paths and [p.strip() for p in paths[1].splitlines()] == [
        'artifacts/android-candidate/app-debug.apk',
        'artifacts/android-candidate/BUILD-MANIFEST.json',
        'artifacts/android-candidate/SHA256SUMS.json',
        'artifacts/android-candidate/THIRD_PARTY_NOTICES.txt']
    assert 'pull_request_target' not in workflow and '--dart-define' not in workflow
    assert 'ref: ${{ github.event.pull_request.head.sha || github.sha }}' in workflow


def test_candidate_inventory_rejects_stale_installer(tmp_path):
    from scripts.build_windows import candidate_installers
    (tmp_path/'BHLI-Audit-Setup-1.0.0-x64.exe').write_bytes(b'new')
    assert candidate_installers(tmp_path) == [tmp_path/'BHLI-Audit-Setup-1.0.0-x64.exe']
    (tmp_path/'BHLI-Audit-Setup-0.3.0-x64.exe').write_bytes(b'old')
    with pytest.raises(RuntimeError, match='Unexpected installer'):
        candidate_installers(tmp_path)


@pytest.mark.parametrize('outside', [False, True])
def test_windows_output_guard_preserves_existing_files(tmp_path, monkeypatch, outside):
    from scripts import build_windows as builder
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    monkeypatch.setattr(builder.sys, 'platform', 'win32')
    monkeypatch.setattr(builder.platform, 'machine', lambda: 'AMD64')
    output = tmp_path / ('outside' if outside else 'dist/candidate')
    output.mkdir(parents=True)
    sentinel = output/'owned-file.txt'; sentinel.write_text('preserve')
    with pytest.raises(SystemExit, match='inside|empty'):
        builder.build('unused-compiler', output)
    assert sentinel.read_text() == 'preserve'


def test_apk_notices_preserve_flutter_and_native_licenses(tmp_path):
    from scripts.android_candidate import apk_notices
    apk = tmp_path/'app.apk'
    with zipfile.ZipFile(apk, 'w') as z:
        z.writestr('assets/flutter_assets/NOTICES.Z', gzip.compress(b'Flutter notice'))
        z.writestr('META-INF/androidx/LICENSE.txt', 'Native notice')
    assert apk_notices(apk) == [('assets/flutter_assets/NOTICES.Z', 'Flutter notice'),
                                ('META-INF/androidx/LICENSE.txt', 'Native notice')]


@pytest.mark.parametrize('name', ['assets/.env', 'private.jks', '../LICENSE', 'assets/integration_test/data'])
def test_apk_private_payload_is_rejected(tmp_path, name):
    from scripts.android_candidate import apk_notices
    apk = tmp_path/'app.apk'
    with zipfile.ZipFile(apk, 'w') as z:
        z.writestr('assets/flutter_assets/NOTICES.Z', gzip.compress(b'notice'))
        z.writestr(name, 'fixture')
    with pytest.raises(ValueError, match='Private/test'):
        apk_notices(apk)


def test_candidate_checksums_match_actual_bytes_and_refuse_overwrite(tmp_path, monkeypatch):
    from scripts import android_candidate as candidate
    apk = tmp_path/'app.apk'; apk.write_bytes(b'fictional apk fixture')
    mobile = tmp_path/'mobile'; mobile.mkdir(); (mobile/'pubspec.lock').write_text('fixture')
    monkeypatch.setattr(candidate, 'MOBILE', mobile)
    output = tmp_path/'candidate'
    candidate.write_candidate(apk, output, 'a'*40, {'flutter': 'fixture'}, [], [('LICENSE', 'notice')])
    hashes = json.loads((output/'SHA256SUMS.json').read_text())
    manifest = json.loads((output/'BUILD-MANIFEST.json').read_text())
    assert 'expected_toolchain' in manifest and 'observed_toolchain' in manifest
    assert manifest['observed_toolchain']['java_sdk_selection'] == 'Verify against Gradle acceptance logs'
    assert set(hashes) == {'app-debug.apk', 'BUILD-MANIFEST.json', 'THIRD_PARTY_NOTICES.txt'}
    assert all(hashlib.sha256((output/name).read_bytes()).hexdigest() == value for name,value in hashes.items())
    with pytest.raises(ValueError, match='empty'):
        candidate.write_candidate(apk, output, 'a'*40, {}, [], [])


@pytest.mark.parametrize('old,new', [('versionCode=\'2\'', 'versionCode=\'1\''),
                                   ("name='com.bhli.audit.mobile'", "name='wrong.app'"),
                                   ('application-debuggable', '')])
def test_android_candidate_rejects_wrong_actual_manifest(old, new):
    from scripts.android_candidate import validate_badging
    valid = "package: name='com.bhli.audit.mobile' versionCode='2' versionName='1.0.0'\nminSdkVersion:'24'\napplication-debuggable\n"
    validate_badging(valid)
    with pytest.raises(ValueError, match='identity/build'):
        validate_badging(valid.replace(old, new))
