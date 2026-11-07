"""Read-only inspection of a separately built offline development APK."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


def inspect_source(entry, lib_root):
    """Follow project imports so shared widgets cannot pull in remote sessions."""
    lib_root = Path(lib_root).resolve()
    pending, seen = [Path(entry).resolve()], set()
    while pending:
        source = pending.pop()
        if source in seen:
            continue
        if not source.is_relative_to(lib_root):
            raise ValueError('Source import escapes application library')
        seen.add(source)
        text = source.read_text(encoding='utf-8-sig')
        for uri in re.findall(r"(?:import|export)\s+['\"]([^'\"]+)['\"]", text):
            if (uri.startswith('package:http/') or '/core/network/' in '/' + uri
                    or '/features/auth/' in '/' + uri):
                raise ValueError('Offline entry imports remote transport/authentication')
            if uri.startswith('package:bhli_audit/'):
                pending.append((lib_root / uri.removeprefix('package:bhli_audit/')).resolve())
            elif ':' not in uri:
                pending.append((source.parent / uri).resolve())
    return sorted(str(path.relative_to(lib_root)) for path in seen)


def inspect_candidate(apk, badging):
    match = re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging)
    if (not match or match.groups() != ('com.bhli.audit.offline', '2', '1.0.0-offline-dev')
            or 'application-debuggable' not in badging):
        raise ValueError('Unexpected offline identity/build')
    if re.search(r"uses-permission[^\n]*android\.permission\.(?:INTERNET|ACCESS_NETWORK_STATE|ACCESS_WIFI_STATE)", badging):
        raise ValueError('Offline candidate contains a network permission')
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate candidate payload')
        for name in names:
            path = PurePosixPath(name)
            if (path.is_absolute() or '..' in path.parts or '\\' in name
                    or path.name.startswith('.env') or 'fixtures' in path.parts
                    or path.suffix.lower() in
                    ('.db', '.sqlite', '.sqlite3', '.env', '.jks', '.keystore', '.pem', '.pfx', '.key',
                     '.bhlibackup', '.bhlitransfer')):
                raise ValueError('Private or populated database payload')
    return {'application_id': match[1], 'version_code': int(match[2]),
            'version': match[3], 'build_type': 'debug', 'production_ready': False,
            'sha256': hashlib.file_digest(Path(apk).open('rb'), 'sha256').hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', required=True, type=Path)
    parser.add_argument('--badging', required=True, type=Path)
    parser.add_argument('--entry', type=Path, default=Path('mobile/lib/main_offline.dart'))
    args = parser.parse_args()
    result = inspect_candidate(args.apk, args.badging.read_text(encoding='utf-8-sig'))
    result['source_imports'] = inspect_source(args.entry, Path('mobile/lib'))
    print(json.dumps(result, indent=2))
