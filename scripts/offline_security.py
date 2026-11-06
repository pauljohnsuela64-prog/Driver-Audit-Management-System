"""Exact offline wheel runtime and native inventory; never import from online builds."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path


PINS = {'cryptography': '50.0.2', 'cffi': '2.1.1', 'pycparser': '3.12'}


def security_inventory(destination=None):
    for name, expected in PINS.items():
        if metadata.version(name) != expected:
            raise RuntimeError('Use the pinned offline security build overlay: ' + name)
    from cryptography.hazmat.backends.openssl.backend import backend
    from cryptography.hazmat.bindings import _rust
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
    from scripts.license_notices import verified_notices
    manifest, payloads = verified_notices('windows-offline-security')
    expected_sboms = {Path(name).name: hashlib.sha256(data).hexdigest()
                      for name, data in payloads if '/sboms/' in name}
    native_files = {}
    for wheel in manifest['wheels']:
        name = wheel['filename'].split('-')[0]
        dist = metadata.distribution(name)
        for record in wheel['native_files']:
            source = Path(dist.locate_file(record['path']))
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            if digest != record['sha256']:
                raise RuntimeError('Installed native security binary differs from reviewed wheel')
            native_files[record['path']] = digest
    # Exercise the fixed suite before starting a candidate build.
    Argon2id(salt=b'0' * 16, length=32, iterations=2, lanes=1,
             memory_cost=19456).derive(b'offline-build-capability-probe')
    openssl = backend.openssl_version_text()
    if openssl != 'OpenSSL 4.0.3 29 Sep 2026':
        raise RuntimeError('Unreviewed cryptography native OpenSSL runtime')
    dist = metadata.distribution('cryptography')
    sboms = []
    for entry in dist.files or []:
        if '/sboms/' not in str(entry).replace('\\', '/') or not str(entry).endswith('.json'):
            continue
        data = Path(dist.locate_file(entry)).read_bytes()
        json.loads(data)
        name = Path(entry).name
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_sboms.get(name):
            raise RuntimeError('Installed security SBOM differs from reviewed wheel')
        sboms.append({'path': name, 'sha256': digest})
        if destination is not None:
            target = Path(destination) / 'cryptography' / 'sboms' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    if {record['path'] for record in sboms} != {'sbom.json', 'cryptography-rust.cyclonedx.json'}:
        raise RuntimeError('Missing cryptography native dependency SBOMs')
    return dict(PINS, openssl=openssl, sboms=sboms, native_files=native_files,
                wheels=manifest['wheels'],
                native_binary_sha256=hashlib.sha256(Path(_rust.__file__).read_bytes()).hexdigest())
