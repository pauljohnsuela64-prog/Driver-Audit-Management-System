"""Desktop-only settings; deliberately does not read the server's .env."""
from dataclasses import dataclass
import ipaddress
from urllib.parse import urlsplit


@dataclass(frozen=True, repr=False)
class Config:
    base_url: str = 'http://127.0.0.1:8000'
    connect_timeout: float = 5
    read_timeout: float = 15

    def __post_init__(self):
        try:
            u = urlsplit(self.base_url)
            port = u.port
            host = u.hostname
            loopback = host == 'localhost'
            if not loopback:
                try:
                    loopback = ipaddress.ip_address(host).is_loopback
                except ValueError:
                    pass
            if (not host or u.username is not None or u.password is not None or u.query or u.fragment
                    or u.path not in ('', '/') or '\\' in self.base_url
                    or any(ord(c) <= 32 for c in self.base_url)
                    or u.scheme not in ('http', 'https') or (u.scheme == 'http' and not loopback)
                    or (port is not None and not 1 <= port <= 65535)
                    or not 0 < self.connect_timeout <= 60 or not 0 < self.read_timeout <= 60):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError('Use a valid HTTPS service URL, or HTTP on loopback only') from None
        object.__setattr__(self, 'base_url', self.base_url.rstrip('/'))

    def __repr__(self):
        return 'Config(<service URL hidden>)'
