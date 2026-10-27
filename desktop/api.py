"""Small REST interface; no logging, redirect following or persisted credentials."""
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import http.client
import json
import re
import ssl
from urllib.parse import urlsplit
from uuid import UUID

from desktop.config import Config
from desktop.models import Audit, AuditPage, EventPage, Login, User, Account, AccountPage, timestamp, integer

MESSAGES = {
    401: ('unauthorized', 'Your credentials or session are no longer valid. Please sign in.'),
    403: ('forbidden', 'You do not have permission to view this content.'),
    404: ('not_found', 'This record is no longer available.'),
    409: ('conflict', 'This operation conflicts with the current server state.'),
    412: ('precondition_failed', 'This record has changed. Refresh before continuing.'),
    422: ('invalid_request', 'Check the supplied values and try again.'),
    428: ('precondition_required', 'Reload this record to obtain its current version before saving.'),
    429: ('rate_limited', 'Too many requests. Wait before trying again.'),
    500: ('internal_error', 'The service could not complete the request. Try again.'),
    503: ('service_unavailable', 'The service is temporarily unavailable. Try again.'),
}
ERROR_CODES = {409: {'conflict','username_exists','access_conflict','self_access_change','last_admin',
                     'self_reset','password_reuse'}, 412: {'version_mismatch'}, 428: {'precondition_required'}}
MAX_RETRY_SECONDS = 86_400  # Bound untrusted delays before any native UI arithmetic.
# 100 records × (10,000 remarks + bounded name/station/plate fields), including
# worst-case JSON Unicode escaping. Keep a finite ceiling above legal pages.
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, status=0, code=None, message=None, retry_after=0):
        default = MESSAGES.get(status, ('unexpected_response', 'The service returned an unexpected response.'))
        self.status = status
        self.code = code or (default[0] if status else 'network_error')
        self.retry_after = max(0,min(MAX_RETRY_SECONDS,retry_after)) if type(retry_after) is int else 60
        super().__init__(message or (default[1] if status else 'Unable to reach the service. Check your connection and try again.'))


@dataclass(frozen=True, repr=False)
class Reply:
    status: int
    headers: dict
    body: bytes


class HttpTransport:
    def __init__(self, config):
        self.config = config

    def __call__(self, method, path, headers, body):
        url = urlsplit(self.config.base_url)
        args = dict(host=url.hostname, port=url.port, timeout=self.config.connect_timeout)
        connection = (http.client.HTTPSConnection(**args, context=ssl.create_default_context())
                      if url.scheme == 'https' else http.client.HTTPConnection(**args))
        try:
            connection.connect()
            connection.sock.settimeout(self.config.read_timeout)
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES+1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError('Oversized response')
            return Reply(response.status, dict(response.getheaders()), raw)
        finally:
            connection.close()


def retry_seconds(value):
    try:
        if value.isdigit():
            value=value.lstrip('0') or '0'
            return MAX_RETRY_SECONDS if len(value)>5 else min(int(value),MAX_RETRY_SECONDS)
        delta = parsedate_to_datetime(value) - datetime.now(timezone.utc)
        return min(MAX_RETRY_SECONDS,max(0, int(delta.total_seconds()) + 1))
    except (ValueError, TypeError, OverflowError):
        return 60


class ApiClient:
    def __init__(self, config: Config, transport=None):
        self.transport = transport or HttpTransport(config)

    def _request(self, method, path, token=None, payload=None, conditional=None):
        headers = {'Accept': 'application/json'}
        if conditional:
            headers.update(conditional)
        if token is not None:
            if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
                raise ApiError(401)
            headers['Authorization'] = 'Bearer ' + token
        body = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(payload).encode('utf-8')
        try:
            reply = self.transport(method, path, headers, body)
        except (OSError, http.client.HTTPException):
            raise ApiError() from None
        except (ValueError, UnicodeError):
            raise ApiError(502, message='The service returned an invalid response.') from None
        response_headers = {k.lower(): v for k, v in reply.headers.items()}
        if not 200 <= reply.status < 300:
            # Preserve known conflict semantics, never arbitrary codes/messages or submitted data.
            code=None
            try:
                candidate=json.loads(reply.body)['error']['code']
                if candidate in ERROR_CODES.get(reply.status,set()):
                    code=candidate
            except (ValueError,KeyError,TypeError,RecursionError):
                pass
            raise ApiError(reply.status, code=code, retry_after=retry_seconds(response_headers.get('retry-after', '60')) if reply.status == 429 else 0)
        if reply.status == 204:
            return None, response_headers
        try:
            data = json.loads(reply.body)
            if not isinstance(data, dict):
                raise ValueError
            return data, response_headers
        except (ValueError, UnicodeError, TypeError, RecursionError):
            raise ApiError(502, message='The service returned an invalid response.') from None

    def _parse(self, parser, data, *args):
        try:
            return parser(data, *args)
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
            raise ApiError(502, message='The service returned an invalid response.') from None

    def login(self, username, password):
        if not isinstance(username, str) or not 1 <= len(username.strip()) <= 100 or not isinstance(password, str) or not 1 <= len(password) <= 128:
            raise ApiError(422)
        data, _ = self._request('POST', '/auth/login', payload=dict(username=username.strip(), password=password))
        def parse(data):
            token, expiry = data['access_token'], timestamp(data['expires_at'])
            if (data.get('token_type') != 'bearer' or not isinstance(token, str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token) or expiry <= datetime.now(timezone.utc)):
                raise ValueError
            return token, expiry
        return self._parse(parse, data)

    def me(self, token):
        data, _ = self._request('GET', '/auth/me', token)
        return self._parse(User.parse, data)

    def sign_in(self, username, password):
        token, expiry = self.login(username, password)
        try:
            return Login(token, expiry, self.me(token))
        except Exception:
            try:
                self.logout(token)
            except Exception:
                pass
            raise

    def logout(self, token):
        self._request('POST', '/auth/logout', token)

    @staticmethod
    def _password(value,new=True):
        if not isinstance(value,str) or not (15 if new else 1)<=len(value)<=128 or new and not value.strip():
            raise ApiError(422)
        return value

    @staticmethod
    def _user_id(value):
        if type(value) is not int or value<1:raise ApiError(422)
        return str(value)

    def list_users(self,token,page=1):
        if type(page) is not int or not 1<=page<=10000:raise ApiError(422)
        data,_=self._request('GET',f'/users?page={page}&page_size=100',token)
        return self._parse(AccountPage.parse,data)

    def get_user(self,token,user_id):
        data,_=self._request('GET','/users/'+self._user_id(user_id),token)
        result=self._parse(Account.parse,data)
        if result.id!=user_id:raise ApiError(502)
        return result

    def create_admin(self,token,username,full_name,password):
        if not isinstance(username,str) or not 1<=len(username.strip())<=100 or not isinstance(full_name,str) or not 1<=len(full_name.strip())<=200:
            raise ApiError(422)
        payload=dict(username=username.strip(),full_name=full_name.strip(),role='ADMIN',password=self._password(password))
        data,_=self._request('POST','/users',token,payload)
        result=self._parse(Account.parse,data)
        if result.role!='ADMIN':raise ApiError(502)
        return result

    def reset_admin_password(self,token,user_id,admin_password,new_password):
        payload=dict(admin_password=self._password(admin_password,False),new_password=self._password(new_password))
        data,_=self._request('POST','/users/'+self._user_id(user_id)+'/reset-password',token,payload)
        if data is not None:raise ApiError(502)

    def disable_admin(self,token,user_id):
        data,_=self._request('PATCH','/users/'+self._user_id(user_id)+'/access',token,{'is_active':False})
        result=self._parse(Account.parse,data)
        if result.id!=user_id or result.is_active:raise ApiError(502)
        return result

    def change_password(self,token,current_password,new_password):
        payload=dict(current_password=self._password(current_password,False),new_password=self._password(new_password))
        data,_=self._request('POST','/auth/change-password',token,payload)
        if data is not None:raise ApiError(502)

    def list_audits(self, token, query):
        data, _ = self._request('GET', '/audits?' + query.encoded(), token)
        return self._parse(AuditPage.parse, data, query.include_deleted)

    def get_audit(self, token, audit_id, include_deleted=False):
        if type(audit_id) is not int or audit_id < 1:
            raise ApiError(422)
        if type(include_deleted) is not bool:
            raise ApiError(422)
        data, headers = self._request('GET', '/audits/' + str(audit_id) + ('?include_deleted=true' if include_deleted else ''), token)
        etag = headers.get('etag')
        if etag is not None and not re.fullmatch(r'"[1-9][0-9]{0,9}"', etag):
            raise ApiError(502)
        return self._parse(Audit.parse, data, etag, include_deleted)

    @staticmethod
    def _condition(audit_id,etag):
        if type(audit_id) is not int or audit_id<1 or not isinstance(etag,str) or not re.fullmatch(r'"[1-9][0-9]{0,9}"',etag):
            raise ApiError(428,message='Reload this record to obtain its current version before saving.')
        return {'If-Match':etag}

    def create_audit(self,token,payload,key):
        from desktop.audit_operations import normalize, ValidationError
        try:
            key=str(UUID(key))
            payload=normalize(payload)
        except (ValueError,TypeError,AttributeError,ValidationError):
            raise ApiError(422) from None
        data,headers=self._request('POST','/audits',token,payload,{'Idempotency-Key':key})
        return self._parse(Audit.parse,data,headers.get('etag'))

    def update_audit(self,token,audit_id,payload,etag):
        from desktop.audit_operations import FIELDS
        condition=self._condition(audit_id,etag)
        if not payload or set(payload)-set(FIELDS):
            raise ApiError(422)
        data,headers=self._request('PATCH','/audits/'+str(audit_id),token,payload,condition)
        return self._parse(Audit.parse,data,headers.get('etag'))

    def delete_audit(self,token,audit_id,etag):
        data,_=self._request('DELETE','/audits/'+str(audit_id),token,conditional=self._condition(audit_id,etag))
        if data is not None:
            raise ApiError(502)

    def audit_history(self,token,audit_id,page=1,include_deleted=False):
        if type(audit_id) is not int or audit_id<1 or type(page) is not int or not 1<=page<=10000 or type(include_deleted) is not bool:
            raise ApiError(422)
        path=f'/audits/{audit_id}/history?page={page}&page_size=25'+('&include_deleted=true' if include_deleted else '')
        data,_=self._request('GET',path,token)
        return self._parse(EventPage.parse,data,audit_id)
