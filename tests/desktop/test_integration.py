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
