import re
import uuid
from typing import Any

import httpx

from src.app.observability.logging import get_logger
from src.modules.communications.infrastructure.bale.base import BaseBaleProvider
from src.modules.communications.infrastructure.bale.models import BaleSendResult

logger = get_logger("communications.bale.safir")


def format_bale_phone(phone_number: str) -> str:
    """Format an Iranian mobile phone number to Bale's required format (989XXXXXXXXX).

    Bale Safir API requires numbers to include Iran's country code (98)
    without leading plus (+), zero (0), spaces or hyphens.
    Example: '09121234567' -> '989121234567'.
    """
    digits = re.sub(r"[^\d]", "", phone_number.strip())
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]

    # Now digits should be 10 digits starting with 9 (e.g. 9121234567)
    if not (len(digits) == 10 and digits.startswith("9")):
        raise ValueError(f"شماره موبایل وارد شده نامعتبر است: {phone_number}")

    return f"98{digits}"


class BaleSafirProvider(BaseBaleProvider):
    """Official Bale (بله) Safir Messaging Gateway Provider.

    Documentation: https://docs.bale.ai/safir
    Endpoint: POST https://safir.bale.ai/api/v3/send_message
    Header: api-access-key: YOUR_API_ACCESS_KEY
    """

    def __init__(
        self,
        api_access_key: str,
        bot_id: int,
        base_url: str = "https://safir.bale.ai/api/v3",
        timeout_seconds: float = 10.0,
    ):
        self.api_access_key = api_access_key.strip()
        self.bot_id = bot_id
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _validate_config(self) -> None:
        if not self.api_access_key:
            raise ValueError("Bale API Access Key is missing or empty.")
        if self.bot_id <= 0:
            raise ValueError("Bale Bot ID must be a positive integer.")

    async def send_otp(
        self, phone_number: str, otp: str, request_id: str | None = None
    ) -> BaleSendResult:
        """Send a dedicated OTP verification code through Bale Safir.

        Payload format:
        {
            "request_id": "...",
            "bot_id": 123456789,
            "phone_number": "989121234567",
            "message_data": {
                "otp_message": {
                    "otp": "12345"
                }
            }
        }
        """
        req_id = request_id or uuid.uuid4().hex
        try:
            formatted_phone = format_bale_phone(phone_number)
        except ValueError as err:
            logger.warning("Invalid phone number passed to Bale Safir", phone=phone_number, error=str(err))
            return BaleSendResult(
                success=False,
                phone_number=phone_number,
                error_code=8,
                error_description=str(err),
                request_id=req_id,
            )

        payload = {
            "request_id": req_id,
            "bot_id": self.bot_id,
            "phone_number": formatted_phone,
            "message_data": {
                "otp_message": {
                    "otp": str(otp).strip(),
                }
            },
        }

        return await self._execute_send(formatted_phone, payload, req_id, is_otp=True)

    async def send_message(
        self, phone_number: str, text: str, request_id: str | None = None
    ) -> BaleSendResult:
        """Send a regular text notification message through Bale Safir.

        Payload format:
        {
            "request_id": "...",
            "bot_id": 123456789,
            "phone_number": "989121234567",
            "message_data": {
                "message": {
                    "text": "..."
                }
            }
        }
        """
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

        payload = {
            "request_id": req_id,
            "bot_id": self.bot_id,
            "phone_number": formatted_phone,
            "message_data": {
                "message": {
                    "text": text,
                }
            },
        }

        return await self._execute_send(formatted_phone, payload, req_id, is_otp=False)

    async def _execute_send(
        self,
        formatted_phone: str,
        payload: dict[str, Any],
        request_id: str,
        is_otp: bool,
    ) -> BaleSendResult:
        try:
            self._validate_config()
        except ValueError as e:
            logger.error("Bale Safir misconfigured", error=str(e))
            return BaleSendResult(
                success=False,
                phone_number=formatted_phone,
                error_code=2,
                error_description=str(e),
                request_id=request_id,
            )

        endpoint = f"{self.base_url}/send_message"
        headers = {
            "api-access-key": self.api_access_key,
            "Content-Type": "application/json",
        }

        logger.info(
            "Dispatching %s to Bale Safir API",
            "OTP verification code" if is_otp else "text message",
            phone=formatted_phone,
            request_id=request_id,
            bot_id=self.bot_id,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(endpoint, json=payload, headers=headers)

            try:
                data = response.json()
            except Exception:
                data = {}

            # Check for Bale error_data in response body
            error_data = data.get("error_data")
            if error_data:
                err_code, err_desc = self._parse_error_data(error_data)
                logger.warning(
                    "Bale Safir API rejected request",
                    phone=formatted_phone,
                    request_id=request_id,
                    error_code=err_code,
                    error_description=err_desc,
                )
                return BaleSendResult(
                    success=False,
                    phone_number=formatted_phone,
                    error_code=err_code,
                    error_description=err_desc,
                    request_id=request_id,
                )

            # Check HTTP status
            if response.status_code not in (200, 201):
                desc = data.get("message") or data.get("description") or response.text or "HTTP Error"
                code = 2
                if response.status_code == 429:
                    code = 3
                elif response.status_code in (401, 403):
                    code = 401
                logger.error(
                    "Bale Safir HTTP error",
                    status_code=response.status_code,
                    phone=formatted_phone,
                    response_text=response.text,
                )
                return BaleSendResult(
                    success=False,
                    phone_number=formatted_phone,
                    error_code=code,
                    error_description=f"HTTP {response.status_code}: {desc}",
                    request_id=request_id,
                )

            # Extract message_id
            message_id = data.get("message_id")
            if not message_id:
                logger.warning("Bale Safir returned 200 but message_id is missing", data=data)
                return BaleSendResult(
                    success=False,
                    phone_number=formatted_phone,
                    error_code=2,
                    error_description="Bale response is missing message_id.",
                    request_id=request_id,
                )

            logger.info(
                "Successfully dispatched to Bale Safir",
                phone=formatted_phone,
                message_id=str(message_id),
                request_id=request_id,
            )
            return BaleSendResult(
                success=True,
                phone_number=formatted_phone,
                message_id=str(message_id),
                request_id=request_id,
            )

        except httpx.TimeoutException as exc:
            logger.error("Bale Safir API request timed out", phone=formatted_phone, error=str(exc))
            return BaleSendResult(
                success=False,
                phone_number=formatted_phone,
                error_code=2,
                error_description="Bale Safir connection timed out.",
                request_id=request_id,
            )
        except Exception as exc:
            logger.exception("Unexpected error while communicating with Bale Safir", phone=formatted_phone, error=str(exc))
            return BaleSendResult(
                success=False,
                phone_number=formatted_phone,
                error_code=2,
                error_description=str(exc),
                request_id=request_id,
            )

    @staticmethod
    def _parse_error_data(error_data: Any) -> tuple[int, str]:
        """Extract primary error code and description from error_data structure."""
        if isinstance(error_data, list) and len(error_data) > 0:
            first_err = error_data[0]
            if isinstance(first_err, dict):
                code = int(first_err.get("code", 2))
                desc = str(first_err.get("description", first_err.get("message", "Bale error")))
                return code, desc
        elif isinstance(error_data, dict):
            code = int(error_data.get("code", 2))
            desc = str(error_data.get("description", error_data.get("message", "Bale error")))
            return code, desc

        return 2, str(error_data)
