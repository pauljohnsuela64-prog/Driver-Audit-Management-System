"""Session data has one main-thread owner and is never persisted."""
from datetime import datetime, timezone


class SessionState:
    def __init__(self):
        self.login = None
        self.generation = 0

    def set(self, login):
        self.generation += 1
        self.login = login

    def clear(self):
        previous = self.login
        self.login = None
        self.generation += 1
        return previous

    def expired(self, now=None):
        return self.login is None or self.login.expires_at <= (now or datetime.now(timezone.utc))

    @property
    def destinations(self):
        if self.login is None:
            return ()
        common = ('Dashboard', 'Driver Audits')
        admin = ('Employee Accounts', 'Administrator Activity') if self.login.user.role == 'ADMIN' else ()
        return common + admin + ('My Account',)
