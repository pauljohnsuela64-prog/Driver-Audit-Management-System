"""Repeatable client-only Windows build; never loads dotenv or database configuration."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata as metadata
import json
import platform
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN={'backend','database','migrations','scripts','tests','pytest','sqlalchemy','pymysql','fastapi','uvicorn','dotenv'}


def inspect_bundle(bundle):
    from PyInstaller.archive.readers import CArchiveReader
    archive=CArchiveReader(str(bundle/'BHLIAudit.exe'))
    modules=archive.open_embedded_archive('PYZ.pyz').toc
    unexpected=sorted(name for name in modules if name.split('.')[0].lower() in FORBIDDEN)
    if unexpected:raise RuntimeError('Forbidden client modules: '+','.join(unexpected))
    for path in bundle.rglob('*'):
        if path.is_file() and (path.name.startswith('.env') or path.suffix.lower() in ('.pfx','.pem','.key','.db','.sqlite3')):
            raise RuntimeError('Private configuration or data found in bundle')
    return sorted(modules)


def build(iscc):
    if sys.platform!='win32' or platform.machine().upper() not in ('AMD64','X86_64'):
        raise SystemExit('Build requires Windows x64')
    if sys.version_info[:2]!=(3,14):raise SystemExit('Build requires Python 3.14')
    subprocess.run([sys.executable,'-m','pip','check'],check=True,cwd=ROOT)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',str(ROOT/'packaging/windows/BHLIAudit.spec')],check=True,cwd=ROOT)
    bundle=ROOT/'dist/BHLIAudit';modules=inspect_bundle(bundle)
    licenses=bundle/'THIRD_PARTY_LICENSES';licenses.mkdir(exist_ok=True)
    dependencies=[]
    for dist in metadata.distributions():
        name=dist.metadata['Name'];dependencies.append({'name':name,'version':dist.version})
        for file in dist.files or []:
            if 'licen' in Path(file).name.lower() or Path(file).name.lower()=='copying':
                source=Path(dist.locate_file(file))
                if source.is_file():
                    target=licenses/name/Path(file).name;target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source,target)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.is_file():shutil.copyfile(python_license,licenses/'CPython-LICENSE.txt')
    source_sha=subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    manifest={'source_sha':source_sha,'python':platform.python_version(),'architecture':platform.machine(),
        'pyinstaller':metadata.version('pyinstaller'),'dependencies':sorted(dependencies,key=lambda d:d['name'].lower()),
        'modules':modules,'signed_release':False}
    (bundle/'BUILD-MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    subprocess.run([str(Path(iscc).resolve()),str(ROOT/'packaging/windows/installer.iss')],cwd=ROOT,check=True)
    outputs=[p for p in (ROOT/'dist/installer').glob('*.exe')]
    hashes={str(p.relative_to(ROOT/'dist')):hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs}
    hashes.update({str(p.relative_to(ROOT/'dist')):hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.rglob('*') if p.is_file()})
    (ROOT/'dist/SHA256SUMS.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(json.dumps({'source_sha':source_sha,'bundle':str(bundle),'installers':[str(p) for p in outputs],'files':len(hashes),'signed_release':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--iscc',required=True)
    build(parser.parse_args().iscc)
