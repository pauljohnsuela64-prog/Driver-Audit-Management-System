"""Verify the reviewed same-version Android preservation patch, without tooling."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/sqflite_android'
MANIFEST_SHA256 = '80c4858b5d4cd8b82be809a3017cad02ce5d044b2715a5251c37e126960ab5f8'
ARCHIVE_SHA256 = '3986f4cbdde19ca538aae877981c5a53400dcc4601499df18e7ed9e848a0bdd4'
LICENSE_SHA256 = 'c81f9454cf3107c116bc3c1fd22b7d751523a2b11e17cf90c0db3327d3c9e0da'
PATCH_FILE = 'android/src/main/java/com/tekartik/sqflite/Database.java'
EXTRA_FILES = {'BHLI-PROVENANCE.json', 'NOTICE-BHLI-SAFETY-PATCH.txt'}


def _need(condition):
    if not condition:
        raise ValueError('Unreviewed or damaged SQLite vendor provenance')


def verify_vendor(directory=VENDOR):
    """Return authenticated inventory only after all source and notice checks."""
    root = Path(directory)
    _need(root.is_dir() and not root.is_symlink())
    manifest_path = root / 'BHLI-PROVENANCE.json'
    _need(manifest_path.is_file() and manifest_path.stat().st_size <= 64 * 1024)
    data = manifest_path.read_bytes()
    _need(hashlib.sha256(data).hexdigest() == MANIFEST_SHA256)
    manifest = json.loads(data)
    _need(manifest['format'] == 1)
    upstream = manifest['upstream']
    _need(upstream['name'] == 'sqflite_android' and upstream['version'] == '2.4.5')
    _need(upstream['archive_sha256'] == ARCHIVE_SHA256)
    _need(upstream['archive_url'] == 'https://pub.dev/api/archives/sqflite_android-2.4.5.tar.gz')
    _need(upstream['license'] == 'BSD-2-Clause' and upstream['license_sha256'] == LICENSE_SHA256)
    _need(manifest['patch']['file'] == PATCH_FILE)
    entries = manifest['files']
    _need(len(entries) == 61)
    seen = set()
    modified = []
    for entry in entries:
        name = entry['path']
        path = PurePosixPath(name)
        _need(name and '\\' not in name and ':' not in name and not path.is_absolute())
        _need('..' not in path.parts and name not in seen)
        _need(all(re.fullmatch('[0-9a-f]{64}', entry[key]) for key in ('sha256', 'upstream_sha256')))
        seen.add(name)
        source = root / name
        _need(source.is_file() and not source.is_symlink() and source.stat().st_size <= 1024 * 1024)
        _need(hashlib.sha256(source.read_bytes()).hexdigest() == entry['sha256'])
        if entry['sha256'] != entry['upstream_sha256']:
            modified.append(name)
    _need(modified == [PATCH_FILE])
    _need(hashlib.sha256((root / 'LICENSE').read_bytes()).hexdigest() == LICENSE_SHA256)
    all_paths = list(root.rglob('*'))
    _need(not any(path.is_symlink() for path in all_paths))
    _need({path.relative_to(root).as_posix() for path in all_paths if path.is_file()} == seen | EXTRA_FILES)
    notice = root / 'NOTICE-BHLI-SAFETY-PATCH.txt'
    _need(notice.stat().st_size <= 64 * 1024)
    _need(hashlib.sha256(notice.read_bytes()).hexdigest() == manifest['patch']['notice_sha256'])
    return manifest


if __name__ == '__main__':
    result = verify_vendor()
    print(json.dumps({'package': result['upstream']['name'],
                      'version': result['upstream']['version'],
                      'source_files': len(result['files']),
                      'provenance_sha256': MANIFEST_SHA256}))
