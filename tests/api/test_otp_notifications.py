import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_password_login_with_phone_number_and_email():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Login with Iranian phone number
        phone_login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "identifier": "09121111111",
                "password": "AdminPassword123!",
            },
        )
        assert phone_login_res.status_code == 200
        phone_data = phone_login_res.json()
        assert phone_data["user"]["role"] == "sysmanager"
        assert phone_data["user"]["phone_number"] == "09121111111"

        # 2. Login with email
        email_login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "identifier": "sysmanager@personal-fc.local",
                "password": "AdminPassword123!",
            },
        )
        assert email_login_res.status_code == 200
        email_data = email_login_res.json()
        assert email_data["user"]["email"] == "sysmanager@personal-fc.local"


@pytest.mark.asyncio
async def test_otp_flow_phone_and_email():
    import uuid
    from src.modules.communications.infrastructure.sms.factory import get_sms_provider

    sms_provider = get_sms_provider()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Request OTP for existing phone number
        req_res = await client.post(
            "/api/v1/auth/otp/request",
            json={"identifier": "09122222222"},
        )
        assert req_res.status_code == 200
        otp_info = req_res.json()
        assert otp_info["channel"] == "sms"
        assert otp_info["identifier"] == "09122222222"
        # Verify debug_code is never exposed in response
        assert otp_info.get("debug_code") is None

        # Dispatched code from provider mock
        dispatched_code = sms_provider.sent_messages[-1]["code"]
        assert dispatched_code is not None

        # 2. Cooldown check - immediate repeat should return 429
        repeat_res = await client.post(
            "/api/v1/auth/otp/request",
            json={"identifier": "09122222222"},
        )
        assert repeat_res.status_code == 429

        # 3. Wrong OTP verification code fails
        wrong_verify = await client.post(
            "/api/v1/auth/otp/verify",
            json={"identifier": "09122222222", "code": "00000"},
        )
        assert wrong_verify.status_code == 401

        # 4. Correct OTP code logs in successfully
        correct_verify = await client.post(
            "/api/v1/auth/otp/verify",
            json={"identifier": "09122222222", "code": dispatched_code},
        )
        assert correct_verify.status_code == 200
        verified_data = correct_verify.json()
        assert verified_data["user"]["phone_number"] == "09122222222"
        assert verified_data["user"]["role"] == "admin"

        # 5. OTP for a non-existent phone number returns 404 (USER_NOT_FOUND)
        new_phone = f"0912{uuid.uuid4().int % 9000000 + 1000000}"
        new_req = await client.post(
            "/api/v1/auth/otp/request",
            json={"identifier": new_phone},
        )
        assert new_req.status_code == 404
        assert new_req.json()["error"]["code"] == "USER_NOT_FOUND"

        # 6. Request registration OTP for new user
        reg_otp_req = await client.post(
            "/api/v1/auth/register/otp/request",
            json={
                "phone_number": new_phone,
                "password": "ValidPassword123!",
                "full_name": "کاربر جدید تلفنی",
            },
        )
        assert reg_otp_req.status_code == 200
        new_reg_code = sms_provider.sent_messages[-1]["code"]

        # 7. Register the user with phone number, password, and mandatory OTP code
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "phone_number": new_phone,
                "password": "ValidPassword123!",
                "full_name": "کاربر جدید تلفنی",
                "code": new_reg_code,
            },
        )
        assert reg_res.status_code == 201
        assert reg_res.json()["user"]["phone_number"] == new_phone
        assert reg_res.json()["user"]["is_verified"] is True

        # 8. Now OTP login request succeeds for the registered user
        otp_req_reg = await client.post(
            "/api/v1/auth/otp/request",
            json={"identifier": new_phone},
        )
        assert otp_req_reg.status_code == 200
        new_login_code = sms_provider.sent_messages[-1]["code"]

        new_verify = await client.post(
            "/api/v1/auth/otp/verify",
            json={"identifier": new_phone, "code": new_login_code},
        )
        assert new_verify.status_code == 200
        new_user_data = new_verify.json()
        assert new_user_data["user"]["phone_number"] == new_phone
        assert new_user_data["user"]["role"] == "user"



@pytest.mark.asyncio
async def test_notifications_and_volatility_triggers():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Login to get token
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"identifier": "sysmanager@personal-fc.local", "password": "AdminPassword123!"},
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Fetch notifications
        res = await client.get("/api/v1/notifications", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "unread_count" in data
        assert len(data["items"]) >= 1

        first_notif = data["items"][0]
        notif_id = first_notif["id"]

        # 3. Mark single notification as read
        read_res = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=headers)
        assert read_res.status_code == 200
        assert read_res.json()["is_read"] is True

        # 4. Mark all as read
        all_res = await client.post("/api/v1/notifications/read-all", headers=headers)
        assert all_res.status_code == 200

        # 5. Check triggers
        trigger_res = await client.post("/api/v1/notifications/check-triggers")
        assert trigger_res.status_code == 200
