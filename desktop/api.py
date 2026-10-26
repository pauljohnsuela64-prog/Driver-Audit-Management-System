"""Small REST interface; no logging, redirect following or persisted credentials."""
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import http.client
import json
import re
import ssl
from urllib.parse import urlsplit

from desktop.config import Config
from desktop.models import Audit, AuditPage, Login, User, timestamp

MESSAGES = {
    401: ('unauthorized', 'Your credentials or session are no longer valid. Please sign in.'),
    403: ('forbidden', 'You do not have permission to view this content.'),
    404: ('not_found', 'This record is no longer available.'),
    409: ('conflict', 'This operation conflicts with the current server state.'),
    412: ('precondition_failed', 'This record has changed. Refresh before continuing.'),
    422: ('invalid_request', 'Check the supplied values and try again.'),
    429: ('rate_limited', 'Too many requests. Wait before trying again.'),
    500: ('internal_error', 'The service could not complete the request. Try again.'),
    503: ('service_unavailable', 'The service is temporarily unavailable. Try again.'),
}


class ApiError(Exception):
    def __init__(self, status=0, code='network_error', message=None, retry_after=0):
        default = MESSAGES.get(status, ('unexpected_response', 'The service returned an unexpected response.'))
        self.status = status
        self.code = default[0] if status else code
        self.retry_after = retry_after
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
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('Oversized response')
            return Reply(response.status, dict(response.getheaders()), raw)
        finally:
            connection.close()


def retry_seconds(value):
    try:
        if value.isdigit():
            return int(value)
        delta = parsedate_to_datetime(value) - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()) + 1)
    except (ValueError, TypeError, OverflowError):
        return 60


class ApiClient:
    def __init__(self, config: Config, transport=None):
        self.transport = transport or HttpTransport(config)

    def _request(self, method, path, token=None, payload=None):
        headers = {'Accept': 'application/json'}
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
            # Envelope text is deliberately not surfaced; status + known code are sufficient.
            raise ApiError(reply.status, retry_after=retry_seconds(response_headers.get('retry-after', '60')) if reply.status == 429 else 0)
        if reply.status == 204:
            return None, response_headers
        try:
            data = json.loads(reply.body)
            if not isinstance(data, dict):
                raise ValueError
            return data, response_headers
        except (ValueError, UnicodeError, TypeError):
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

    def list_audits(self, token, query):
        data, _ = self._request('GET', '/audits?' + query.encoded(), token)
        return self._parse(AuditPage.parse, data)

    def get_audit(self, token, audit_id):
        if type(audit_id) is not int or audit_id < 1:
            raise ApiError(422)
        data, headers = self._request('GET', '/audits/' + str(audit_id), token)
        etag = headers.get('etag')
        if etag is not None and not re.fullmatch(r'"[1-9][0-9]{0,9}"', etag):
            raise ApiError(502)
        return self._parse(Audit.parse, data, etag)
