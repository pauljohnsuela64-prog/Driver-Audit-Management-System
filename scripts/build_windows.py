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

from scripts.license_notices import copy_verified_notices, verified_notices

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN={'backend','database','migrations','scripts','tests','pytest','sqlalchemy','pymysql','fastapi','uvicorn','dotenv'}


def candidate_installers(directory):
    from desktop.version import VERSION
    expected=directory/f'BHLI-Audit-Setup-{VERSION}-x64.exe'
    found=sorted(directory.glob('*.exe'))
    if found != [expected]:
        raise RuntimeError('Unexpected installer inventory; use fresh isolated output')
    return found


def copy_notices(dist,destination):
    for file in dist.files or []:
        relative=Path(file)
        if ('licen' in relative.name.lower() or relative.name.lower().startswith(('copying','notice'))):
            if relative.is_absolute() or '..' in relative.parts:
                raise RuntimeError('Unsafe notice path in dependency metadata')
            source=Path(dist.locate_file(file))
            if source.is_file():
                # Retain vendor subdirectories: several dependencies use LICENSE.
                target=destination/dist.metadata['Name']/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,target)


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


def build(iscc, output_root=None):
    if sys.platform!='win32' or platform.machine().upper() not in ('AMD64','X86_64'):
        raise SystemExit('Build requires Windows x64')
    if sys.version_info[:2]!=(3,14):raise SystemExit('Build requires Python 3.14')
    output=(Path(output_root) if output_root else ROOT/'dist').resolve()
    if not output.is_relative_to((ROOT/'dist').resolve()):
        raise SystemExit('Candidate output must stay inside repository dist')
    if output.exists() and any(output.iterdir()):
        raise SystemExit('Candidate output must be empty; preserve existing artifacts')
    source_sha=subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}','status','--porcelain','--untracked-files=normal'],cwd=ROOT,text=True)
    if dirty:raise SystemExit('Commit reviewed source before building candidates')
    verified_notices('windows')
    output.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,'-m','pip','check'],check=True,cwd=ROOT)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(output),
                    '--workpath',str(output/'work'),str(ROOT/'packaging/windows/BHLIAudit.spec')],check=True,cwd=ROOT)
    bundle=output/'BHLIAudit';modules=inspect_bundle(bundle)
    licenses=bundle/'THIRD_PARTY_LICENSES';licenses.mkdir(exist_ok=True)
    dependencies=[]
    for dist in metadata.distributions():
        name=dist.metadata['Name'];dependencies.append({'name':name,'version':dist.version})
        copy_notices(dist,licenses)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.is_file():shutil.copyfile(python_license,licenses/'CPython-LICENSE.txt')
    supplemental=copy_verified_notices('windows',licenses/'SUPPLEMENTAL')
    manifest={'source_sha':source_sha,'python':platform.python_version(),'architecture':platform.machine(),
        'pyinstaller':metadata.version('pyinstaller'),'dependencies':sorted(dependencies,key=lambda d:d['name'].lower()),
        'modules':modules,'signed_release':False,'supplemental_notices':supplemental}
    (bundle/'BUILD-MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    subprocess.run([str(Path(iscc).resolve()),'/DBundleDir='+str(bundle),'/DOutputDir='+str(output/'installer'),
                    str(ROOT/'packaging/windows/installer.iss')],cwd=ROOT,check=True)
    outputs=candidate_installers(output/'installer')
    hashes={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs}
    hashes.update({str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.rglob('*') if p.is_file()})
    from desktop.version import VERSION
    archive=Path(shutil.make_archive(str(output/f'BHLI-Audit-Windows-{VERSION}-x64'),'zip',output,'BHLIAudit'))
    hashes[archive.name]=hashlib.sha256(archive.read_bytes()).hexdigest()
    (output/'SHA256SUMS.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(json.dumps({'source_sha':source_sha,'bundle':str(bundle),'installers':[str(p) for p in outputs],'files':len(hashes),'signed_release':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--iscc',required=True);parser.add_argument('--output-root',type=Path)
    args=parser.parse_args();build(args.iscc,args.output_root)
