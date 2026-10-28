import warnings

import pytest
from desktop.api import ApiClient,ApiError
from desktop.config import Config
from desktop.models import AuditQuery

from scripts.mobile_demo import mobile_demonstration


ADMIN='fictional mobile administrator passphrase'
AUDITOR='fictional mobile auditor passphrase'


def test_mobile_fixture_both_roles_shared_active_records_and_cleanup(monkeypatch):
    import backend.main
    monkeypatch.setattr(backend.main,'runtime_database_url',lambda:pytest.fail('Production config accessed'))
    with mobile_demonstration(ADMIN,AUDITOR) as demo:
        database=demo.database_file
        client=ApiClient(Config(demo.origin))
        admin=client.sign_in('demo_admin',ADMIN)
        auditor=client.sign_in('demo_auditor',AUDITOR)
        assert (admin.user.role,auditor.user.role)==('ADMIN','AUDITOR')
        page=client.list_audits(auditor.token,AuditQuery(page_size=25))
        assert page.total==60 and len(page.items)==25
        second=client.list_audits(auditor.token,AuditQuery(page=2,page_size=25))
        assert not {record.id for record in page.items}&{record.id for record in second.items}
        unicode_record=next(record for record in page.items if record.plate_number=='000123')
        assert '李' in unicode_record.driver_name and unicode_record.audited_by_name=='Fictional HR Two (original)'
        assert client.get_audit(auditor.token,unicode_record.id).audited_by_name==unicode_record.audited_by_name
        with pytest.raises(ApiError) as denied:
            client.list_audits(auditor.token,AuditQuery(include_deleted=True))
        assert denied.value.status==403
        client.logout(auditor.token)
        with pytest.raises(ApiError) as revoked:client.me(auditor.token)
        assert revoked.value.status==401
        client.logout(admin.token)
    assert not database.parent.exists()


def test_mobile_fixture_rejects_weak_or_shared_passwords():
    for first,second in [('short',AUDITOR),(ADMIN,'short'),(ADMIN,ADMIN)]:
        with pytest.raises(ValueError):
            with mobile_demonstration(first,second):pytest.fail('Unsafe fixture accepted')


def test_mobile_cli_rejects_echoed_password_input(monkeypatch):
    from getpass import GetPassWarning
    import scripts.mobile_demo as module
    def unsafe(prompt):warnings.warn('no hidden input',GetPassWarning)
    monkeypatch.setattr(module,'getpass',unsafe)
    monkeypatch.setattr(module,'mobile_demonstration',lambda *args:pytest.fail('Fixture started'))
    with pytest.raises(SystemExit):module.main()
