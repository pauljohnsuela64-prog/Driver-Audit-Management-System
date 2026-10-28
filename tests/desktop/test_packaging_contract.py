from pathlib import Path
from desktop.resources import resource_path
from desktop.version import VERSION
import importlib.util
import pytest


def test_owned_icon_is_multiresolution():
    import struct
    data=resource_path('bhli.ico').read_bytes()
    assert struct.unpack('<HHH',data[:6])==(0,1,7)
    sizes=[struct.unpack('<BBBBHHII',data[6+i*16:22+i*16])[0] or 256 for i in range(7)]
    assert sizes==[16,24,32,48,64,128,256]


def test_packaging_entry_and_metadata_are_client_only():
    spec=Path('packaging/windows/BHLIAudit.spec').read_text()
    assert 'console=False' in spec and 'upx=False' in spec and 'uac_admin=False' in spec
    assert 'collect_data_files(\'customtkinter\')' in spec
    assert VERSION in Path('packaging/windows/version_info.txt').read_text()
    entry=Path('packaging/windows/entry.py').read_text()
    assert 'desktop.__main__' in entry and 'BHLI-START-01' in entry and 'from backend' not in entry


@pytest.mark.parametrize('failure,code,visible',[(SystemExit(2),2,True),(SystemExit(0),0,False),(ValueError('private detail'),1,True)])
def test_windowless_startup_errors_are_visible_and_safe(monkeypatch,failure,code,visible):
    spec=importlib.util.spec_from_file_location('packaged_entry','packaging/windows/entry.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    import desktop.__main__
    def start():raise failure
    seen=[];monkeypatch.setattr(desktop.__main__,'main',start)
    monkeypatch.setattr(module,'show_error',lambda:seen.append('BHLI-START-01'),raising=False)
    assert module.run()==code and bool(seen)==visible
