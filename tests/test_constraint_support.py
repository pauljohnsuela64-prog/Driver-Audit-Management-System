import pytest
from sqlalchemy.exc import OperationalError
from tests.constraint_support import constraint_violation


def test_mysql_check_error_is_accepted():
    with constraint_violation():
        raise OperationalError("test", {}, Exception(3819, "CHECK violated"))


def test_unrelated_operational_error_is_not_accepted():
    with pytest.raises(AssertionError, match="Unexpected operational failure"):
        with constraint_violation():
            raise OperationalError("test", {}, Exception(2006, "connection lost"))
