import os
import pytest
from desktop.offline.models import OfflineError


def test_publish_and_bounded_read(tmp_path):
    from desktop.offline.transfer_files import publish_transfer, read_transfer
    path=tmp_path/'audit.bhlitransfer'
    publish_transfer(path,b'package')
    assert read_transfer(path)==b'package'
    assert list(tmp_path.iterdir())==[path]


def test_never_overwrites_existing_or_racing_target(tmp_path,monkeypatch):
    from desktop.offline.transfer_files import publish_transfer
    path=tmp_path/'audit.bhlitransfer'; method='rename' if os.name=='nt' else 'link'; link=getattr(os,method)
    def racing(source,target):
        path.write_bytes(b'other user data')
        return link(source,target)
    monkeypatch.setattr(os,method,racing)
    with pytest.raises(OfflineError): publish_transfer(path,b'package')
    assert path.read_bytes()==b'other user data'
    assert list(tmp_path.iterdir())==[path]


def test_cancelled_publish_has_no_destination_or_staging_file(tmp_path):
    from desktop.offline.transfer_files import publish_transfer
    path=tmp_path/'audit.bhlitransfer'
    with pytest.raises(OfflineError) as caught: publish_transfer(path,b'package',cancel=lambda:True)
    assert caught.value.code=='cancelled'
    assert not list(tmp_path.iterdir())


def test_oversize_read_and_disk_error_are_sanitized(tmp_path,monkeypatch):
    from desktop.offline.transfer_files import read_transfer, publish_transfer
    path=tmp_path/'private.bhlitransfer'; path.write_bytes(b'x'*65)
    with pytest.raises(OfflineError): read_transfer(path,limit=64)
    def fail(*args): raise OSError('private secret path')
    monkeypatch.setattr(os,'fsync',fail)
    target=tmp_path/'output.bhlitransfer'
    with pytest.raises(OfflineError) as caught: publish_transfer(target,b'package')
    assert 'private' not in str(caught.value)
    assert list(tmp_path.iterdir())==[path]


def test_cancel_during_publication_keeps_confirmed_file(tmp_path,monkeypatch):
    from threading import Event
    from desktop.offline.transfer_files import publish_transfer
    token=Event(); method='rename' if os.name=='nt' else 'link'; link=getattr(os,method); path=tmp_path/'complete.bhlitransfer'
    def late_cancel(source,target):
        link(source,target); token.set()
    monkeypatch.setattr(os,method,late_cancel)
    assert publish_transfer(path,b'complete',cancel=token.is_set)
    assert path.read_bytes()==b'complete'


@pytest.mark.skipif(os.name!='nt',reason='Windows no-replace rename publication')
def test_windows_publication_does_not_require_hardlink_support(tmp_path,monkeypatch):
    from desktop.offline.transfer_files import publish_transfer
    def unsupported(*args): raise OSError('Hardlinks unsupported on this filesystem')
    monkeypatch.setattr(os,'link',unsupported)
    path=tmp_path/'usb-compatible.bhlitransfer'
    assert publish_transfer(path,b'complete')
    assert path.read_bytes()==b'complete'
