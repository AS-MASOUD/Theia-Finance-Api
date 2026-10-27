import re

from pydantic import BaseModel, Field, field_validator

from src.app.database.models import SystemRole
from src.modules.auth.application.dtos import UserResponse

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PASSWORD_REGEX = re.compile(r"^(?=.*[a-z])(?=.*\d)(?=.*[^a-zA-Z0-9\s]).{8,128}$")

class UserCreateRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=128, description="Initial password")
    full_name: str = Field(..., min_length=2, max_length=50, description="Full name")
    role: SystemRole = Field(default=SystemRole.USER, description="System role to assign")
    is_active: bool = Field(default=True, description="Account active status")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 2 or len(clean) > 50:
            raise ValueError("نام و نام خانوادگی باید بین ۲ تا ۵۰ کاراکتر باشد.")
        return clean

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("قالب آدرس ایمیل نامعتبر است.")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not PASSWORD_REGEX.match(v):
            raise ValueError("رمز عبور باید حداقل ۸ کاراکتر و شامل حروف کوچک انگلیسی (a-z)، عدد و نماد یا علامت ویژه (مانند !@#$) باشد.")
        return v

class UserUpdateRoleRequest(BaseModel):
    role: SystemRole = Field(..., description="New system role")

class UserUpdateStatusRequest(BaseModel):
    is_active: bool = Field(..., description="New active status")

class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=50)
    email: str | None = Field(default=None)
    role: SystemRole | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip()
        if len(clean) < 2 or len(clean) > 50:
            raise ValueError("نام و نام خانوادگی باید بین ۲ تا ۵۰ کاراکتر باشد.")
        return clean

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("قالب آدرس ایمیل نامعتبر است.")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not PASSWORD_REGEX.match(v):
            raise ValueError("رمز عبور باید حداقل ۸ کاراکتر و شامل حروف کوچک انگلیسی (a-z)، عدد و نماد یا علامت ویژه (مانند !@#$) باشد.")
        return v

class RoleDefinitionResponse(BaseModel):
    role: str
    name_fa: str
    name_en: str
    description_fa: str
    description_en: str
    badge_color: str
    permissions: list[str]

class UserListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: list[UserResponse]
