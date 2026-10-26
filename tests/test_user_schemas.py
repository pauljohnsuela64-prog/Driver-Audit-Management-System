import pytest
from pydantic import ValidationError
from backend.schemas.users import AccountResponse, UserCreate

PAYLOAD = {"username":"employee", "full_name":"Example Employee", "role":"AUDITOR",
           "password":"example passphrase only"}


def test_account_contract_normalization_and_secret_repr():
    value = UserCreate(**(PAYLOAD | {"username":" employee ", "full_name":" Example Employee "}))
    assert value.username == "employee" and value.full_name == "Example Employee"
    assert PAYLOAD["password"] not in repr(value)
    assert set(AccountResponse.model_fields) == {"id","username","full_name","role","is_active"}


@pytest.mark.parametrize("field,value", [
    ("username"," "), ("username","x"*101), ("username",23),
    ("full_name"," "), ("full_name","x"*201), ("role","OWNER"),
    ("password","short"), ("password"," "*20), ("password","x"*129),
    ("password",None), ("is_active",False), ("password_hash","forged"), ("id",1),
])
def test_invalid_account_input(field,value):
    with pytest.raises(ValidationError):
        UserCreate(**(PAYLOAD | {field:value}))


@pytest.mark.parametrize("field", PAYLOAD)
def test_required_account_fields(field):
    payload = dict(PAYLOAD)
    del payload[field]
    with pytest.raises(ValidationError):
        UserCreate(**payload)
