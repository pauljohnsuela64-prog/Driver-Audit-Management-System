"""Lifetime native ownership of one offline data directory.

The lock file is retained: unlinking a locked inode permits two owners. SQLite
still protects against older applications and tools which do not use this lease.
"""
import os
from pathlib import Path
import stat

from .models import OfflineError


class StoreLease:
    def __init__(self, directory, descriptor):
        self.directory = directory
        self._descriptor = descriptor

    @classmethod
    def acquire(cls, directory):
        directory = Path(directory).resolve(strict=True)
        path = directory / 'offline-store.lock'
        descriptor = None
        try:
            if path.is_symlink():
                raise OSError('Unsafe lock file')
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode) or path.is_symlink():
                raise OSError('Unsafe lock file')
            if os.name == 'nt':
                import msvcrt
                # Windows byte locks may extend beyond EOF; no pre-lock write.
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return cls(directory, descriptor)
        except OSError:
            if descriptor is not None:
                os.close(descriptor)
            raise OfflineError('store_owned', 'Close the other offline app using this data directory, then retry. If no other copy is open, check access to local storage.') from None

    @property
    def held(self):
        return self._descriptor is not None

    def release(self):
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None
