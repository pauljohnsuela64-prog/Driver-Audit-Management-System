"""Actual account endpoints on fixture-isolated SQLite or --mysql only."""
from threading import Event
import pytest
from tests.test_auth import api,auth_engine,encoded_password,PASSWORD
from desktop.api import ApiClient,ApiError,Reply
from desktop.config import Config
from desktop.account_operations import desktop_sign_in,list_admins
from desktop.models import AuditQuery
from uuid import uuid4


def client_for(api):
    server,_,_=api
    def transport(method,path,headers,body):
        response=server.request(method,path,headers=headers,content=body)
        return Reply(response.status_code,dict(response.headers),response.content)
    return ApiClient(Config(),transport)


def test_two_admins_attribution_disable_and_legacy_rejection(api):
    client=client_for(api)
    first=desktop_sign_in(client,'admin',PASSWORD)
    created=client.create_admin(first.token,'second_admin','Second HR',PASSWORD)
    second=desktop_sign_in(client,'second_admin',PASSWORD)
    assert {u.id for u in list_admins(client,first.token,Event())}=={first.user.id,created.id}
    records=[]
    for identity in (first,second):
        record=client.create_audit(identity.token,dict(driver_name='Fictional Driver',audit_date='2026-10-27',
            station='Fictional Station',plate_number='DUPLICATE'),str(uuid4()))
        records.append(record)
        assert record.audited_by_user_id==identity.user.id and record.audited_by_name==identity.user.full_name
    with pytest.raises(ApiError) as denied:desktop_sign_in(client,'auditor',PASSWORD)
    assert denied.value.status==403
    # Generic API/back-end AUDITOR compatibility remains intact.
    legacy=client.sign_in('auditor',PASSWORD);client.logout(legacy.token)
    client.disable_admin(first.token,second.user.id)
    with pytest.raises(ApiError) as revoked:client.me(second.token)
    assert revoked.value.status==401
    client.reset_admin_password(first.token,second.user.id,PASSWORD,'replacement test passphrase')
    assert not client.get_user(first.token,second.user.id).is_active
    with pytest.raises(ApiError):client.sign_in('second_admin','replacement test passphrase')
    unchanged=client.get_audit(first.token,records[1].id)
    assert unchanged.audited_by_name=='Second HR' and unchanged.audited_by_user_id==second.user.id
    assert client.audit_history(first.token,unchanged.id).total==1


def test_reset_reauthentication_and_self_change_revoke_sessions(api):
    client=client_for(api);first=desktop_sign_in(client,'admin',PASSWORD)
    target=client.create_admin(first.token,'second_admin','Second HR',PASSWORD)
    second=desktop_sign_in(client,'second_admin',PASSWORD)
    with pytest.raises(ApiError) as denied:client.reset_admin_password(first.token,target.id,'incorrect', 'replacement test passphrase')
    assert denied.value.status==401
    assert client.me(second.token).id==target.id
    client.reset_admin_password(first.token,target.id,PASSWORD,'replacement test passphrase')
    with pytest.raises(ApiError):client.me(second.token)
    with pytest.raises(ApiError):client.sign_in('second_admin',PASSWORD)
    second=desktop_sign_in(client,'second_admin','replacement test passphrase')
    client.change_password(second.token,'replacement test passphrase','next replacement test password')
    with pytest.raises(ApiError):client.me(second.token)
    with pytest.raises(ApiError):client.sign_in('second_admin','replacement test passphrase')
    assert desktop_sign_in(client,'second_admin','next replacement test password').user.id==target.id
    with pytest.raises(ApiError) as self_disable:client.disable_admin(first.token,first.user.id)
    assert self_disable.value.code=='self_access_change'
