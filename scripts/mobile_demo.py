"""Developer-only, disposable loopback API for Android; no production config."""
from contextlib import contextmanager
from dataclasses import dataclass
from getpass import GetPassWarning,getpass
from pathlib import Path
import secrets
import time
import warnings

from desktop.api import ApiClient
from desktop.config import Config
from scripts.desktop_demo import demonstration


@dataclass(frozen=True)
class MobileDemo:
    origin: str
    port: int
    database_file: Path


@contextmanager
def mobile_demonstration(admin_password,auditor_password):
    for password in (admin_password,auditor_password):
        if not isinstance(password,str) or not 15<=len(password)<=128 or not password.strip():
            raise ValueError('Choose separate nonblank demo passwords of 15-128 characters')
    if admin_password==auditor_password:
        raise ValueError('Use separate demo passwords')
    # Existing fixture owns its temporary SQLite engine and loopback listener.
    with demonstration(admin_password,secrets.token_urlsafe(24)) as demo:
        client=ApiClient(Config(demo.origin))
        admin=client.sign_in('demo_admin',admin_password)
        try:
            accounts=client._request('GET','/users?search=demo_auditor',admin.token)[0]['items']
            target=next(account for account in accounts if account['username']=='demo_auditor')
            client.reset_admin_password(admin.token,target['id'],admin_password,auditor_password)
        finally:
            client.logout(admin.token)
        admin_password=auditor_password=None
        yield MobileDemo(demo.origin,demo.port,demo.database_file)


def main():
    print('BHLI Audit Android demo: temporary fictional SQLite/API, no production configuration.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',GetPassWarning)
            admin=getpass('Choose demo_admin password (15-128 characters): ')
            auditor=getpass('Choose separate demo_auditor password (15-128 characters): ')
        with mobile_demonstration(admin,auditor) as demo:
            admin=auditor=None
            print('Accounts: demo_admin (ADMIN), demo_auditor (AUDITOR). All records are fictional.')
            print('API origin:',demo.origin)
            print(f'ADB: adb -s <test-device-serial> reverse tcp:{demo.port} tcp:{demo.port}')
            print('Use that loopback origin in the explicit debug-loopback build. Ctrl+C removes this fixture.')
            while True:time.sleep(.5)
    except KeyboardInterrupt:
        print('\nDemo stopped; temporary API/database removed.')
    except (EOFError,GetPassWarning):
        raise SystemExit('Hidden input unavailable. Use a local interactive terminal; never put passwords in arguments.') from None
    except Exception:
        raise SystemExit('Demo could not start. Check dependencies and separate valid demo passwords.') from None


if __name__=='__main__':main()
