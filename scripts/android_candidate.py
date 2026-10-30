"""Build and inventory the ordinary internal/debug app; never a release signer."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

if __package__:
    from .license_notices import (verified_notices, verify_apk_notices,
                                 application_notices, verify_apk_application_notices)
else:
    from license_notices import (verified_notices, verify_apk_notices,
                                application_notices, verify_apk_application_notices)

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / 'mobile'
BUILD_ARGS = ['build', 'apk', '--debug', '--target', 'lib/main.dart']


def validate_badging(text):
    import re
    match = re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", text)
    if (not match or match.groups() != ('com.bhli.audit.mobile', '2', '1.0.0')
            or "minSdkVersion:'24'" not in text or 'application-debuggable' not in text):
        raise ValueError('Unexpected APK identity/build')


def apk_notices(apk):
    notices = []
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate APK entry')
        for item in archive.infolist():
            path = Path(item.filename)
            if (path.is_absolute() or '..' in path.parts
                    or path.name.startswith('.env')
                    or path.suffix.lower() in ('.jks', '.keystore', '.pfx', '.pem', '.key', '.db', '.sqlite3')
                    or 'integration_test' in item.filename.lower()):
                raise ValueError('Private/test payload in candidate')
            if path.name.upper().startswith(('LICENSE', 'NOTICE', 'COPYING')):
                if item.file_size > 20 * 1024 * 1024:
                    raise ValueError('Oversized notice')
                data = archive.read(item)
                if path.name == 'NOTICES.Z':
                    import io
                    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                        data = stream.read(20 * 1024 * 1024 + 1)
                    if len(data) > 20 * 1024 * 1024:
                        raise ValueError('Oversized expanded notice')
                notices.append((item.filename, data.decode('utf-8')))
        if not any(name.endswith('/NOTICES.Z') for name, _ in notices):
            raise ValueError('Flutter notices missing')
    return notices


def write_candidate(apk, output, sha, toolchain, dependencies, notices, observed=None,
                    supplemental=(), application=()):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Candidate output must be empty')
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(apk, output / 'app-debug.apk')
    text = '\n\n'.join(f'===== {name} =====\n{body}' for name, body in notices)
    notice_file = output / 'THIRD_PARTY_NOTICES.txt'
    notice_file.write_text(text, encoding='utf-8')
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = dict(source_sha=sha, application_id='com.bhli.audit.mobile',
                    version='1.0.0', version_code=2, build_type='debug',
                    production_signed=False, build_command=['flutter', *BUILD_ARGS],
                    private_defines=False, expected_toolchain=toolchain,
                    observed_toolchain=dict(observed or {}, java_sdk_selection='Verify against Gradle acceptance logs'),
                    dependencies=dependencies,
                    pubspec_lock_sha256=digest(MOBILE / 'pubspec.lock'),
                    apk_sha256=digest(output / 'app-debug.apk'),
                    notices_sha256=digest(notice_file),
                    supplemental_notices=list(supplemental),
                    application_license_notices=list(application),
                    notice_scope='Embedded APK notices plus resolved Dart/SDK and reviewed supplemental notices; not redistribution clearance')
    (output / 'BUILD-MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    hashes = {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output / 'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    return manifest


def build(flutter, output):
    from urllib.parse import urljoin, urlparse
    from urllib.request import url2pathname
    git = ['git', '-c', f'safe.directory={ROOT.as_posix()}']
    if subprocess.check_output([*git, 'status', '--porcelain'], cwd=ROOT).strip():
        raise SystemExit('Commit reviewed source before building candidates')
    if output.exists() and any(output.iterdir()):
        raise SystemExit('Candidate output must be empty')
    verified_notices('android')
    application_notices()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith('DAMS_') and k not in ('DART_DEFINES', 'FLUTTER_BUILD_ARGS')}
    sha = subprocess.check_output([*git, 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    actual = json.loads(subprocess.check_output([flutter, '--version', '--machine'], cwd=MOBILE, env=env))
    pinned = json.loads((MOBILE / 'toolchain.json').read_text())
    if actual['frameworkRevision'] != pinned['framework_revision'] or actual['dartSdkVersion'] != pinned['dart']:
        raise SystemExit('Unexpected Flutter/Dart toolchain')
    subprocess.run([flutter, *BUILD_ARGS], cwd=MOBILE, env=env, check=True)
    apk = MOBILE / 'build/app/outputs/flutter-apk/app-debug.apk'
    sdk = Path(env.get('ANDROID_HOME') or env.get('ANDROID_SDK_ROOT') or '')
    aapt = sdk / 'build-tools' / pinned['android_build_tools'] / ('aapt2.exe' if os.name == 'nt' else 'aapt2')
    badging = subprocess.check_output([str(aapt), 'dump', 'badging', str(apk)], text=True, encoding='utf-8')
    validate_badging(badging)
    supplemental = verify_apk_notices(apk)
    project_notices = verify_apk_application_notices(apk)
    notices = apk_notices(apk)
    existing = {name for name, _ in notices}
    # Include scope documents in the sidecar as well as the APK. LICENSE and
    # NOTICE are already collected by apk_notices; avoid duplicating them.
    for name, data in application_notices():
        entry = 'assets/application-license/' + name
        if entry not in existing:
            notices.append((entry, data.decode('utf-8')))
    deps = json.loads(subprocess.check_output([flutter, 'pub', 'deps', '--json'], cwd=MOBILE, env=env))
    versions = {p['name']: p['version'] for p in deps['packages']}
    config_path = MOBILE / '.dart_tool/package_config.json'
    packages = json.loads(config_path.read_text())['packages']
    flutter_package = next(p for p in packages if p['name'] == 'flutter')
    def package_root(package):
        uri = urlparse(urljoin(config_path.as_uri(), package['rootUri']))
        if uri.scheme != 'file':
            raise ValueError('Unexpected resolved package source')
        return Path(url2pathname(uri.path)).resolve()
    sdk_license = package_root(flutter_package).parents[1] / 'LICENSE'
    inventory = []
    for package in packages:
        folder = package_root(package)
        if folder == MOBILE:
            continue
        files = [p for p in folder.iterdir() if p.is_file()
                 and p.name.upper().startswith(('LICENSE', 'NOTICE', 'COPYING'))]
        if not files and folder.is_relative_to(sdk_license.parent):
            files = [sdk_license]
        if not files:
            raise ValueError('Resolved dependency has no verified license: ' + package['name'])
        entries = []
        for path in sorted(files):
            data = path.read_bytes()
            notices.append((package['name'] + '/' + path.name, data.decode('utf-8-sig')))
            entries.append(dict(name=path.name, sha256=hashlib.sha256(data).hexdigest()))
        inventory.append(dict(name=package['name'], version=versions.get(package['name']), notices=entries))
    observed = {k: actual[k] for k in ('frameworkVersion', 'frameworkRevision', 'dartSdkVersion', 'engineRevision')}
    observed['host_platform'] = __import__('platform').system()
    observed['apk_manifest_verified'] = True
    observed['aapt2_version'] = subprocess.check_output([str(aapt), 'version'], text=True).strip()
    result = write_candidate(apk, output, sha, pinned, inventory, notices, observed,
                             supplemental, project_notices)
    print(json.dumps(dict(source_sha=sha, version=result['version'], apk_sha256=result['apk_sha256'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flutter', default='flutter')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/android-candidate')
    args = parser.parse_args()
    build(args.flutter, args.output.resolve())
