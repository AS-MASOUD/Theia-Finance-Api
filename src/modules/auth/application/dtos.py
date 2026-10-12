import re
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
IRAN_PHONE_REGEX = re.compile(r"^09\d{9}$")
PASSWORD_REGEX = re.compile(r"^(?=.*[a-z])(?=.*\d)(?=.*[^a-zA-Z0-9\s]).{8,128}$")


class UserRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=50, description="Full name")
    email: str | None = Field(default=None, description="User email address")
    phone_number: str | None = Field(default=None, description="Iranian mobile number (e.g. 09123456789)")
    password: str = Field(..., min_length=8, max_length=128, description="User password")
    code: str | None = Field(default=None, min_length=4, max_length=8, description="Optional OTP verification code")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not PASSWORD_REGEX.match(v):
            raise ValueError("Password must be at least 8 characters and include lowercase letters, numbers, and symbols.")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 2 or len(clean) > 50:
            raise ValueError("نام و نام خانوادگی باید بین ۲ تا ۵۰ کاراکتر باشد.")
        return clean

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        if not IRAN_PHONE_REGEX.match(clean):
            raise ValueError("شماره موبایل نامعتبر است. شماره باید با 09 شروع شده و دارای ۱۱ رقم باشد.")
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


class RegisterRequestOTP(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=50, description="Full name")
    phone_number: str = Field(..., description="Iranian mobile number (e.g. 09123456789)")
    email: str | None = Field(default=None, description="User email address")
    password: str | None = Field(default=None, min_length=8, max_length=128, description="User password")
    channel: str | None = Field(default=None, description="Preferred OTP channel: 'bale', 'sms', or None (auto)")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not PASSWORD_REGEX.match(v):
            raise ValueError("Password must be at least 8 characters and include letters, numbers, and symbols.")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 2 or len(clean) > 50:
            raise ValueError("نام و نام خانوادگی باید بین ۲ تا ۵۰ کاراکتر باشد.")
        return clean

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        clean = v.strip()
        if not IRAN_PHONE_REGEX.match(clean):
            raise ValueError("شماره موبایل نامعتبر است. شماره باید با 09 شروع شده و دارای ۱۱ رقم باشد.")
        return clean

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip().lower()
        if not clean:
            return None
        if not EMAIL_REGEX.match(clean):
            raise ValueError("قالب آدرس ایمیل نامعتبر است.")
        return clean


class RegisterVerifyOTPRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=50, description="Full name")
    phone_number: str = Field(..., description="Iranian mobile number (e.g. 09123456789)")
    email: str | None = Field(default=None, description="User email address")
    password: str | None = Field(default=None, min_length=8, max_length=128, description="User password")
    code: str = Field(..., min_length=4, max_length=8, description="OTP code received")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 2 or len(clean) > 50:
            raise ValueError("نام و نام خانوادگی باید بین ۲ تا ۵۰ کاراکتر باشد.")
        return clean

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        clean = v.strip()
        if not IRAN_PHONE_REGEX.match(clean):
            raise ValueError("شماره موبایل نامعتبر است. شماره باید با 09 شروع شده و دارای ۱۱ رقم باشد.")
        return clean

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip().lower()
        if not clean:
            return None
        if not EMAIL_REGEX.match(clean):
            raise ValueError("قالب آدرس ایمیل نامعتبر است.")
        return clean


class LoginWithPasswordRequest(BaseModel):
    identifier: str = Field(
        ...,
        description="User email address or mobile phone number (e.g. 09123456789 or user@example.com)",
    )
    password: str = Field(..., description="User password")


class RequestOTPRequest(BaseModel):
    identifier: str = Field(
        ...,
        description="Mobile phone number (e.g. 09123456789) or email address to receive OTP code",
    )
    channel: str | None = Field(
        default=None,
        description="Preferred OTP delivery channel: 'bale', 'sms', 'email', or None (auto-negotiated)",
    )


class LoginWithOTPRequest(BaseModel):
    identifier: str = Field(
        ...,
        description="Mobile phone number or email address",
    )
    code: str = Field(..., min_length=4, max_length=8, description="OTP code received")


class UserLoginRequest(BaseModel):
    """Backward compatible login request accepting either email or identifier."""
    email: str | None = Field(default=None, description="User email address")
    identifier: str | None = Field(default=None, description="Email or mobile number")
    password: str = Field(..., description="User password")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None = None
    phone_number: str | None = None
    full_name: str
    role: str
    age: int | None = None
    job: str | None = None
    bio: str | None = None
    monthly_income: Decimal | None = None
    liquid_assets: Decimal | None = None
    investment_assets: Decimal | None = None
    total_liabilities: Decimal | None = None
    financial_goals: list | None = None
    has_completed_financial_onboarding: bool = False
    risk_score: int | None = None
    risk_level: str | None = None
    risk_answers: dict | None = None
    portfolio_suggestion: dict | None = None
    has_completed_risk_onboarding: bool = False
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: datetime | None = None


class JobBenchmarkResponse(BaseModel):
    job_category: str
    average_salary_toman: Decimal
    min_salary_toman: Decimal
    max_salary_toman: Decimal
    user_salary_toman: Decimal
    comparison_ratio_percent: float
    status_fa: str
    suggestion_fa: str


class FinancialOnboardingRequest(BaseModel):
    job: str = Field(..., min_length=2, max_length=100)
    monthly_income: Decimal = Field(..., ge=0)
    liquid_assets: Decimal = Field(default=Decimal("0"), ge=0)
    investment_assets: Decimal = Field(default=Decimal("0"), ge=0)
    total_liabilities: Decimal = Field(default=Decimal("0"), ge=0)
    financial_goals: list[str] = Field(default_factory=list)


class FinancialOnboardingResponse(BaseModel):
    user: UserResponse
    benchmark: JobBenchmarkResponse
    message: str = "اطلاعات مالی و اهداف شما با موفقیت ثبت شد."


class RiskAssessmentRequest(BaseModel):
    answers: dict[str, int] = Field(..., description="Mapping of question index or key to chosen point (1-4)")
    custom_portfolio_allocation: dict[str, float] | None = Field(
        default=None, description="Optional custom target percentage allocation overrides"
    )


class RiskAssessmentResultResponse(BaseModel):
    total_score: int
    risk_level: str
    risk_title_fa: str
    description_fa: str
    portfolio_suggestion: dict[str, float]


class RiskOnboardingResponse(BaseModel):
    user: UserResponse
    risk_result: RiskAssessmentResultResponse
    message: str = "آزمون روانشناسی ریسک‌پذیری با موفقیت ثبت شد."


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=50)
    email: str | None = Field(default=None)
    phone_number: str | None = Field(default=None)
    age: int | None = Field(default=None, ge=10, le=120)
    job: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=500)
    portfolio_suggestion: dict[str, float] | None = Field(default=None)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        if len(clean) < 2 or len(clean) > 50:
            raise ValueError("نام و نام خانوادگی باید بین ۲ تا ۵۰ کاراکتر باشد.")
        return clean

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        clean = v.strip()
        if not IRAN_PHONE_REGEX.match(clean):
            raise ValueError("شماره موبایل نامعتبر است. شماره باید با 09 شروع شده و دارای ۱۱ رقم باشد.")
        return clean

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("قالب آدرس ایمیل نامعتبر است.")
        return clean


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class OTPResponse(BaseModel):
    identifier: str
    channel: str
    expires_in: int
    cooldown_seconds: int
    message: str = "کد یکبار مصرف با موفقیت ارسال شد."


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if not PASSWORD_REGEX.match(v):
            raise ValueError("New password must be at least 8 characters and include lowercase letters, numbers, and symbols.")
        return v

