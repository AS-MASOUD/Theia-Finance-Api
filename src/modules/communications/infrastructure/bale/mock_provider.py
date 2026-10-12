import uuid
from typing import Any

from src.app.observability.logging import get_logger
from src.modules.communications.infrastructure.bale.base import BaseBaleProvider
from src.modules.communications.infrastructure.bale.models import BaleSendResult
from src.modules.communications.infrastructure.bale.safir import format_bale_phone

logger = get_logger("communications.bale.mock")


class MockBaleProvider(BaseBaleProvider):
    """Development / Testing Bale Provider.

    Simulates the official Bale Safir API locally without making network calls.
    Allows configuring specific phone numbers to simulate Bale error codes
    (e.g., NotBaleUser code 17 for SMS fallback verification).
    """

    def __init__(self):
        self.sent_messages: list[dict[str, Any]] = []
        # Phone numbers that will simulate code 17 (NotBaleUser)
        self.mock_non_bale_phones: set[str] = set()
        # Phone numbers that will simulate code 3 (RateLimitExceeded)
        self.mock_rate_limited_phones: set[str] = set()

    def add_non_bale_user(self, phone_number: str) -> None:
        """Mark a phone number as not having a Bale account for testing fallback."""
        try:
            formatted = format_bale_phone(phone_number)
            self.mock_non_bale_phones.add(formatted)
        except Exception:
            self.mock_non_bale_phones.add(phone_number)

    def add_rate_limited_user(self, phone_number: str) -> None:
        """Mark a phone number as rate limited for testing."""
        try:
            formatted = format_bale_phone(phone_number)
            self.mock_rate_limited_phones.add(formatted)
        except Exception:
            self.mock_rate_limited_phones.add(phone_number)

    def clear(self) -> None:
        """Clear sent messages and mock states."""
        self.sent_messages.clear()
        self.mock_non_bale_phones.clear()
        self.mock_rate_limited_phones.clear()

    async def send_otp(
        self, phone_number: str, otp: str, request_id: str | None = None
    ) -> BaleSendResult:
        req_id = request_id or uuid.uuid4().hex
        try:
            formatted_phone = format_bale_phone(phone_number)
        except ValueError as err:
            return BaleSendResult(
                success=False,
                phone_number=phone_number,
                error_code=8,
                error_description=str(err),
                request_id=req_id,
            )

        # Simulate NotBaleUser (code 17)
        if formatted_phone in self.mock_non_bale_phones or formatted_phone.endswith("999"):
            logger.info("🔑 [MOCK BALE] Simulated NotBaleUser (17) for %s", formatted_phone)
            return BaleSendResult(
                success=False,
                phone_number=formatted_phone,
                error_code=17,
                error_description="NotBaleUser: Target phone number has no account on Bale",
                request_id=req_id,
            )

        # Simulate RateLimitExceeded (code 3)
        if formatted_phone in self.mock_rate_limited_phones:
            logger.info("🔑 [MOCK BALE] Simulated RateLimitExceeded (3) for %s", formatted_phone)
            return BaleSendResult(
                success=False,
                phone_number=formatted_phone,
                error_code=3,
                error_description="RateLimitExceeded: Message rate limit reached",
                request_id=req_id,
            )

        mock_msg_id = f"bale_msg_{uuid.uuid4().hex[:12]}"
        logger.info(
            "🔑 [MOCK BALE OTP DISPATCHED] Phone: %s | MessageId: %s | Code: [REDACTED]",
            formatted_phone,
            mock_msg_id,
        )

        self.sent_messages.append(
            {
                "phone": formatted_phone,
                "code": otp,
                "message_id": mock_msg_id,
                "request_id": req_id,
                "type": "otp",
            }
        )

        # Ensure existing test fixtures that inspect SMS mock receive the dispatched OTP code
        try:
            from src.modules.communications.infrastructure.sms.factory import get_sms_provider

            sms_prov = get_sms_provider()
            if hasattr(sms_prov, "sent_messages"):
                sms_prov.sent_messages.append(
                    {
                        "phone": formatted_phone,
                        "code": otp,
                        "message_id": mock_msg_id,
                        "request_id": req_id,
                        "type": "bale_otp",
                    }
                )
        except Exception:
            pass

        return BaleSendResult(
            success=True,
            phone_number=formatted_phone,
            message_id=mock_msg_id,
            request_id=req_id,
        )

    async def send_message(
        self, phone_number: str, text: str, request_id: str | None = None
    ) -> BaleSendResult:
        req_id = request_id or uuid.uuid4().hex
        try:
            formatted_phone = format_bale_phone(phone_number)
        except ValueError as err:
            return BaleSendResult(
                success=False,
                phone_number=phone_number,
                error_code=8,
                error_description=str(err),
                request_id=req_id,
            )

        if formatted_phone in self.mock_non_bale_phones:
            return BaleSendResult(
                success=False,
                phone_number=formatted_phone,
                error_code=17,
                error_description="NotBaleUser",
                request_id=req_id,
            )

        mock_msg_id = f"bale_msg_{uuid.uuid4().hex[:12]}"
        self.sent_messages.append(
            {
                "phone": formatted_phone,
                "text": text,
                "message_id": mock_msg_id,
                "request_id": req_id,
                "type": "text",
            }
        )

        return BaleSendResult(
            success=True,
            phone_number=formatted_phone,
            message_id=mock_msg_id,
            request_id=req_id,
        )
