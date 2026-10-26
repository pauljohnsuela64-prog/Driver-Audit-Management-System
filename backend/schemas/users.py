"""Employee account input and credential-free output contracts."""
from typing import Literal

from pydantic import BaseModel, field_validator
from backend.schemas.auth import BootstrapRequest, UserResponse


class UserCreate(BootstrapRequest):
    role: Literal["ADMIN", "AUDITOR"]

    @field_validator("password")
    @classmethod
    def nonblank_password(cls, value):
        if not value.get_secret_value().strip():
            raise ValueError("Password must not be blank")
        return value


class AccountResponse(UserResponse):
    is_active: bool


class AccountPage(BaseModel):
    items: list[AccountResponse]
    total: int
    page: int
    page_size: int
