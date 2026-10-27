"""The developer demo runs normal authentication against disposable SQLite only."""
import socket
import pytest

from desktop.api import ApiClient,ApiError
from desktop.config import Config
from desktop.models import AuditQuery
from scripts.desktop_demo import demonstration

ADMIN_PASSWORD='fictional administrator passphrase'
AUDITOR_PASSWORD='fictional auditor passphrase'


def test_demo_real_http_auth_filters_attribution_and_cleanup(monkeypatch):
    import backend.main
    def forbidden():
        raise AssertionError('Production configuration must never be consulted')
    monkeypatch.setattr(backend.main,'runtime_database_url',forbidden)
    with demonstration(ADMIN_PASSWORD,AUDITOR_PASSWORD) as demo:
        database=demo.database_file
        assert database.is_file()
        client=ApiClient(Config(demo.origin))
        admin=client.sign_in('demo_admin',ADMIN_PASSWORD)
        auditor=client.sign_in('demo_admin2',AUDITOR_PASSWORD)
        assert admin.user.role=='ADMIN' and auditor.user.role=='ADMIN'
        assert admin.user.id!=auditor.user.id
        page=client.list_audits(auditor.token,AuditQuery(page_size=100))
        assert page.total==60 and len(page.items)==60
        own=client.list_audits(auditor.token,AuditQuery(audited_by_user_id=auditor.user.id))
        assert own.total==40
        detail=client.get_audit(auditor.token,own.items[0].id)
        assert detail.audited_by_name=='Fictional HR Two (original)'
        assert auditor.user.full_name=='Demo Administrator Two'
        assert detail.etag is not None
        archived=client.list_audits(admin.token,AuditQuery(include_deleted=True,page_size=100))
        assert archived.total==61
        deleted=next(record for record in archived.items if record.deleted_at)
        history=client.audit_history(admin.token,deleted.id,include_deleted=True)
        assert [event.action for event in history.items]==['CREATE','UPDATE','DELETE']
        assert history.items[0].after_data.audited_by_name=='Fictional HR Two (original)'
        legacy=client.sign_in('demo_auditor',demo.legacy_password)
        with pytest.raises(ApiError) as denied:
            client._request('GET','/users',legacy.token)
        assert denied.value.status==403
        client.logout(legacy.token)
        client.logout(admin.token)
        client.logout(auditor.token)
        with pytest.raises(ApiError) as revoked:
            client.me(auditor.token)
        assert revoked.value.status==401
        port=demo.port
    assert not database.parent.exists()
    with socket.socket() as probe:
        assert probe.connect_ex(('127.0.0.1',port))!=0


def test_demo_rejects_weak_or_shared_passwords():
    for first,second in [('short',AUDITOR_PASSWORD),(ADMIN_PASSWORD,'short'),(ADMIN_PASSWORD,ADMIN_PASSWORD)]:
        with pytest.raises(ValueError):
            with demonstration(first,second):
                pytest.fail('Unsafe demo credentials accepted')


def test_demo_cleans_up_after_caller_failure():
    with pytest.raises(RuntimeError,match='intentional'):
        with demonstration(ADMIN_PASSWORD,AUDITOR_PASSWORD) as demo:
            database=demo.database_file
            raise RuntimeError('intentional')
    assert not database.parent.exists()


def test_demo_console_fails_closed_without_hidden_password_input(monkeypatch):
    import warnings
    from getpass import GetPassWarning
    import scripts.desktop_demo as module
    started=[]
    def unsafe_prompt(prompt):
        warnings.warn('Hidden input unavailable',GetPassWarning)
        return 'fictional password must not be consumed'
    def forbidden_start(*args):
        started.append(True)
        raise RuntimeError('Demo should not start')
    monkeypatch.setattr(module,'getpass',unsafe_prompt)
    monkeypatch.setattr(module,'demonstration',forbidden_start)
    with pytest.raises(SystemExit):
        module.main()
    assert started==[]


def test_demo_seed_never_uses_environment_http_proxy(monkeypatch):
    with socket.socket() as unused_proxy:
        unused_proxy.bind(('127.0.0.1',0))
        origin=f'http://127.0.0.1:{unused_proxy.getsockname()[1]}'
        for key in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy'):
            monkeypatch.setenv(key,origin)
        monkeypatch.setenv('NO_PROXY','')
        monkeypatch.setenv('no_proxy','')
        with demonstration(ADMIN_PASSWORD,AUDITOR_PASSWORD) as demo:
            assert ApiClient(Config(demo.origin)).sign_in('demo_admin',ADMIN_PASSWORD).user.role=='ADMIN'
