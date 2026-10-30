"""Offline inclusion of reviewed third-party notices; never an application license grant."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

NOTICE_ROOT = Path(__file__).resolve().parents[1] / 'packaging' / 'notices'


def verified_notices(platform):
    if platform not in ('windows', 'android'):
        raise ValueError('Unknown notice platform')
    root = (NOTICE_ROOT / platform).resolve()
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    records = manifest['files']
    if not records:
        raise ValueError('Empty notice inventory')
    seen = set()
    payloads = []
    for record in records:
        name = record['path']
        relative = PurePosixPath(name)
        source = (root / name).resolve()
        if (not name or '\\' in name or ':' in name or relative.is_absolute()
                or '..' in relative.parts or name in seen
                or not source.is_relative_to(root)):
            raise ValueError('Unsafe or duplicate notice path')
        seen.add(name)
        if not source.is_file() or source.stat().st_size > 20 * 1024 * 1024:
            raise ValueError('Missing or oversized notice: ' + name)
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Modified notice: ' + name)
        payloads.append((name, data))
    if platform == 'android':
        assets = list((root / 'assets').rglob('*'))
        actual = {p.relative_to(root).as_posix() for p in assets if p.is_file()}
        if actual != seen or any(p.is_symlink() for p in assets):
            raise ValueError('Unreviewed Android notice asset')
    return manifest, payloads


def copy_verified_notices(platform, destination):
    manifest, payloads = verified_notices(platform)
    # Validate the whole source inventory before creating any output.
    for name, data in payloads:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (destination / 'NOTICE-PROVENANCE.json').write_text(
        json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest['files']


def verify_apk_notices(apk):
    manifest, payloads = verified_notices('android')
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        for name, data in payloads:
            if names.count(name) != 1 or archive.read(name) != data:
                raise ValueError('Missing or modified embedded notice: ' + name)
    return manifest['files']
