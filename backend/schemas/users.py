"""Employee account input and credential-free output contracts."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints, field_validator, model_validator
from backend.schemas.auth import BootstrapRequest, UserResponse, Username


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


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Username | None = None
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None

    @model_validator(mode="after")
    def supplied_fields(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Supply at least one non-null profile field")
        return self


class UserAccessPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["ADMIN", "AUDITOR"] | None = None
    is_active: StrictBool | None = None

    @model_validator(mode="after")
    def supplied_fields(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Supply at least one non-null access field")
        return self
