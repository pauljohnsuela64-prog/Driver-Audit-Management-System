# Separate local-only development executable; never bundles a user database.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).resolve().parents[1]
assets = root / 'desktop' / 'assets'
a = Analysis([str(root / 'packaging/windows/offline_entry.py')], pathex=[str(root)],
    binaries=[], datas=collect_data_files('customtkinter') + [(str(assets / 'bhli.ico'), 'desktop/assets')],
    hiddenimports=['_cffi_backend'], hookspath=[], runtime_hooks=[],
    excludes=['backend', 'database', 'migrations', 'scripts', 'tests', 'pytest',
              'sqlalchemy', 'pymysql', 'fastapi', 'uvicorn', 'dotenv',
              'desktop.api', 'desktop.session', 'desktop.app', 'desktop.tasks',
              'desktop.config', 'desktop.account_operations', 'desktop.audit_actions',
              'desktop.export_ui', 'desktop.reports', 'desktop.__main__'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='BHLIAuditOffline', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    icon=str(assets / 'bhli.ico'), version=str(root / 'packaging/windows/offline_version_info.txt'),
    uac_admin=False, uac_uiaccess=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='BHLIAuditOffline')
