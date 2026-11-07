"""Build an isolated offline development candidate; never install or read live DBs."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata as metadata
import json
import platform
import shutil
import sqlite3
import subprocess
import sys

from desktop.offline.identity import PRODUCT, VERSION, ARTIFACT_VERSION, APP_ID, INSTALLER_GUID
from scripts.build_windows import copy_notices
from scripts.license_notices import copy_verified_notices, copy_application_notices, verified_notices
from scripts.offline_security import security_inventory

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {'backend', 'database', 'migrations', 'tests', 'pytest', 'sqlalchemy',
             'pymysql', 'fastapi', 'uvicorn', 'dotenv'}
ONLINE_MODULES = {'desktop.api', 'desktop.session', 'desktop.app', 'desktop.tasks',
                  'desktop.config', 'desktop.account_operations', 'desktop.audit_actions',
                  'desktop.export_ui', 'desktop.reports', 'desktop.__main__'}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect_payload_files(bundle):
    for path in Path(bundle).rglob('*'):
        if path.is_symlink():
            raise RuntimeError('Private or unsafe payload link')
        if path.is_file() and (
            path.name.startswith('.env') or
            'fixtures' in path.relative_to(bundle).parts or
            path.suffix.lower() in {'.db', '.db3', '.sqlite', '.sqlite3', '.pem', '.pfx',
                                    '.key', '.jks', '.keystore', '.bhlibackup', '.bhlitransfer'} or
            path.name.lower().endswith(('-wal', '-shm', '-journal'))
        ):
            raise RuntimeError('Private key, configuration or database payload')


def inspect_bundle(bundle):
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(Path(bundle) / 'BHLIAuditOffline.exe'))
    modules = sorted(archive.open_embedded_archive('PYZ.pyz').toc)
    unexpected = [name for name in modules if name.split('.')[0].lower() in FORBIDDEN or
                  any(name == prefix or name.startswith(prefix + '.') for prefix in ONLINE_MODULES)]
    if unexpected:
        raise RuntimeError('Online/server/test modules in offline candidate: ' + ', '.join(unexpected))
    required = {'sqlite3', 'desktop.offline.repository', 'desktop.offline.backup_crypto',
                'cryptography', 'cryptography.hazmat.primitives.kdf.argon2',
                'cryptography.hazmat.primitives.ciphers.aead'}
    if not required.issubset(modules):
        raise RuntimeError('Offline SQLite/security implementation missing from candidate')
    native = list(Path(bundle).rglob('_rust.pyd'))
    if len(native) != 1:
        raise RuntimeError('Offline native cryptography implementation missing from candidate')
    if digest(native[0]) != security_inventory()['native_binary_sha256']:
        raise RuntimeError('Unexpected bundled cryptography native binary')
    security = security_inventory()
    for name, expected in security['native_files'].items():
        files = list(Path(bundle).rglob(Path(name).name))
        if len(files) != 1 or digest(files[0]) != expected:
            raise RuntimeError('Missing or modified offline native security dependency')
    inspect_payload_files(bundle)
    return modules


def build(iscc, output_root):
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('Offline development packaging requires Windows x64')
    if sys.version_info[:3] != (3, 14, 10) or metadata.version('pyinstaller') != '6.22.3':
        raise SystemExit('Use Python 3.14.10 / PyInstaller 6.22.3 in .venv-offline-build')
    if Path(sys.prefix).resolve() != (ROOT / '.venv-offline-build').resolve():
        raise SystemExit('Use the separate .venv-offline-build with requirements-offline-build.lock')
    security_inventory()
    verified_notices('windows-offline-security')
    output = Path(output_root).resolve()
    if not output.is_relative_to((ROOT / 'dist').resolve()) or output == (ROOT / 'dist').resolve():
        raise SystemExit('Use a fresh isolated subdirectory of repository dist')
    if output.exists() and any(output.iterdir()):
        raise SystemExit('Output must be empty; preserve all existing candidates')
    git = ['git', '-c', f'safe.directory={ROOT.as_posix()}']
    if subprocess.check_output(git + ['status', '--porcelain'], cwd=ROOT, text=True):
        raise SystemExit('Commit reviewed source before building candidates')
    source_sha = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'pip', 'check'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--distpath', str(output), '--workpath', str(output / 'work'),
                    str(ROOT / 'packaging/windows/BHLIAuditOffline.spec')], cwd=ROOT, check=True)
    bundle = output / 'BHLIAuditOffline'
    modules = inspect_bundle(bundle)
    licenses = bundle / 'THIRD_PARTY_LICENSES'
    licenses.mkdir(exist_ok=True)
    security = security_inventory(licenses)
    dependencies = []
    for dist in metadata.distributions():
        dependencies.append({'name': dist.metadata['Name'], 'version': dist.version})
        copy_notices(dist, licenses)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('CPython composite license missing')
    shutil.copyfile(python_license, licenses / 'CPython-LICENSE.txt')
    supplemental = copy_verified_notices('windows', licenses / 'SUPPLEMENTAL')
    security_notices = copy_verified_notices('windows-offline-security', licenses / 'OFFLINE-SECURITY')
    application = copy_application_notices(bundle)
    sqlite_dlls = list(bundle.rglob('sqlite3.dll'))
    runtime_dll = Path(sys.base_prefix) / 'DLLs/sqlite3.dll'
    if len(sqlite_dlls) != 1 or not runtime_dll.is_file() or digest(sqlite_dlls[0]) != digest(runtime_dll):
        raise RuntimeError('Unexpected bundled SQLite native binary')
    manifest = dict(product=PRODUCT, version=VERSION, application_id=APP_ID,
                    installer_guid=INSTALLER_GUID, source_sha=source_sha,
                    python=platform.python_version(), sqlite=sqlite3.sqlite_version,
                    sqlite_dll_sha256=digest(sqlite_dlls[0]), signed_release=False,
                    fictional_development_only=True, database_bundled=False,
                    modules=modules, offline_security=security,
                    build_environment_dependencies=sorted(dependencies, key=lambda d: d['name'].lower()),
                    supplemental_notices=supplemental, application_license_notices=application)
    manifest['offline_security_notices'] = security_notices
    (bundle / 'BUILD-MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    subprocess.run([str(Path(iscc).resolve()), '/DBundleDir=' + str(bundle),
                    '/DOutputDir=' + str(output / 'installer'),
                    str(ROOT / 'packaging/windows/offline_installer.iss')], cwd=ROOT, check=True)
    installers = sorted((output / 'installer').glob('*.exe'))
    expected = output / 'installer' / f'BHLI-Audit-Offline-Setup-{ARTIFACT_VERSION}-x64.exe'
    if installers != [expected]:
        raise RuntimeError('Unexpected offline installer inventory')
    archive = Path(shutil.make_archive(str(output / f'BHLI-Audit-Offline-Windows-{ARTIFACT_VERSION}-x64'),
                                     'zip', output, 'BHLIAuditOffline'))
    inspect_payload_files(bundle)
    hashes = {str(p.relative_to(output)): digest(p) for p in bundle.rglob('*') if p.is_file()}
    hashes.update({str(p.relative_to(output)): digest(p) for p in [archive, expected]})
    (output / 'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print(json.dumps({'source_sha': source_sha, 'bundle': str(bundle), 'installer': str(expected),
                      'archive': str(archive), 'signed_release': False, 'fictional_development_only': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iscc', required=True)
    parser.add_argument('--output-root', required=True, type=Path)
    args = parser.parse_args()
    build(args.iscc, args.output_root)
