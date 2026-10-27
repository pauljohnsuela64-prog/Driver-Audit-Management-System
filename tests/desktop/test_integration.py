"""Desktop contract against the real API on an isolated fixture database only."""
import pytest
from tests.test_auth import api, auth_engine, encoded_password, PASSWORD
from desktop.api import ApiClient, ApiError, Reply
from desktop.config import Config
from desktop.models import AuditQuery


@pytest.mark.parametrize('username',['admin','auditor'])
def test_real_api_desktop_contract(api,username):
    server,_,_=api
    response=server.post('/auth/login',json={'username':'auditor','password':PASSWORD})
    seed_token=response.json()['access_token']
    record=server.post('/audits',headers={'Authorization':'Bearer '+seed_token},json={
        'driver_name':'Example Driver','audit_date':'2026-10-26','station':'Example Station',
        'plate_number':'EXAMPLE-1','remarks':'Isolated contract verification only'}).json()
    paths=[]
    def transport(method,path,headers,body):
        paths.append((method,path))
        response=server.request(method,path,headers=headers,content=body)
        return Reply(response.status_code,dict(response.headers),response.content)
    client=ApiClient(Config(),transport)
    identity=client.sign_in(username,PASSWORD)
    assert identity.user.role==username.upper()
    result=client.list_audits(identity.token,AuditQuery(station='Example',sort='audit_date'))
    assert result.total==1 and result.items[0].id==record['id']
    detail=client.get_audit(identity.token,record['id'])
    assert detail.etag=='"1"' and detail.audited_by_name=='auditor'
    client.logout(identity.token)
    with pytest.raises(ApiError) as error:
        client.me(identity.token)
    assert error.value.status==401
    assert all(method=='GET' or path in ('/auth/login','/auth/logout') for method,path in paths)


def test_real_api_create_lost_response_retry_and_historical_identity(api):
    from desktop.audit_operations import CreationIntent
    server,_,_=api
    lose_once=[True]
    def transport(method,path,headers,body):
        response=server.request(method,path,headers=headers,content=body)
        if method=='POST' and path=='/audits' and lose_once[0]:
            lose_once[0]=False
            assert response.status_code==201
            raise OSError('Fictional lost response after commit')
        return Reply(response.status_code,dict(response.headers),response.content)
    client=ApiClient(Config(),transport)
    identity=client.sign_in('auditor',PASSWORD)
    intent=CreationIntent(identity.user.id,dict(driver_name='Example',helper_name=None,
        audit_date='2026-10-27',station='Example',plate_number='DUPLICATES-OK',remarks=None))
    with pytest.raises(ApiError):
        client.create_audit(identity.token,intent.payload,intent.key)
    record=client.create_audit(identity.token,intent.payload,intent.key)
    assert client.list_audits(identity.token,AuditQuery()).total==1
    assert len(client.audit_history(identity.token,record.id).items)==1
    admin=client.sign_in('admin',PASSWORD)
    response=server.patch('/users/'+str(identity.user.id),headers={'Authorization':'Bearer '+admin.token},
                          json={'full_name':'Renamed Employee'})
    assert response.status_code==200
    updated=client.update_audit(identity.token,record.id,{'remarks':'Updated'},record.etag)
    assert updated.audited_by_name=='auditor' and updated.audited_by_user_id==identity.user.id
    with pytest.raises(ApiError) as error:
        client.update_audit(admin.token,record.id,{'remarks':'Stale'},record.etag)
    assert error.value.status==412
    assert client.audit_history(admin.token,record.id).total==2
    client.delete_audit(admin.token,record.id,updated.etag)
    assert client.list_audits(admin.token,AuditQuery()).total==0
    assert client.get_audit(admin.token,record.id,include_deleted=True).deleted_at
    history=client.audit_history(admin.token,record.id,include_deleted=True)
    assert [e.action for e in history.items]==['CREATE','UPDATE','DELETE']
    assert history.items[-1].before_data.audited_by_name=='auditor'
    for operation in (lambda:client.get_audit(identity.token,record.id,include_deleted=True),
                      lambda:client.audit_history(identity.token,record.id,include_deleted=True)):
        with pytest.raises(ApiError) as error:
            operation()
        assert error.value.status==403


def test_real_api_other_auditor_cannot_edit_by_name(api):
    server,_,_=api
    def transport(method,path,headers,body):
        response=server.request(method,path,headers=headers,content=body)
        return Reply(response.status_code,dict(response.headers),response.content)
    client=ApiClient(Config(),transport)
    admin=client.sign_in('admin',PASSWORD)
    assert server.post('/users',headers={'Authorization':'Bearer '+admin.token},json={
        'username':'second','full_name':'auditor','role':'AUDITOR','password':PASSWORD}).status_code==201
    first=client.sign_in('auditor',PASSWORD)
    second=client.sign_in('second',PASSWORD)
    from uuid import uuid4
    record=client.create_audit(first.token,dict(driver_name='Example',audit_date='2026-10-27',
        station='Example',plate_number='EXAMPLE'),str(uuid4()))
    with pytest.raises(ApiError) as error:
        client.update_audit(second.token,record.id,{'driver_name':'Not owned'},record.etag)
    assert error.value.status==403
    assert client.audit_history(first.token,record.id).total==1
