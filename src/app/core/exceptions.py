from typing import Any


class AppException(Exception):
    """Base application exception for all domain and operational errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class EntityNotFoundException(AppException):
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(
            message=f"{entity_name} with identifier '{entity_id}' was not found.",
            code="ENTITY_NOT_FOUND",
            status_code=404,
            details={"entity": entity_name, "id": str(entity_id)},
        )


class EntityConflictException(AppException):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="ENTITY_CONFLICT",
            status_code=409,
            details=details,
        )


class FinancialCalculationException(AppException):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="CALCULATION_ERROR",
            status_code=422,
            details=details,
        )


class ExternalProviderException(AppException):
    def __init__(self, provider: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=f"External provider '{provider}' failure: {message}",
            code="PROVIDER_ERROR",
            status_code=502,
            details={"provider": provider, **(details or {})},
        )


class AuthenticationException(AppException):
    def __init__(
        self,
        message: str = "Invalid authentication credentials.",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="AUTHENTICATION_FAILED",
            status_code=401,
            details=details,
        )


class PermissionDeniedException(AppException):
    def __init__(
        self,
        message: str = "Insufficient permissions to perform this action.",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            status_code=403,
            details=details,
        )


class InvalidOperationException(AppException):
    def __init__(
        self,
        message: str = "Invalid operation requested.",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="INVALID_OPERATION",
            status_code=400,
            details=details,
        )


class AccountLockedException(AppException):
    def __init__(
        self,
        message: str = "حساب کاربری به دلیل تلاش‌های ناموفق مکرر موقتاً قفل شده است.",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="ACCOUNT_LOCKED",
            status_code=403,
            details=details,
        )



