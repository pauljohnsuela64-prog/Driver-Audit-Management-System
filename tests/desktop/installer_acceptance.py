"""Native per-user installer acceptance; own isolated install path, no production."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import winreg

from tests.desktop.packaged_acceptance import window,wait,user
from tests.desktop.installer_support import uninstall_complete

APP_KEY=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{C9470975-3249-43C2-A410-80972C956B05}_is1'


def shell_folder(id):
    value=ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None,id,None,0,value):raise RuntimeError('Windows shell folder unavailable')
    return Path(value.value)


def installed_key():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,APP_KEY):return True
    except FileNotFoundError:return False


def run(installer,output):
    output.mkdir(parents=True,exist_ok=True);target=output/'Installed BHLI Áudit'
    desktop=shell_folder(0x10)/'BHLI Audit.lnk';menu=shell_folder(2)/'BHLI Audit'/'BHLI Audit.lnk'
    if installed_key() or desktop.exists() or menu.exists() or (target.exists() and any(target.iterdir())):
        raise SystemExit('Existing BHLI installation/shortcut detected; refusing to alter it')
    settings=Path(os.environ['LOCALAPPDATA'])/'BHLI Audit/settings.json';created=not settings.exists()
    if created:
        settings.parent.mkdir(parents=True,exist_ok=True)
        settings.write_text('{"version":1,"api_url":"https://fictional.invalid"}',encoding='utf-8')
    before=hashlib.sha256(settings.read_bytes()).hexdigest()
    saved=output/'retained-fictional-export.xlsx';saved.write_bytes(b'fictional export retained outside installation')
    args=[str(installer),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/DIR='+str(target)]
    process=None
    def uninstall():
        uninstaller=target/'unins000.exe'
        if uninstaller.exists() and (target/'BHLIAudit.exe').exists():
            subprocess.run([str(uninstaller),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],check=True,timeout=90)
            # The bootstrap exits before its self-deleting child. EXE removal
            # precedes shortcuts/registration: require the entire postcondition.
            wait(lambda:uninstall_complete(target,desktop,menu,installed_key),30)
    try:
        subprocess.run(args,check=True,timeout=120)
        assert installed_key() and menu.exists() and not desktop.exists()
        executable=target/'BHLIAudit.exe';assert executable.exists()
        env=dict(os.environ);env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
        env['DAMS_DESKTOP_API_URL']='http://127.0.0.1:1';env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
        process=subprocess.Popen([str(executable)],cwd=output,env=env)
        root=wait(lambda:window(process.pid,'BHLI Audit'));time.sleep(.5)
        executable_hash=hashlib.sha256(executable.read_bytes()).hexdigest()
        upgrade=subprocess.run(args,timeout=30)
        assert upgrade.returncode!=0 and hashlib.sha256(executable.read_bytes()).hexdigest()==executable_hash
        assert process.poll() is None
        blocked=subprocess.run([str(target/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],timeout=30)
        assert blocked.returncode!=0 and executable.exists() and process.poll() is None
        user.PostMessageW(root,0x10,0,0);process.wait(timeout=12)
        uninstall()
        assert not installed_key() and not menu.exists() and saved.exists()
        assert hashlib.sha256(settings.read_bytes()).hexdigest()==before
        subprocess.run(args+['/TASKS=desktopicon'],check=True,timeout=120)
        assert desktop.exists() and menu.exists()
        assert hashlib.sha256(settings.read_bytes()).hexdigest()==before
        uninstall();assert not desktop.exists() and not menu.exists() and not installed_key()
        report={'per_user_install':True,'unicode_space_path':True,'start_menu':True,'desktop_shortcut_opt_in':True,
            'running_uninstall_refused':True,'running_upgrade_refused':True,'reinstall':True,'settings_retained':True,'exports_retained':True,
            'final_uninstall':True,'signed_release':False}
        (output/'installer-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
    finally:
        if process and process.poll() is None:
            root=window(process.pid,'BHLI Audit')
            if root:user.PostMessageW(root,0x10,0,0)
            process.wait(timeout=12)
        uninstall()
        if created and settings.exists() and hashlib.sha256(settings.read_bytes()).hexdigest()==before:
            settings.unlink()
            try:settings.parent.rmdir()
            except OSError:pass


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--installer',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();run(args.installer.resolve(),args.output.resolve())
