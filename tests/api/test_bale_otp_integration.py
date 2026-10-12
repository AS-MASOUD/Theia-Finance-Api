import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from src.app.database.models import OTPRequestModel
from src.main import app
from src.modules.communications.infrastructure.bale.factory import get_bale_provider
from src.modules.communications.infrastructure.sms.factory import get_sms_provider
from tests.conftest import TestSessionFactory


@pytest.mark.asyncio
async def test_bale_otp_default_delivery_and_verification():
    """Verify that by default (bale_first strategy), OTP is delivered via Bale Safir and verifiable."""
    test_phone = "09123333333"

    async with TestSessionFactory() as db:
        await db.execute(delete(OTPRequestModel).where(OTPRequestModel.identifier == test_phone))
        await db.commit()

    bale_provider = get_bale_provider()
    bale_provider.clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request login OTP (09123333333 is user account seeded in system)
        res = await client.post(
            "/api/v1/auth/otp/request",
            json={"identifier": test_phone},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["channel"] == "bale"
        assert data["identifier"] == test_phone
        assert "بله" in data["message"]

        # Ensure Bale mock received the OTP with proper Bale format (989...)
        assert len(bale_provider.sent_messages) >= 1
        last_bale_msg = bale_provider.sent_messages[-1]
        assert last_bale_msg["phone"] == "989123333333"
        otp_code = last_bale_msg["code"]
        assert len(otp_code) >= 5

        # Verify OTP code to log in
        verify_res = await client.post(
            "/api/v1/auth/otp/verify",
            json={"identifier": test_phone, "code": otp_code},
        )
        assert verify_res.status_code == 200
        token_data = verify_res.json()
        assert token_data["user"]["phone_number"] == test_phone
        assert "access_token" in token_data


@pytest.mark.asyncio
async def test_bale_otp_fallback_to_sms_when_not_bale_user():
    """Verify that when a user is not registered on Bale (code 17), the system smoothly falls back to SMS."""
    test_phone = "09123333333"

    async with TestSessionFactory() as db:
        await db.execute(delete(OTPRequestModel).where(OTPRequestModel.identifier == test_phone))
        await db.commit()

    bale_provider = get_bale_provider()
    sms_provider = get_sms_provider()
    bale_provider.clear()
    sms_provider.sent_messages.clear()

    # Mark the phone as not registered on Bale (simulates error code 17 - NotBaleUser)
    bale_provider.add_non_bale_user(test_phone)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/otp/request",
            json={"identifier": test_phone},
        )
        assert res.status_code == 200
        data = res.json()

        # Channel must report SMS fallback
        assert data["channel"] == "sms"
        assert data["identifier"] == test_phone

        # SMS mock received the fallback OTP
        assert len(sms_provider.sent_messages) >= 1
        dispatched_sms_code = sms_provider.sent_messages[-1]["code"]

        # Verification succeeds with SMS code
        verify_res = await client.post(
            "/api/v1/auth/otp/verify",
            json={"identifier": test_phone, "code": dispatched_sms_code},
        )
        assert verify_res.status_code == 200


@pytest.mark.asyncio
async def test_bale_otp_user_registration_flow():
    """Verify user registration flow with Bale OTP delivery."""
    new_phone = f"0912{uuid.uuid4().int % 9000000 + 1000000}"
    bale_provider = get_bale_provider()
    bale_provider.clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request registration OTP via Bale
        reg_otp_res = await client.post(
            "/api/v1/auth/register/otp/request",
            json={
                "phone_number": new_phone,
                "password": "SecurePassword123!",
                "full_name": "کاربر تستی بله",
                "channel": "bale",
            },
        )
        assert reg_otp_res.status_code == 200
        otp_info = reg_otp_res.json()
        assert otp_info["channel"] == "bale"

        dispatched_code = bale_provider.sent_messages[-1]["code"]

        # Finalize registration with Bale OTP
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "phone_number": new_phone,
                "password": "SecurePassword123!",
                "full_name": "کاربر تستی بله",
                "code": dispatched_code,
            },
        )
        assert reg_res.status_code == 201
        assert reg_res.json()["user"]["phone_number"] == new_phone

        # Login with new user via Bale OTP
        login_otp_req = await client.post(
            "/api/v1/auth/otp/request",
            json={"identifier": new_phone},
        )
        assert login_otp_req.status_code == 200
        login_code = bale_provider.sent_messages[-1]["code"]

        login_verify = await client.post(
            "/api/v1/auth/otp/verify",
            json={"identifier": new_phone, "code": login_code},
        )
        assert login_verify.status_code == 200
        assert login_verify.json()["user"]["phone_number"] == new_phone


@pytest.mark.asyncio
async def test_bale_explicit_channel_selection():
    """Verify explicit channel selection between 'bale' and 'sms'."""
    test_phone = "09123333333"

    async with TestSessionFactory() as db:
        await db.execute(delete(OTPRequestModel).where(OTPRequestModel.identifier == test_phone))
        await db.commit()

    bale_provider = get_bale_provider()
    sms_provider = get_sms_provider()
    bale_provider.clear()
    sms_provider.sent_messages.clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Explicit request via SMS
        sms_res = await client.post(
            "/api/v1/auth/otp/request",
            json={"identifier": test_phone, "channel": "sms"},
        )
        assert sms_res.status_code == 200
        assert sms_res.json()["channel"] == "sms"
        assert len(sms_provider.sent_messages) == 1
        assert len(bale_provider.sent_messages) == 0

        # Wait or clean db to bypass cooldown for second request
        async with TestSessionFactory() as db:
            await db.execute(delete(OTPRequestModel).where(OTPRequestModel.identifier == test_phone))
            await db.commit()

        # Explicit request via Bale
        bale_res = await client.post(
            "/api/v1/auth/otp/request",
            json={"identifier": test_phone, "channel": "bale"},
        )
        assert bale_res.status_code == 200
        assert bale_res.json()["channel"] == "bale"
        assert len(bale_provider.sent_messages) == 1
