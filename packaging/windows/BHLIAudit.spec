# Build on Windows from the repository root with the isolated build environment.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root=Path(SPECPATH).resolve().parents[1]
assets=root/'desktop'/'assets'
if not (assets/'bhli.ico').is_file():raise SystemExit('Application icon missing')
a=Analysis([str(root/'packaging/windows/entry.py')],pathex=[str(root)],
    binaries=[],datas=collect_data_files('customtkinter')+[(str(assets/'bhli.ico'),'desktop/assets')],
    hiddenimports=[],hookspath=[],runtime_hooks=[],
    excludes=['backend','database','migrations','scripts','tests','pytest','sqlalchemy','pymysql','fastapi','uvicorn'],
    noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='BHLIAudit',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=False,
    icon=str(assets/'bhli.ico'),version=str(root/'packaging/windows/version_info.txt'),
    uac_admin=False,uac_uiaccess=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='BHLIAudit')
