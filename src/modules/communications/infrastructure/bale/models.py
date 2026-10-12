from dataclasses import dataclass

from src.app.core.exceptions import AppException


@dataclass(frozen=True)
class BaleSendResult:
    """Represents the outcome of sending an OTP or message via Bale Safir API."""

    success: bool
    phone_number: str
    message_id: str | None = None
    error_code: int | None = None
    error_description: str | None = None
    request_id: str | None = None

    @property
    def is_not_bale_user(self) -> bool:
        """Code 17: User is not registered on Bale Messenger."""
        return self.error_code == 17

    @property
    def is_rate_limited(self) -> bool:
        """Code 3: Bot or account rate limit exceeded."""
        return self.error_code == 3

    @property
    def is_invalid_phone(self) -> bool:
        """Code 8: Recipient phone number is invalid."""
        return self.error_code == 8

    @property
    def is_payment_required(self) -> bool:
        """Code 20: Insufficient business credit/wallet balance on Bale."""
        return self.error_code == 20

    @property
    def is_server_error(self) -> bool:
        """Code 2: Bale Safir internal server error."""
        return self.error_code == 2


class BaleException(AppException):
    """Base exception for Bale messenger operations."""

    def __init__(self, message: str, code: str = "BALE_ERROR", status_code: int = 502, details: dict | None = None):
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class BaleNotUserException(BaleException):
    """Raised when the target phone number is not registered on Bale."""

    def __init__(self, phone_number: str):
        super().__init__(
            message=f"شماره {phone_number} در پیام‌رسان بله ثبت‌نام نکرده است.",
            code="BALE_NOT_USER",
            status_code=400,
            details={"phone_number": phone_number, "bale_code": 17},
        )


class BaleRateLimitException(BaleException):
    """Raised when Bale Safir rate limit is hit."""

    def __init__(self, message: str = "محدودیت نرخ ارسال پیام در بله فعال شده است."):
        super().__init__(
            message=message,
            code="BALE_RATE_LIMIT",
            status_code=429,
            details={"bale_code": 3},
        )
