"""Bounded per-process login attempt limiter; gateway limits cover multiple workers."""
from collections import deque
from threading import Lock
from time import monotonic

from backend.core.errors import ServiceError


class LoginLimiter:
    def __init__(self, limit=10, window=60, capacity=4096):
        self.limit, self.window, self.capacity = limit, window, capacity
        self.entries = {}
        self.lock = Lock()

    def check(self, key):
        now = monotonic()
        with self.lock:
            for address in list(self.entries):
                events = self.entries[address]
                while events and events[0] <= now - self.window:
                    events.popleft()
                if not events:
                    del self.entries[address]
            events = self.entries.get(key)
            if ((events is not None and len(events) >= self.limit)
                    or (events is None and len(self.entries) >= self.capacity)):
                raise ServiceError(429, "rate_limited", "Too many login attempts; retry later")
            self.entries.setdefault(key, deque()).append(now)
