from datetime import datetime, timedelta, timezone
import json

import pytest

from desktop.api import ApiClient, ApiError, Reply
from desktop.config import Config
from desktop.models import AuditQuery

TOKEN = 'x' * 43
USER = dict(id=1, username='reviewer', full_name='Example Reviewer', role='ADMIN')
AUDIT = dict(id=1, version=2, driver_name='Example Driver', helper_name=None,
             audit_date='2026-10-26', station='Example Station', plate_number='EXAMPLE-1',
             remarks=None, audited_by_name='Original Reviewer', audited_by_user_id=1,
             created_at='2026-10-26T01:00:00Z', updated_at='2026-10-26T02:00:00Z', deleted_at=None)


class Transport:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, method, path, headers, body):
        self.requests.append((method, path, headers, body))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def reply(data=None, status=200, **headers):
    return Reply(status, headers, json.dumps(data).encode() if data is not None else b'')


@pytest.mark.parametrize('url', ['http://example.com', 'https://user:pass@example.com',
                                'https://example.com?token=x', 'ftp://localhost',
                                'http://127.0.0.1.evil.test', 'https://example.com/#x',
                                'http://localhost:bad', 'http://localhost/../secret'])
def test_reject_unsafe_urls_without_echo(url):
    with pytest.raises(ValueError) as error:
        Config(url)
    assert url not in str(error.value)


@pytest.mark.parametrize('url', ['http://localhost:8000', 'http://127.0.0.1:8000',
                                'http://[::1]:8000', 'https://api.example.com'])
def test_allowed_urls(url):
    assert Config(url).base_url == url


def test_sign_in_uses_login_then_identity_and_no_secret_repr():
    t = Transport(reply(dict(access_token=TOKEN, token_type='bearer',
                             expires_at=(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat())), reply(USER))
    login = ApiClient(Config(), t).sign_in('reviewer', 'private-password')
    assert login.user.role == 'ADMIN'
    assert TOKEN not in repr(login)
    assert t.requests[0][0:2] == ('POST', '/auth/login')
    assert json.loads(t.requests[0][3]) == dict(username='reviewer', password='private-password')
    assert t.requests[1][2]['Authorization'] == 'Bearer '+TOKEN


def test_identity_failure_revokes_provisional_token():
    t = Transport(reply(dict(access_token=TOKEN, token_type='bearer', expires_at='2099-01-01T00:00:00Z')),
                  reply(dict(USER, role='SUPERUSER')), reply(status=204))
    with pytest.raises(ApiError):
        ApiClient(Config(), t).sign_in('reviewer', 'private-password')
    assert t.requests[-1][1] == '/auth/logout'


def test_list_filters_and_detail_etag():
    t = Transport(reply(dict(items=[AUDIT], total=1, page=2, page_size=25)), reply(AUDIT, etag='"2"'))
    c = ApiClient(Config(), t)
    page = c.list_audits(TOKEN, AuditQuery(page=2, driver_name='A&B', station='East', sort='audit_date'))
    assert page.items[0].audited_by_name == 'Original Reviewer'
    assert 'driver_name=A%26B' in t.requests[0][1]
    assert 'include_deleted' not in t.requests[0][1]
    assert c.get_audit(TOKEN, 1).etag == '"2"'


@pytest.mark.parametrize('values', [dict(page=0), dict(page=10001), dict(page_size=101), dict(sort='driver'),
                                   dict(date_from='2026-02-30'), dict(date_from='2026-12-01', date_to='2026-01-01'),
                                   dict(driver_name='x'*201), dict(audited_by_user_id=0)])
def test_query_validation(values):
    with pytest.raises(ValueError):
        AuditQuery(**values)


@pytest.mark.parametrize('status,code', [(401,'unauthorized'),(403,'forbidden'),(404,'not_found'),
    (409,'conflict'),(412,'precondition_failed'),(422,'invalid_request'),(429,'rate_limited'),
    (500,'internal_error'),(503,'service_unavailable'),(302,'unexpected_response')])
def test_errors_sanitized(status, code):
    t = Transport(reply({'error': {'code':'password=secret', 'message':'mysql://secret token='+TOKEN}}, status, **{'retry-after':'7'}))
    with pytest.raises(ApiError) as caught:
        ApiClient(Config(), t).me(TOKEN)
    e = caught.value
    assert e.status == status and e.code == code
    assert 'secret' not in str(e) + repr(e) and TOKEN not in str(e)
    if status == 429:
        assert e.retry_after == 7


@pytest.mark.parametrize('body', [b'<html>password</html>', b'[]', b'null', b'{"role":"ADMIN"}'])
def test_malformed_response_safe(body):
    with pytest.raises(ApiError, match='invalid response'):
        ApiClient(Config(), Transport(Reply(200, {}, body))).me(TOKEN)


def test_offline_and_timeout_sanitized():
    for error in [TimeoutError('private-password'), OSError('mysql://secret')]:
        with pytest.raises(ApiError) as e:
            ApiClient(Config(), Transport(error)).me(TOKEN)
        assert 'private-password' not in str(e.value) and 'secret' not in str(e.value)


def test_logout_204_and_header_injection():
    t = Transport(reply(status=204))
    assert ApiClient(Config(), t).logout(TOKEN) is None
    with pytest.raises(ApiError):
        ApiClient(Config(), t).me('bad\r\nAuthorization: evil')
    assert len(t.requests) == 1


def test_conflict_envelope_preserves_known_code_without_server_message():
    t=Transport(reply({'error':{'code':'version_mismatch','message':'token=private'}},412))
    with pytest.raises(ApiError) as e:
        ApiClient(Config(),t).me(TOKEN)
    assert e.value.code=='version_mismatch'
    assert 'private' not in str(e.value)


def test_http_date_retry_header():
    from email.utils import format_datetime
    t=Transport(reply(status=429,**{'Retry-After':format_datetime(datetime.now(timezone.utc)+timedelta(seconds=30))}))
    with pytest.raises(ApiError) as e:
        ApiClient(Config(),t).me(TOKEN)
    assert 29<=e.value.retry_after<=31


@pytest.mark.parametrize('header',['9'*400,'9'*5000,'Fri, 31 Dec 9999 23:59:59 GMT'],
                         ids=['oversized','overlong','distant-date'])
def test_unreasonable_retry_after_cannot_overflow_native_deadline(header):
    import math
    import time
    from desktop.api import retry_seconds
    seconds=retry_seconds(header)
    assert 0<=seconds<=86400
    assert math.isfinite(time.monotonic()+seconds)


def test_retry_after_leading_zeroes_preserve_actual_delay():
    from desktop.api import retry_seconds
    assert retry_seconds('000000000007')==7


def test_duplicate_record_ids_in_page_are_invalid():
    t=Transport(reply(dict(items=[AUDIT,AUDIT],total=2,page=1,page_size=25)))
    with pytest.raises(ApiError):
        ApiClient(Config(),t).list_audits(TOKEN,AuditQuery())


def test_real_http_transport_refuses_redirect_and_times_out():
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    import time
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            if self.server.slow:
                time.sleep(.15)
            self.send_response(302)
            self.send_header('Location','https://example.com/never-follow')
            self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.slow=False
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        client=ApiClient(Config(f'http://127.0.0.1:{server.server_port}',read_timeout=.03))
        with pytest.raises(ApiError) as e:
            client.me(TOKEN)
        assert e.value.status==302
        server.slow=True
        with pytest.raises(ApiError) as e:
            client.me(TOKEN)
        assert e.value.code=='network_error'
    finally:
        server.shutdown()
        server.server_close()


def test_real_transport_accepts_contract_valid_full_unicode_page():
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    records=[dict(AUDIT,id=index+1,remarks='\U0001f4dd'*10000) for index in range(100)]
    payload=json.dumps(dict(items=records,total=100,page=1,page_size=100),ensure_ascii=False).encode('utf-8')
    assert len(payload)>2_000_000
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    Thread(target=server.serve_forever,daemon=True).start()
    try:
        result=ApiClient(Config(f'http://127.0.0.1:{server.server_port}')).list_audits(TOKEN,AuditQuery(page_size=100))
        assert len(result.items)==100 and len(result.items[0].remarks)==10000
    finally:
        server.shutdown()
        server.server_close()


def test_http_transport_keeps_finite_body_limit_and_closes_connection(monkeypatch):
    from types import SimpleNamespace
    import desktop.api as module
    class Connection:
        def __init__(self):
            self.closed=False
            self.sock=SimpleNamespace(settimeout=lambda _:None)
        def connect(self):
            pass
        def request(self,*args,**kwargs):
            pass
        def getresponse(self):
            return SimpleNamespace(status=200,getheaders=lambda:[],read=lambda limit:b'x'*limit)
        def close(self):
            self.closed=True
    connection=Connection()
    monkeypatch.setattr(module.http.client,'HTTPConnection',lambda **kwargs:connection)
    with pytest.raises(ValueError,match='Oversized response'):
        module.HttpTransport(Config())('GET','/audits',{},None)
    assert connection.closed
