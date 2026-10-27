import os
import subprocess
import pytest
from scripts.acquire_windows_tools import verify_signature


def test_signature_shell_does_not_inherit_incompatible_modules(monkeypatch,tmp_path):
    monkeypatch.setenv('PSModulePath','foreign-powershell-modules')
    monkeypatch.setenv('SystemRoot',str(tmp_path))
    calls=[]
    monkeypatch.setattr(subprocess,'run',lambda command,**kwargs:calls.append((command,kwargs)))
    installer=tmp_path/'signed compiler.exe'
    verify_signature(installer)
    command,options=calls[0]
    assert command[0]==str(tmp_path/'System32/WindowsPowerShell/v1.0/powershell.exe')
    assert 'PSModulePath' not in options['env']
    assert options['env']['DAMS_INNO_FILE']==str(installer)
    assert options['check'] is True
    assert "'Valid'" in command[-1] and 'Pyrsys' in command[-1]
    assert os.environ['PSModulePath']=='foreign-powershell-modules'


def test_invalid_signature_remains_a_hard_failure(monkeypatch,tmp_path):
    def fail(command,**kwargs):raise subprocess.CalledProcessError(1,command)
    monkeypatch.setattr(subprocess,'run',fail)
    with pytest.raises(subprocess.CalledProcessError):verify_signature(tmp_path/'unsigned.exe')
