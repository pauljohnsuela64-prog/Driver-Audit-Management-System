from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints, field_validator

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Username
    password: SecretStr

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value):
        if not 1 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Invalid password length")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str
    role: Literal["ADMIN", "AUDITOR"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class BootstrapRequest(LoginRequest):
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        if len(value.get_secret_value()) < 15:
            raise ValueError("Use at least 15 characters")
        return value
