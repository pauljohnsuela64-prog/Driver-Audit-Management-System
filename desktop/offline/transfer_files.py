"""Bounded reads and exclusive publication, with no supplied path extraction."""
import os
from pathlib import Path
import tempfile
from .models import OfflineError

MAX_BYTES = 32 * 1024 * 1024
CHUNK = 64 * 1024

def _cancel(cancel):
    if cancel():
        raise OfflineError('cancelled', 'Transfer cancelled before completion.')

def read_transfer(path, *, cancel=lambda: False, limit=MAX_BYTES):
    try:
        with open(path, 'rb') as stream:
            result = bytearray()
            while True:
                _cancel(cancel)
                chunk = stream.read(min(CHUNK, limit + 1 - len(result)))
                if not chunk:
                    return bytes(result)
                result.extend(chunk)
                if len(result) > limit:
                    raise OfflineError('transfer', 'This transfer file exceeds 32 MiB. Ask for a narrower date range.')
    except OSError:
        raise OfflineError('file', 'The transfer file could not be read. Check access and retry.') from None

def publish_transfer(path, raw, *, cancel=lambda: False):
    """Flush a private sibling, then exclusively publish its completed bytes.

    Return False only when the published file is complete but staging cleanup
    failed. Publication never replaces an existing destination, including races.
    """
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise OfflineError('transfer', 'The transfer exceeds 32 MiB. Select a narrower date range.')
    temporary = None
    published = False
    cleanup = True
    try:
        _cancel(cancel)
        target = Path(path)
        with tempfile.NamedTemporaryFile(prefix='.bhli-transfer-', suffix='.tmp', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            for offset in range(0, len(raw), CHUNK):
                _cancel(cancel)
                stream.write(raw[offset:offset + CHUNK])
            stream.flush()
            os.fsync(stream.fileno())
        _cancel(cancel)
        if os.name == 'nt':
            # Windows rename fails if target exists and also supports FAT/exFAT.
            os.rename(temporary, target)
            temporary = None
        else:
            os.link(temporary, target)
        published = True
    except FileExistsError:
        raise OfflineError('exists', 'A file already exists at this name. Choose a new filename; it was not replaced.') from None
    except OSError:
        raise OfflineError('file', 'The transfer file could not be saved. Check disk space and folder access, then choose a new filename.') from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                cleanup = False
                if not published:
                    raise OfflineError('file', 'The transfer did not complete. An owned temporary file could not be removed from the selected folder. Check disk space and folder access before retrying.') from None
    return cleanup if published else False
