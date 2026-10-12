from abc import ABC, abstractmethod

from src.modules.communications.infrastructure.bale.models import BaleSendResult


class BaseBaleProvider(ABC):
    """Abstract interface for Bale Messenger Safir API provider."""

    @abstractmethod
    async def send_otp(
        self, phone_number: str, otp: str, request_id: str | None = None
    ) -> BaleSendResult:
        """Send a dedicated OTP verification code through Bale Safir API.

        Delivers the code using Bale's specialized verification-message bot
        with a native copy-code button and security styling.
        """
        pass

    @abstractmethod
    async def send_message(
        self, phone_number: str, text: str, request_id: str | None = None
    ) -> BaleSendResult:
        """Send a regular text or notification message via Bale Safir."""
        pass
