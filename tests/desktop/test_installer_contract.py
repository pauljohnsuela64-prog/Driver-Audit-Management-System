from pathlib import Path


def test_installer_is_per_user_preserves_data_and_refuses_running_app():
    source=Path('packaging/windows/installer.iss').read_text()
    assert 'PrivilegesRequired=lowest' in source and '{localappdata}\\Programs\\BHLI Audit' in source
    assert 'Flags: unchecked' in source and '{userdesktop}' in source
    assert 'CloseApplications=no' in source and 'RestartApplications=no' in source
    assert 'AppMutex=Local\\BHLI.Audit.Desktop.Running' in source
    assert 'InitializeUninstall' in source
    assert '[UninstallDelete]' not in source and '[Registry]' not in source
    assert all(value not in source.lower() for value in ('mysql','alembic','dams_prod','taskkill','rmdir','del /'))
