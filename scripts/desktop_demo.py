"""Developer-only disposable demo. The shipping desktop entry point is unchanged.

Run `python -m scripts.desktop_demo` in a local console. Normal authentication,
authorization and audit services are used; no production configuration is read.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date,timedelta
from getpass import getpass,GetPassWarning
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from threading import Thread
import time
import warnings

import uvicorn
from backend.core.database import make_engine
from backend.main import create_app
from backend.models import Base
from backend.schemas.auth import BootstrapRequest
from backend.services.bootstrap import bootstrap_admin
from desktop.api import ApiClient
from desktop.config import Config


@dataclass(frozen=True)
class Demo:
    origin: str
    port: int
    database_file: Path


def _seed(origin,admin_password,auditor_password):
    client=ApiClient(Config(origin))
    admin=client.sign_in('demo_admin',admin_password)
    auditor=None
    def request(method,path,token,payload):
        # Developer fixture setup uses the same bounded direct HTTP transport:
        # no environment proxy routing and no redirect-based credential forwarding.
        return client._request(method,path,token,payload)[0]
    try:
        account=request('POST','/users',admin.token,dict(username='demo_auditor',
            full_name='Fictional Auditor (original)',role='AUDITOR',password=auditor_password))
        auditor=client.sign_in('demo_auditor',auditor_password)
        for index in range(60):
            token=admin.token if index%3==0 else auditor.token
            request('POST','/audits',token,dict(driver_name=f'Fictional Driver {index+1:03}',
                helper_name=None if index%2 else f'Fictional Helper {index+1:03}',
                audit_date=(date.today()-timedelta(days=index)).isoformat(),
                station=['Fictional North','Fictional Central','Fictional South'][index%3],
                plate_number=f'DEMO-{index//2+1:03}',
                remarks=None if index%4==0 else 'Disposable demonstration record. No business data. '+
                    ('Long remarks exercise wrapping and scrolling. '*80 if index==59 else '')))
        # Show that current profile names cannot rewrite historical audit snapshots.
        request('PATCH',f'/users/{account["id"]}',admin.token,dict(full_name='Demo Auditor'))
    finally:
        if auditor:
            client.logout(auditor.token)
        client.logout(admin.token)


@contextmanager
def demonstration(admin_password,auditor_password):
    """Own a fresh loopback HTTP server and SQLite directory; accept no DB URL/path."""
    # Validate before allocating resources, using the established password contract.
    for password in (admin_password,auditor_password):
        if not isinstance(password,str) or not 15<=len(password)<=128 or not password.strip():
            raise ValueError('Choose nonblank demo passwords of 15–128 characters')
    if admin_password==auditor_password:
        raise ValueError('Choose separate ADMIN and AUDITOR demo passwords')
    with TemporaryDirectory(prefix='dams-desktop-demo-') as directory:
        database=Path(directory).resolve()/'demo.sqlite3'
        engine=make_engine('sqlite:///'+database.as_posix())
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        server=None
        thread=None
        try:
            Base.metadata.create_all(engine)
            bootstrap_admin(engine,BootstrapRequest(username='demo_admin',full_name='Demo Administrator',
                                                   password=admin_password))
            listener.bind(('127.0.0.1',0))
            listener.listen(128)
            listener.setblocking(False)
            port=listener.getsockname()[1]
            origin=f'http://127.0.0.1:{port}'
            server=uvicorn.Server(uvicorn.Config(create_app(engine=engine),host='127.0.0.1',port=port,
                access_log=False,log_level='critical',proxy_headers=False,timeout_graceful_shutdown=2))
            thread=Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True,name='dams-disposable-api')
            thread.start()
            deadline=time.monotonic()+15
            while not server.started and thread.is_alive() and time.monotonic()<deadline:
                time.sleep(.02)
            if not server.started:
                raise RuntimeError('Disposable API could not start')
            _seed(origin,admin_password,auditor_password)
            admin_password=auditor_password=None
            yield Demo(origin,port,database)
        finally:
            if server:
                server.should_exit=True
            if thread:
                thread.join(timeout=8)
            listener.close()
            engine.dispose()
            if thread and thread.is_alive():
                raise RuntimeError('Disposable API did not shut down cleanly')


def main():
    print('BHLI Audit disposable demo — no production configuration or MySQL connections.')
    print('Choose two separate passwords. They stay in memory; enter them again at normal sign-in.')
    try:
        with warnings.catch_warnings():
            # Follow the existing administrator CLI: never fall back to echoed stdin.
            warnings.simplefilter('error',GetPassWarning)
            admin_password=getpass('ADMIN demo password (15–128 characters): ')
            auditor_password=getpass('AUDITOR demo password (15–128 characters): ')
        with demonstration(admin_password,auditor_password) as demo:
            admin_password=auditor_password=None
            print('Accounts: demo_admin (ADMIN), demo_auditor (AUDITOR). All 60 audits are fictional.')
            print('Close the application to stop this API and remove its temporary database.')
            from desktop.app import Application
            Application(ApiClient(Config(demo.origin))).mainloop()
    except (KeyboardInterrupt,EOFError):
        print('\nDemonstration canceled.')
    except GetPassWarning:
        raise SystemExit('Hidden password input is unavailable. Run in a local PowerShell console without redirected input.') from None
    except Exception:
        # Never print exceptions that could contain request or credential data.
        raise SystemExit('Demo could not complete. Check dependencies and use two separate valid passwords.') from None


if __name__=='__main__':
    main()
