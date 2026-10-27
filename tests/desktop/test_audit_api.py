import json
from uuid import uuid4

import pytest

from desktop.api import ApiClient, ApiError, MAX_RESPONSE_BYTES
from desktop.config import Config
from desktop.models import Audit, AuditQuery
from tests.desktop.test_api import AUDIT, TOKEN, Transport, reply

PAYLOAD = {k:AUDIT[k] for k in ('driver_name','helper_name','audit_date','station','plate_number','remarks')}


def test_create_update_delete_use_exact_safe_headers():
    key = str(uuid4())
    transport = Transport(reply(AUDIT,status=201,etag='"2"'),reply(AUDIT,etag='"2"'),reply(status=204))
    client = ApiClient(Config(),transport)
    assert client.create_audit(TOKEN,PAYLOAD,key).id == 1
    assert transport.requests[0][2]['Idempotency-Key'] == key
    assert json.loads(transport.requests[0][3]) == PAYLOAD
    assert client.update_audit(TOKEN,1,{'remarks':None},'"2"').etag == '"2"'
    assert transport.requests[1][2]['If-Match'] == '"2"'
    assert client.delete_audit(TOKEN,1,'"2"') is None
    assert transport.requests[2][0] == 'DELETE'
    assert transport.requests[2][2]['If-Match'] == '"2"'


@pytest.mark.parametrize('etag',[None,'*','W/"2"','"0"','2','"2", "3"','"2"\r\nInjected:x'])
def test_mutation_requires_exact_valid_etag(etag):
    transport = Transport()
    with pytest.raises(ApiError):
        ApiClient(Config(),transport).update_audit(TOKEN,1,{'remarks':None},etag)
    assert not transport.requests


def test_active_parser_stays_strict_and_deleted_access_is_explicit():
    deleted = dict(AUDIT,deleted_at='2026-10-27T01:00:00Z')
    with pytest.raises(ValueError):
        Audit.parse(deleted)
    transport=Transport(reply(deleted,etag='"2"'),reply(dict(items=[deleted],total=1,page=1,page_size=25)))
    client=ApiClient(Config(),transport)
    assert client.get_audit(TOKEN,1,include_deleted=True).deleted_at is not None
    assert 'include_deleted=true' in transport.requests[0][1]
    assert client.list_audits(TOKEN,AuditQuery(include_deleted=True)).items[0].deleted_at


def event(**changes):
    return dict(id=1,audit_id=1,actor_user_id=2,action='UPDATE',before_data=AUDIT,
                after_data=dict(AUDIT,version=3,remarks='Changed'),created_at='2026-10-27T01:00:00Z') | changes


def test_history_typed_chronological_pages_and_large_unicode_bound():
    large=dict(AUDIT,remarks='\U0001f600'*10000)
    items=[event(id=i,before_data=large,after_data=large) for i in range(1,26)]
    data=dict(items=items,total=25,page=1,page_size=25)
    assert len(json.dumps(data).encode()) < MAX_RESPONSE_BYTES
    transport=Transport(reply(data))
    page=ApiClient(Config(),transport).audit_history(TOKEN,1,include_deleted=True)
    assert len(page.items)==25 and page.items[0].actor_user_id==2
    assert page.items[0].before_data.remarks==large['remarks']
    assert 'page_size=25' in transport.requests[0][1] and 'include_deleted=true' in transport.requests[0][1]


@pytest.mark.parametrize('changes',[{'action':'RESTORE'},{'actor_user_id':True},{'audit_id':2},
                                    {'created_at':'yesterday'},{'after_data':{'password':'secret'}}])
def test_history_rejects_malformed_events(changes):
    client=ApiClient(Config(),Transport(reply(dict(items=[event(**changes)],total=1,page=1,page_size=25))))
    with pytest.raises(ApiError) as error:
        client.audit_history(TOKEN,1)
    assert error.value.status==502 and 'secret' not in str(error.value)
