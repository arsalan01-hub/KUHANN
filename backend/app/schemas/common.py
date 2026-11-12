"""Pydantic schemas shared by every router."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str
    detail: dict[str, Any] | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


def paginate(items: list[T], total: int, page: int, page_size: int) -> Page[T]:
    pages = (total + page_size - 1) // page_size if page_size else 0
    return Page[T](items=items, total=total, page=page, page_size=page_size, pages=pages)


# --------------------------------------------------------------------------- auth
class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)
    totp_code: str | None = Field(default=None, max_length=10)


class PermissionOut(ORMModel):
    id: str
    code: str
    description: str


class RoleOut(ORMModel):
    id: str
    name: str
    description: str
    is_system: bool
    permission_codes: list[str] = Field(default_factory=list)


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9_]+$")
    description: str = ""
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    description: str | None = None
    permissions: list[str] | None = None


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    totp_enabled: bool
    last_login_at: datetime | None = None
    created_at: datetime
    roles: list[RoleOut] = Field(default_factory=list)
    permission_codes: list[str] = Field(default_factory=list)


class UserCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    full_name: str = Field(default="", max_length=160)
    password: str = Field(min_length=10, max_length=256)
    roles: list[str] = Field(default_factory=list)
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=160)
    password: str | None = Field(default=None, min_length=10, max_length=256)
    roles: list[str] | None = None
    is_active: bool | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=256)


class TotpCode(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class TotpStatusResponse(BaseModel):
    totp_enabled: bool
    message: str
