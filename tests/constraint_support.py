"""Accept only database constraint violations across SQLite and PyMySQL."""
from contextlib import contextmanager

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError


@contextmanager
def constraint_violation():
    # PyMySQL classifies MySQL CHECK error 3819 as OperationalError.
    with pytest.raises((IntegrityError, OperationalError)) as caught:
        yield
    error = caught.value
    if isinstance(error, OperationalError):
        assert error.orig.args[0] == 3819, "Unexpected operational failure, not a CHECK violation"
