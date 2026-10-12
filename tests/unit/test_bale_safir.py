import httpx
import pytest

from src.modules.communications.infrastructure.bale.mock_provider import MockBaleProvider
from src.modules.communications.infrastructure.bale.safir import (
    BaleSafirProvider,
    format_bale_phone,
)


def test_format_bale_phone():
    # Standard 11-digit Iranian mobile
    assert format_bale_phone("09123456789") == "989123456789"
    # International format with +98
    assert format_bale_phone("+989123456789") == "989123456789"
    # 0098 prefix
    assert format_bale_phone("00989123456789") == "989123456789"
    # Already without leading 0 or +
    assert format_bale_phone("989123456789") == "989123456789"
    # Formatted with spaces or hyphens
    assert format_bale_phone("0912-345-6789") == "989123456789"
    assert format_bale_phone("0912 345 6789") == "989123456789"

    # Invalid formats
    with pytest.raises(ValueError):
        format_bale_phone("12345")
    with pytest.raises(ValueError):
        format_bale_phone("02188888888")  # Landline
    with pytest.raises(ValueError):
        format_bale_phone("0900000000000")  # Too long


@pytest.mark.asyncio
async def test_bale_safir_send_otp_success(monkeypatch):
    captured_request = {}

    async def mock_post(client, url, json=None, headers=None, **kwargs):
        captured_request["url"] = str(url)
        captured_request["json"] = json
        captured_request["headers"] = headers
        return httpx.Response(
            status_code=200,
            json={"message_id": "bale_msg_99887766"},
            request=httpx.Request("POST", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = BaleSafirProvider(
        api_access_key="test-api-access-key",
        bot_id=123456,
        base_url="https://safir.bale.ai/api/v3",
    )

    result = await provider.send_otp(
        phone_number="09121234567",
        otp="54321",
        request_id="req-12345",
    )

    assert result.success is True
    assert result.message_id == "bale_msg_99887766"
    assert result.phone_number == "989121234567"
    assert result.request_id == "req-12345"

    # Verify request payload complies with Bale Safir documentation
    assert captured_request["url"] == "https://safir.bale.ai/api/v3/send_message"
    assert captured_request["headers"]["api-access-key"] == "test-api-access-key"
    payload = captured_request["json"]
    assert payload["bot_id"] == 123456
    assert payload["phone_number"] == "989121234567"
    assert payload["request_id"] == "req-12345"
    assert payload["message_data"]["otp_message"]["otp"] == "54321"


@pytest.mark.asyncio
async def test_bale_safir_not_bale_user_error(monkeypatch):
    """Test code 17 (NotBaleUser) response handling."""
    async def mock_post(client, url, json=None, headers=None, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "error_data": [
                    {
                        "phone_number": "989121234567",
                        "code": 17,
                        "description": "NotBaleUser",
                    }
                ]
            },
            request=httpx.Request("POST", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = BaleSafirProvider(api_access_key="key", bot_id=100)
    result = await provider.send_otp(phone_number="09121234567", otp="11223")

    assert result.success is False
    assert result.error_code == 17
    assert result.is_not_bale_user is True
    assert result.error_description == "NotBaleUser"


@pytest.mark.asyncio
async def test_bale_safir_rate_limit_error(monkeypatch):
    """Test code 3 (RateLimitExceeded) response handling."""
    async def mock_post(client, url, json=None, headers=None, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "error_data": [
                    {
                        "phone_number": "989121234567",
                        "code": 3,
                        "description": "RateLimitExceeded",
                    }
                ]
            },
            request=httpx.Request("POST", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = BaleSafirProvider(api_access_key="key", bot_id=100)
    result = await provider.send_otp(phone_number="09121234567", otp="11223")

    assert result.success is False
    assert result.error_code == 3
    assert result.is_rate_limited is True


@pytest.mark.asyncio
async def test_bale_safir_payment_required_error(monkeypatch):
    """Test code 20 (PaymentRequired) response handling."""
    async def mock_post(client, url, json=None, headers=None, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "error_data": [
                    {
                        "phone_number": "989121234567",
                        "code": 20,
                        "description": "PaymentRequired",
                    }
                ]
            },
            request=httpx.Request("POST", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = BaleSafirProvider(api_access_key="key", bot_id=100)
    result = await provider.send_otp(phone_number="09121234567", otp="11223")

    assert result.success is False
    assert result.error_code == 20
    assert result.is_payment_required is True


@pytest.mark.asyncio
async def test_bale_safir_network_timeout(monkeypatch):
    async def mock_post(client, url, **kwargs):
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = BaleSafirProvider(api_access_key="key", bot_id=100)
    result = await provider.send_otp(phone_number="09121234567", otp="11223")

    assert result.success is False
    assert result.error_code == 2
    assert "timed out" in result.error_description.lower()


@pytest.mark.asyncio
async def test_mock_bale_provider():
    mock = MockBaleProvider()

    # 1. Successful OTP send
    res1 = await mock.send_otp(phone_number="09121112233", otp="12345")
    assert res1.success is True
    assert res1.message_id is not None
    assert len(mock.sent_messages) == 1
    assert mock.sent_messages[0]["code"] == "12345"

    # 2. Number marked as non-Bale user returns code 17
    mock.add_non_bale_user("09129998877")
    res2 = await mock.send_otp(phone_number="09129998877", otp="99999")
    assert res2.success is False
    assert res2.is_not_bale_user is True
    assert res2.error_code == 17
