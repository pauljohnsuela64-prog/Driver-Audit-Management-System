import json
from pathlib import Path
import pytest
from desktop import settings


def test_settings_precedence_and_no_frozen_loopback_default(tmp_path):
    path=tmp_path/'settings.json'
    assert settings.resolve_settings(None,{},path,True).config is None
    assert settings.resolve_settings(None,{},path,False).config.base_url=='http://127.0.0.1:8000'
    settings.save_settings(path,'https://api.example.com')
    assert settings.resolve_settings(None,{},path,True).source=='Saved settings'
    assert settings.resolve_settings(None,{'DAMS_DESKTOP_API_URL':'https://env.example.com'},path,True).config.base_url=='https://env.example.com'
    assert settings.resolve_settings('https://cli.example.com',{'DAMS_DESKTOP_API_URL':'bad'},path,True).source=='Command line'


@pytest.mark.parametrize('url',['http://192.168.1.5:8000','https://user:password@example.com','https://example.com?token=secret','bad'])
def test_invalid_configuration_is_recoverable_and_sanitized(tmp_path,url):
    result=settings.resolve_settings(url,{},tmp_path/'settings.json',True)
    assert result.config is None and result.error and url not in result.error


@pytest.mark.parametrize('body',['[]','{"version":1,"api_url":"https://example.com","password":"private"}',
                                '{"version":true,"api_url":"https://example.com"}','x'*9000,'not-json'])
def test_strict_bounded_json(tmp_path,body):
    path=tmp_path/'settings.json';path.write_text(body)
    with pytest.raises(settings.SettingsError):settings.load_settings(path)


def test_atomic_save_does_not_include_credentials(tmp_path,monkeypatch):
    path=tmp_path/'profile'/'settings.json';settings.save_settings(path,'https://api.example.com/')
    assert json.loads(path.read_text())=={'version':1,'api_url':'https://api.example.com'}
    original=path.read_bytes()
    def fail(*args):raise PermissionError('private-system-message')
    monkeypatch.setattr(settings.os,'replace',fail)
    with pytest.raises(settings.SettingsError) as e:settings.save_settings(path,'https://other.example.com')
    assert path.read_bytes()==original and 'private-system-message' not in str(e.value)
    assert list(path.parent.iterdir())==[path]


def test_health_is_unauthenticated_and_strict():
    from tests.desktop.test_api import Transport,reply
    from desktop.api import ApiClient,ApiError
    from desktop.config import Config
    t=Transport(reply({'status':'ok'}));client=ApiClient(Config(),t)
    assert client.health() is True and t.requests[0][0:2]==('GET','/health')
    assert 'Authorization' not in t.requests[0][2]
    with pytest.raises(ApiError):ApiClient(Config(),Transport(reply({'status':'broken'}))).health()
