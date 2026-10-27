from tests.desktop.installer_support import uninstall_complete


def test_early_executable_removal_does_not_mean_uninstall_finished(tmp_path):
    target=tmp_path/'installed';target.mkdir()
    desktop=tmp_path/'desktop.lnk';menu=tmp_path/'menu.lnk'
    files=[target/'BHLIAudit.exe',target/'unins000.exe',desktop,menu]
    for path in files:path.write_text('fictional owned file')
    settings=tmp_path/'settings.json';settings.write_text('retained user configuration')
    registered=True
    assert not uninstall_complete(target,desktop,menu,lambda:registered)
    for path in files:
        path.unlink()
        assert not uninstall_complete(target,desktop,menu,lambda:registered)
    registered=False
    assert uninstall_complete(target,desktop,menu,lambda:registered)
    assert settings.read_text()=='retained user configuration'
