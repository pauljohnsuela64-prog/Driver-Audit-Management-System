"""Windows-only admission and safe wrappers; backend roles remain compatible."""
from threading import Event

import pytest

from desktop import account_operations as ops
from desktop.api import ApiClient, ApiError
from desktop.config import Config
from desktop.models import AccountPage
from tests.desktop.test_api import TOKEN, USER, Transport, reply
from tests.desktop.test_state import login

ACCOUNT=dict(USER,is_active=True)
PASSWORD='fictional secure passphrase'


@pytest.mark.parametrize('role',['ADMIN','AUDITOR'])
@pytest.mark.parametrize('revoke_fails',[False,True])
def test_desktop_admission_and_rejected_token_revocation(role,revoke_fails):
    class Client:
        revoked=[]
        def sign_in(self,*args):return login(role)
        def logout(self,token):
            self.revoked.append(token)
            if revoke_fails:raise ApiError()
    client=Client()
    if role=='ADMIN':
        assert ops.desktop_sign_in(client,'name',PASSWORD).user.role=='ADMIN'
        assert not client.revoked
    else:
        with pytest.raises(ApiError) as error:
            ops.desktop_sign_in(client,'name',PASSWORD)
        assert client.revoked==[TOKEN]
        assert ('not be confirmed' in str(error.value))==revoke_fails
        assert TOKEN not in str(error.value)


def test_account_api_uses_fixed_admin_role_and_minimum_privilege_payloads():
    transport=Transport(reply(ACCOUNT,status=201),reply(status=204),reply(dict(ACCOUNT,id=2,is_active=False)),reply(status=204))
    client=ApiClient(Config(),transport)
    assert client.create_admin(TOKEN,' admin2 ',' Another Admin ',PASSWORD).role=='ADMIN'
    client.reset_admin_password(TOKEN,2,PASSWORD,'new fictional password')
    assert not client.disable_admin(TOKEN,2).is_active
    client.change_password(TOKEN,PASSWORD,'new fictional password')
    import json
    payloads=[json.loads(r[3]) for r in transport.requests]
    assert payloads[0]==dict(username='admin2',full_name='Another Admin',password=PASSWORD,role='ADMIN')
    assert payloads[1]==dict(admin_password=PASSWORD,new_password='new fictional password')
    assert payloads[2]=={'is_active':False}
    assert payloads[3]==dict(current_password=PASSWORD,new_password='new fictional password')


def test_admin_listing_reads_all_pages_filters_legacy_and_deduplicates():
    first=[dict(ACCOUNT,id=i,role='AUDITOR') for i in range(1,101)]
    transport=Transport(reply(dict(items=first,total=101,page=1,page_size=100)),
        reply(dict(items=[dict(ACCOUNT,id=101)],total=101,page=2,page_size=100)))
    result=ops.list_admins(ApiClient(Config(),transport),TOKEN,Event())
    assert [user.id for user in result]==[101]
    assert 'page=2' in transport.requests[1][1]
    cancelled=Event();cancelled.set()
    with pytest.raises(ops.ScanCancelled):ops.list_admins(ApiClient(Config(),Transport()),TOKEN,cancelled)


@pytest.mark.parametrize('bad', [dict(ACCOUNT,is_active='true'),dict(ACCOUNT,id=True),dict(ACCOUNT,role='OWNER')])
def test_safe_account_parsing_rejects_bad_types(bad):
    client=ApiClient(Config(),Transport(reply(bad)))
    with pytest.raises(ApiError):client.get_user(TOKEN,1)


@pytest.mark.parametrize('username,full_name,password', [('', 'Name',PASSWORD),('x'*101,'Name',PASSWORD),
    ('name',' ',PASSWORD),('name','x'*201,PASSWORD),('name','Name','short'),('name','Name',' '*15),
    ('name','Name','x'*129)])
def test_account_creation_validation_never_sends_invalid_values(username,full_name,password):
    transport=Transport()
    with pytest.raises(ApiError) as error:ApiClient(Config(),transport).create_admin(TOKEN,username,full_name,password)
    assert error.value.status==422 and not transport.requests


def test_password_whitespace_is_not_silently_changed():
    transport=Transport(reply(ACCOUNT,status=201))
    ApiClient(Config(),transport).create_admin(TOKEN,'name','Name','  '+PASSWORD+'  ')
    import json
    assert json.loads(transport.requests[0][3])['password']=='  '+PASSWORD+'  '
