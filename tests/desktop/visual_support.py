"""Fictional API data, used only by native tests and screenshot verification."""
import json
from urllib.parse import urlsplit, parse_qs
from tests.desktop.test_api import AUDIT, USER, TOKEN, reply


class DemoTransport:
    def __init__(self):
        self.role = 'ADMIN'
        self.requests = []
        self.mode = 'normal'
        self.gate = None

    def __call__(self, method, path, headers, body):
        self.requests.append((method, path))
        if path == '/auth/login':
            username = json.loads(body)['username']
            if username == 'wrong':
                return reply(status=401)
            self.role = 'AUDITOR' if username == 'auditor' else 'ADMIN'
            return reply(dict(access_token=TOKEN, token_type='bearer', expires_at='2099-01-01T00:00:00Z'))
        if path == '/auth/me':
            return reply(dict(USER, role=self.role, full_name='Example Employee'))
        if path == '/auth/logout':
            return reply(status=204)
        if path.startswith('/audits?'):
            if self.gate is not None:
                self.gate.wait(5)
            if self.mode == 'offline':
                raise OSError('private diagnostic must stay hidden')
            query = parse_qs(urlsplit(path).query)
            items = [] if self.mode == 'empty' else [dict(AUDIT, id=i, driver_name=name,
                station=station, plate_number=f'EXAMPLE-{i}', helper_name='Example Helper' if i%2 else None,
                remarks='Fictional verification record. Original auditor attribution is preserved.')
                for i,name,station in [(3,'Example Driver Three','North Station'),
                                       (2,'Example Driver Two','Central Station'),
                                       (1,'Example Driver One','South Station')]]
            return reply(dict(items=items, total=len(items), page=int(query.get('page',['1'])[0]),
                              page_size=int(query.get('page_size',['25'])[0])))
        if path.startswith('/audits/'):
            return reply(dict(AUDIT,id=int(path.rsplit('/',1)[1]),remarks='Fictional verification record.\nNo production data is used.'), etag='"2"')
        raise AssertionError('Unexpected desktop route')
