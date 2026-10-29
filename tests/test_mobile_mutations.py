"""CP6 real loopback HTTP contracts; all fault injection stays in this test file."""
import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from desktop.api import ApiClient, ApiError, HttpTransport, Reply
from desktop.config import Config
from scripts.mobile_demo import mobile_demonstration


PASSWORDS=tuple(secrets.token_urlsafe(24) for _ in range(3))
PAYLOAD=dict(driver_name='Fictional José 李',helper_name='Fictional Helper',
             audit_date='2026-10-29',station='Fictional North',plate_number='000123',
             remarks='Fictional remarks\nUnicode 李')


@pytest.fixture(scope='module')
def live():
    with mobile_demonstration(*PASSWORDS) as demo:
        client=ApiClient(Config(demo.origin))
        identities=[client.sign_in(name,password) for name,password in zip(
            ('demo_admin','demo_auditor','demo_auditor_b'),PASSWORDS)]
        yield client,identities


def request(client,method,path,identity,payload=None,headers=None):
    return client._request(method,path,identity.token,payload,headers)


def rejected(status,operation):
    with pytest.raises(ApiError) as failure:
        operation()
    assert failure.value.status==status


def test_three_account_six_field_lifecycle_and_attributed_history(live):
    c,(admin,a,b)=live
    created,h=request(c,'POST','/audits',a,PAYLOAD,{'Idempotency-Key':str(uuid4())})
    path=f'/audits/{created["id"]}'
    assert {key:created[key] for key in PAYLOAD}==PAYLOAD
    assert created['audited_by_user_id']==a.user.id
    assert created['audited_by_name']==a.user.full_name
    assert h['etag']=='"1"'
    assert request(c,'GET',path,b)[0]==created
    rejected(403,lambda:request(c,'PATCH',path,b,{'remarks':'denied'},{'If-Match':'"1"'}))
    rejected(422,lambda:request(c,'PATCH',path,a,{'audited_by_user_id':b.user.id},{'If-Match':'"1"'}))
    owned,h=request(c,'PATCH',path,a,{'helper_name':None,'remarks':None},{'If-Match':'"1"'})
    assert owned['helper_name'] is None and owned['remarks'] is None
    edited,h=request(c,'PATCH',path,admin,{'station':'Fictional South'},{'If-Match':h['etag']})
    assert edited['audited_by_user_id']==a.user.id and h['etag']=='"3"'
    rejected(403,lambda:request(c,'DELETE',path,a,headers={'If-Match':'"3"'}))
    request(c,'DELETE',path,admin,headers={'If-Match':'"3"'})
    rejected(404,lambda:request(c,'GET',path,admin))
    for suffix in ('?include_deleted=true','/history?include_deleted=true'):
        rejected(403,lambda suffix=suffix:request(c,'GET',path+suffix,b))
    archived,h=request(c,'GET',path+'?include_deleted=true',admin)
    assert archived['deleted_at'] and archived['version']==4 and h['etag']=='"4"'
    events=request(c,'GET',path+'/history?include_deleted=true',admin)[0]['items']
    assert [e['action'] for e in events]==['CREATE','UPDATE','UPDATE','DELETE']
    assert [e['actor_user_id'] for e in events]==[a.user.id,a.user.id,admin.user.id,admin.user.id]
    assert events[0]['before_data'] is None
    for previous,current in zip(events,events[1:]):
        assert previous['after_data']==current['before_data']
    assert events[1]['after_data']['remarks'] is None
    assert events[2]['after_data']['station']=='Fictional South'
    assert events[-1]['after_data']['deleted_at']


@pytest.mark.parametrize('field,value',[
    ('driver_name',None),('driver_name',' '),('driver_name','x'*201),
    ('helper_name','x'*201),('station',None),('station','x'*151),
    ('plate_number',None),('plate_number','x'*31),('remarks','x'*10001),
    ('audit_date',None),('audit_date','2026-02-30'),('audited_by_name','forged')])
def test_http_validation_does_not_consume_create_key(live,field,value):
    c,(_,a,_)=live
    key={'Idempotency-Key':str(uuid4())}
    rejected(422,lambda:request(c,'POST','/audits',a,PAYLOAD|{field:value},key))
    record,_=request(c,'POST','/audits',a,PAYLOAD,key)
    assert record['driver_name']==PAYLOAD['driver_name']
    rejected(422,lambda:request(c,'PATCH',f'/audits/{record["id"]}',a,{field:value},{'If-Match':'"1"'}))


class LoseCommittedResponse:
    """Read the actual completed server response, then lose it once client-side."""
    def __init__(self,config,method):
        self.real=HttpTransport(config)
        self.method=method
        self.committed=None

    def __call__(self,method,path,headers,body):
        reply=self.real(method,path,headers,body)
        if method==self.method and self.committed is None and 200<=reply.status<300:
            self.committed=reply
            raise OSError('private response-loss detail')
        return reply


def test_committed_create_loss_same_uuid_replay_after_admin_edit(live):
    c,(admin,a,b)=live
    loss=LoseCommittedResponse(c.config,'POST')
    uncertain=ApiClient(c.config,loss)
    key={'Idempotency-Key':str(uuid4())}
    rejected(0,lambda:request(uncertain,'POST','/audits',a,PAYLOAD,key))
    assert loss.committed.status==201
    record,_=request(c,'POST','/audits',a,PAYLOAD,key)
    path=f'/audits/{record["id"]}'
    assert request(c,'GET',path+'/history',a)[0]['total']==1
    edited,_=request(c,'PATCH',path,admin,{'remarks':'Admin committed edit'},{'If-Match':'"1"'})
    replay,_=request(c,'POST','/audits',a,PAYLOAD,key)
    assert replay==edited
    assert request(c,'GET',path+'/history',a)[0]['total']==2
    rejected(409,lambda:request(c,'POST','/audits',a,PAYLOAD|{'remarks':'different'},key))
    rejected(409,lambda:request(c,'POST','/audits',b,PAYLOAD,key))
    duplicate,_=request(c,'POST','/audits',a,PAYLOAD,{'Idempotency-Key':str(uuid4())})
    assert duplicate['id']!=record['id'] and duplicate['plate_number']==record['plate_number']


def test_committed_patch_and_delete_loss_require_fresh_authorized_reads(live):
    c,(admin,a,b)=live
    record,_=request(c,'POST','/audits',a,PAYLOAD)
    path=f'/audits/{record["id"]}'
    patch_loss=LoseCommittedResponse(c.config,'PATCH')
    rejected(0,lambda:request(ApiClient(c.config,patch_loss),'PATCH',path,a,
        {'remarks':'Committed despite response loss'},{'If-Match':'"1"'}))
    fresh,h=request(c,'GET',path,b)
    assert fresh['remarks']=='Committed despite response loss' and h['etag']=='"2"'
    rejected(412,lambda:request(c,'PATCH',path,a,{'station':'stale'},{'If-Match':'"1"'}))
    assert request(c,'GET',path,a)[0]['station']==PAYLOAD['station']
    delete_loss=LoseCommittedResponse(c.config,'DELETE')
    rejected(0,lambda:request(ApiClient(c.config,delete_loss),'DELETE',path,admin,headers={'If-Match':'"2"'}))
    rejected(404,lambda:request(c,'GET',path,a))
    rejected(403,lambda:request(c,'GET',path+'?include_deleted=true',a))
    assert request(c,'GET',path+'?include_deleted=true',admin)[0]['deleted_at']
    events=request(c,'GET',path+'/history?include_deleted=true',admin)[0]['items']
    assert [e['action'] for e in events]==['CREATE','UPDATE','DELETE']


def test_concurrent_same_uuid_and_versioned_writes(live):
    c,(admin,a,_)=live
    barrier=Barrier(2)
    key={'Idempotency-Key':str(uuid4())}
    def create():
        barrier.wait(timeout=5)
        return request(c,'POST','/audits',a,PAYLOAD,key)[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        records=list(pool.map(lambda _:create(),range(2)))
    assert records[0]['id']==records[1]['id']
    path=f'/audits/{records[0]["id"]}'
    assert request(c,'GET',path+'/history',a)[0]['total']==1
    barrier=Barrier(2)
    def edit(fields):
        barrier.wait(timeout=5)
        try:return request(c,'PATCH',path,a,fields,{'If-Match':'"1"'})[0]
        except ApiError as error:return error.status
    fields=[{'station':'Concurrent station'},{'remarks':'Concurrent remarks'}]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(edit,fields))
    assert sum(isinstance(result,dict) for result in results)==1 and 412 in results
    loser=fields[results.index(412)]
    fresh,h=request(c,'GET',path,a)
    merged,_=request(c,'PATCH',path,a,loser,{'If-Match':h['etag']})
    assert merged['station']=='Concurrent station' and merged['remarks']=='Concurrent remarks'
    rejected(412,lambda:request(c,'DELETE',path,admin,headers={'If-Match':'"2"'}))
    assert request(c,'GET',path,a)[0]==merged


@pytest.mark.parametrize('etag,status',[(None,428),('1',422),('W/"1"',422),('"01"',422),('"99"',412)])
def test_exact_http_etag_required(live,etag,status):
    c,(admin,a,_)=live
    record,_=request(c,'POST','/audits',a,PAYLOAD)
    path=f'/audits/{record["id"]}'
    headers={} if etag is None else {'If-Match':etag}
    rejected(status,lambda:request(c,'PATCH',path,a,{'remarks':'no'},headers))
    rejected(status,lambda:request(c,'DELETE',path,admin,headers=headers))


@pytest.mark.parametrize('fault',['malformed','oversize','network'])
def test_transport_faults_sanitize_private_details(live,fault,monkeypatch):
    c,(_,a,_)=live
    real=HttpTransport(c.config)
    if fault=='oversize':
        # Exercise the actual bounded socket read against a real API response.
        monkeypatch.setattr('desktop.api.MAX_RESPONSE_BYTES',64)
    def transport(method,path,headers,body):
        response=real(method,path,headers,body)
        if fault=='malformed':return Reply(200,{},b'private sensitive detail')
        raise OSError('private sensitive detail')
    with pytest.raises(ApiError) as error:
        request(ApiClient(c.config,transport),'GET','/audits',a)
    assert error.value.status==(0 if fault=='network' else 502)
    assert 'private' not in str(error.value) and a.token not in str(error.value)


def test_competing_edit_archive_cannot_both_commit_same_version(live):
    c,(admin,a,_)=live
    record,_=request(c,'POST','/audits',a,PAYLOAD)
    path=f'/audits/{record["id"]}'
    barrier=Barrier(2)
    def mutate(method):
        barrier.wait(timeout=5)
        try:
            request(c,method,path,admin,{'remarks':'Racing edit'} if method=='PATCH' else None,
                    {'If-Match':'"1"'})
            return 'committed'
        except ApiError as error:return error.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(mutate,['PATCH','DELETE']))
    assert results.count('committed')==1
    assert next(result for result in results if result!='committed') in (404,412)
    events=request(c,'GET',path+'/history?include_deleted=true',admin)[0]['items']
    assert len(events)==2 and events[-1]['action'] in ('UPDATE','DELETE')


def test_revoked_session_cannot_read_or_mutate_after_account_switch(live):
    c,(_,_,b)=live
    separate=c.sign_in('demo_auditor',PASSWORDS[1])
    record,_=request(c,'POST','/audits',separate,PAYLOAD)
    path=f'/audits/{record["id"]}'
    c.logout(separate.token)
    rejected(401,lambda:request(c,'GET',path,separate))
    rejected(401,lambda:request(c,'PATCH',path,separate,{'remarks':'late write'},{'If-Match':'"1"'}))
    rejected(403,lambda:request(c,'PATCH',path,b,{'remarks':'switched account'},{'If-Match':'"1"'}))
    assert request(c,'GET',path,b)[0]['remarks']==PAYLOAD['remarks']


def test_real_role_and_status_changes_revoke_sessions_without_rewriting_attribution():
    # Separate fixture: access changes must not invalidate module peers' leases.
    with mobile_demonstration(*PASSWORDS) as demo:
        c=ApiClient(Config(demo.origin))
        admin,a,b=[c.sign_in(name,password) for name,password in zip(
            ('demo_admin','demo_auditor','demo_auditor_b'),PASSWORDS)]
        record,_=request(c,'POST','/audits',a,PAYLOAD)
        path=f'/audits/{record["id"]}'
        request(c,'PATCH',f'/users/{a.user.id}/access',admin,{'role':'ADMIN'})
        rejected(401,lambda:request(c,'GET',path,a))
        promoted=c.sign_in('demo_auditor',PASSWORDS[1])
        assert promoted.user.role=='ADMIN' and promoted.user.id==a.user.id
        request(c,'PATCH',f'/users/{b.user.id}/access',admin,{'is_active':False})
        rejected(401,lambda:request(c,'GET',path,b))
        rejected(401,lambda:c.sign_in('demo_auditor_b',PASSWORDS[2]))
        request(c,'PATCH',f'/users/{b.user.id}/access',admin,{'is_active':True})
        active=c.sign_in('demo_auditor_b',PASSWORDS[2])
        assert request(c,'GET',path,active)[0]['audited_by_name']==record['audited_by_name']
        assert request(c,'GET',path,promoted)[0]['audited_by_user_id']==a.user.id
        for identity in (admin,promoted,active):c.logout(identity.token)
