"""Acquire the pinned, signed Inno compiler for test builds; no server actions."""
from pathlib import Path
import hashlib
import os
import subprocess
import sys
import urllib.request

SHA256='0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f'
URL='https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe'


def verify_signature(download):
    # Hosted pwsh exports its module path. Windows PowerShell cannot load those
    # newer assemblies: let the explicit system shell construct its own defaults.
    env={name:value for name,value in os.environ.items() if name.upper()!='PSMODULEPATH'}
    env['DAMS_INNO_FILE']=str(download)
    shell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.run([str(shell),'-NoProfile','-NonInteractive','-Command',
        "$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath $env:DAMS_INNO_FILE; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Pyrsys B.V.') {throw 'Invalid compiler publisher signature'}"],check=True,env=env)


def acquire():
    if sys.platform!='win32':raise SystemExit('Windows tool only')
    root=Path(__file__).resolve().parents[1]/'build/tools'
    root.mkdir(parents=True,exist_ok=True);download=root/'innosetup-7.1.0-x64.exe';target=root/'inno710'
    if not download.exists():urllib.request.urlretrieve(URL,download)
    if hashlib.sha256(download.read_bytes()).hexdigest()!=SHA256:raise SystemExit('Inno download checksum mismatch')
    verify_signature(download)
    if not (target/'ISCC.exe').exists():
        subprocess.run([str(download),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/CURRENTUSER','/NOICONS','/DIR='+str(target)],check=True)
    print(target/'ISCC.exe')


if __name__=='__main__':acquire()
