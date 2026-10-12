import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_auth_login_and_me():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Login with seeded sysmanager
        login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "sysmanager@personal-fc.local",
                "password": "AdminPassword123!",
            },
        )
        assert login_res.status_code == 200
        token_data = login_res.json()
        assert "access_token" in token_data
        assert token_data["user"]["role"] == "sysmanager"
        assert token_data["user"]["email"] == "sysmanager@personal-fc.local"

        token = token_data["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Get me with bearer token
        me_res = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == "sysmanager@personal-fc.local"
        assert me_data["role"] == "sysmanager"

        # 3. Refresh token
        refresh_res = await client.post("/api/v1/auth/refresh", headers=auth_headers)
        assert refresh_res.status_code == 200
        new_token_data = refresh_res.json()
        assert "access_token" in new_token_data

        # 4. Unauthenticated access fails
        fail_res = await client.get("/api/v1/auth/me")
        assert fail_res.status_code == 401


@pytest.mark.asyncio
async def test_auth_invalid_credentials():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Wrong password
        res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "sysmanager@personal-fc.local",
                "password": "WrongPassword!",
            },
        )
        assert res.status_code == 401

        # Nonexistent user
        res_nonexistent = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@personal-fc.local",
                "password": "AnyPassword123!",
            },
        )
        assert res_nonexistent.status_code == 404
        assert res_nonexistent.json()["error"]["code"] == "USER_NOT_FOUND"


@pytest.mark.asyncio
async def test_auth_register_and_change_password():
    import uuid
    from src.modules.communications.infrastructure.sms.factory import get_sms_provider

    unique_email = f"new.member.{uuid.uuid4().hex[:8]}@personal-fc.local"
    unique_phone = f"0912{uuid.uuid4().int % 10000000:07d}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request registration OTP
        otp_req = await client.post(
            "/api/v1/auth/register/otp/request",
            json={
                "email": unique_email,
                "phone_number": unique_phone,
                "password": "SecurePassword123!",
                "full_name": "New Team Member",
            },
        )
        assert otp_req.status_code == 200
        otp_code = get_sms_provider().sent_messages[-1]["code"]

        # Register new user with mandatory OTP code
        reg_payload = {
            "email": unique_email,
            "phone_number": unique_phone,
            "password": "SecurePassword123!",
            "full_name": "New Team Member",
            "code": otp_code,
        }
        res = await client.post("/api/v1/auth/register", json=reg_payload)
        assert res.status_code == 201
        data = res.json()
        assert data["user"]["email"] == unique_email
        assert data["user"]["role"] == "user"  # Because seed users already exist
        assert data["user"]["is_verified"] is True
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Duplicate register fails
        dup_res = await client.post("/api/v1/auth/register", json=reg_payload)
        assert dup_res.status_code == 409

        # Change password
        cp_payload = {
            "old_password": "SecurePassword123!",
            "new_password": "NewSecurePassword456!",
        }
        cp_res = await client.post("/api/v1/auth/change-password", headers=headers, json=cp_payload)
        assert cp_res.status_code == 200

        # Login with new password
        login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": unique_email,
                "password": "NewSecurePassword456!",
            },
        )
        assert login_res.status_code == 200

        # Update profile (age, job, bio, full_name)
        update_profile_res = await client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={
                "full_name": "نام ویرایش شده",
                "age": 32,
                "job": "تحلیل‌گر بازارهای مالی",
                "bio": "علاقه‌مند به اقتصاد کلان و سرمایه‌گذاری",
            },
        )
        assert update_profile_res.status_code == 200
        profile_data = update_profile_res.json()
        assert profile_data["full_name"] == "نام ویرایش شده"
        assert profile_data["age"] == 32
        assert profile_data["job"] == "تحلیل‌گر بازارهای مالی"
        assert profile_data["bio"] == "علاقه‌مند به اقتصاد کلان و سرمایه‌گذاری"


@pytest.mark.asyncio
async def test_onboarding_and_zero_baseline():
    import uuid
    from src.modules.communications.infrastructure.sms.factory import get_sms_provider

    unique_email = f"zero.test.{uuid.uuid4().hex[:8]}@personal-fc.local"
    unique_phone = f"0912{uuid.uuid4().int % 10000000:07d}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request registration OTP
        reg_otp_res = await client.post(
            "/api/v1/auth/register/otp/request",
            json={
                "email": unique_email,
                "password": "SecurePassword123!",
                "full_name": "Zero Baseline User",
                "phone_number": unique_phone,
            },
        )
        assert reg_otp_res.status_code == 200
        reg_code = get_sms_provider().sent_messages[-1]["code"]

        # 1. Register new regular user with verified code
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePassword123!",
                "full_name": "Zero Baseline User",
                "phone_number": unique_phone,
                "code": reg_code,
            },
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Check overview with new user token: must be zero baseline
        ov_res = await client.get("/api/v1/analytics/overview", headers=headers)
        assert ov_res.status_code == 200
        ov_data = ov_res.json()
        assert ov_data["net_worth"] == "0.0000"
        assert ov_data["total_assets"] == "0.0000"
        assert ov_data["liquid_cash"] == "0.0000"
        assert ov_data["invested_capital"] == "0.0000"
        assert len(ov_data["asset_allocation"]) == 0

        # Check snapshots: must be empty for new user
        snap_res = await client.get("/api/v1/analytics/snapshots?limit=10", headers=headers)
        assert snap_res.status_code == 200
        snaps = snap_res.json()
        assert len(snaps) == 0

        # 3. Test job benchmark query
        bm_res = await client.get(
            "/api/v1/auth/benchmark",
            params={"job": "برنامه‌نویس و مهندس نرم‌افزار", "salary": 45000000},
        )
        assert bm_res.status_code == 200
        bm_data = bm_res.json()
        assert "average_salary_toman" in bm_data
        assert bm_data["comparison_ratio_percent"] > 0

        # 4. Submit financial onboarding
        fin_payload = {
            "job": "مهندس نرم‌افزار",
            "monthly_income": 45000000,
            "liquid_assets": 120000000,
            "investment_assets": 350000000,
            "total_liabilities": 50000000,
            "financial_goals": ["خرید خانه", "استقلال مالی زودهنگام"],
        }
        fin_res = await client.post(
            "/api/v1/auth/onboarding/financial", headers=headers, json=fin_payload
        )
        assert fin_res.status_code == 200
        fin_data = fin_res.json()
        assert fin_data["user"]["has_completed_financial_onboarding"] is True
        assert len(fin_data["benchmark"]["suggestion_fa"]) > 0

        # 5. Submit risk onboarding
        risk_payload = {
            "answers": {
                "q1_drawdown_reaction": 20,
                "q2_horizon": 20,
                "q3_return_vs_safety": 20,
                "q4_experience": 15,
                "q5_income_stability": 20,
            }
        }
        risk_res = await client.post(
            "/api/v1/auth/onboarding/risk", headers=headers, json=risk_payload
        )
        assert risk_res.status_code == 200
        risk_data = risk_res.json()
        assert risk_data["user"]["has_completed_risk_onboarding"] is True
        assert risk_data["risk_result"]["total_score"] == 95
        assert risk_data["risk_result"]["risk_level"] == "aggressive"
        assert "جسور" in risk_data["risk_result"]["risk_title_fa"]
        assert risk_data["risk_result"]["portfolio_suggestion"]["equities"] == 50.0
        assert risk_data["risk_result"]["portfolio_suggestion"]["gold"] == 15.0
        assert risk_data["risk_result"]["portfolio_suggestion"]["crypto"] == 15.0

        # Also test moderate risk calculation
        mod_payload = {
            "answers": {
                "q1_drawdown_reaction": 15,
                "q2_horizon": 15,
                "q3_return_vs_safety": 15,
                "q4_experience": 10,
                "q5_income_stability": 15,
            }
        }
        mod_res = await client.post(
            "/api/v1/auth/onboarding/risk", headers=headers, json=mod_payload
        )
        assert mod_res.status_code == 200
        mod_data = mod_res.json()
        assert mod_data["risk_result"]["total_score"] == 70
        assert mod_data["risk_result"]["risk_level"] == "moderate"
        assert mod_data["risk_result"]["portfolio_suggestion"]["equities"] == 35.0
        assert mod_data["risk_result"]["portfolio_suggestion"]["gold"] == 20.0
        assert mod_data["risk_result"]["portfolio_suggestion"]["fixed_income"] == 25.0
        assert mod_data["risk_result"]["portfolio_suggestion"]["crypto"] == 5.0
        assert mod_data["risk_result"]["portfolio_suggestion"]["cash"] == 15.0

        # 6. Verify overview is now personalized and reflects assets
        new_ov = await client.get("/api/v1/analytics/overview", headers=headers)
        assert new_ov.status_code == 200
        new_ov_data = new_ov.json()
        assert float(new_ov_data["liquid_cash"]) == 120000000.0
        assert float(new_ov_data["invested_capital"]) == 350000000.0
        assert float(new_ov_data["total_assets"]) == 470000000.0
        assert float(new_ov_data["total_liabilities"]) == 50000000.0
        assert float(new_ov_data["net_worth"]) == 420000000.0
        assert len(new_ov_data["asset_allocation"]) == 2


@pytest.mark.asyncio
async def test_auth_phone_and_name_validation():
    import uuid

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Invalid phone number (doesn't start with 09)
        res1 = await client.post(
            "/api/v1/auth/register",
            json={
                "phone_number": "08123456789",
                "password": "Password123!",
                "full_name": "تست کاربر",
            },
        )
        assert res1.status_code == 422

        # 2. Invalid phone number (length != 11)
        res2 = await client.post(
            "/api/v1/auth/register",
            json={
                "phone_number": "091234567",
                "password": "Password123!",
                "full_name": "تست کاربر",
            },
        )
        assert res2.status_code == 422

        # 3. Invalid name (> 50 chars)
        res3 = await client.post(
            "/api/v1/auth/register",
            json={
                "phone_number": "09129998877",
                "password": "Password123!",
                "full_name": "A" * 51,
            },
        )
        assert res3.status_code == 422

        # 4. Invalid name (< 2 chars)
        res4 = await client.post(
            "/api/v1/auth/register",
            json={
                "phone_number": "09129998877",
                "password": "Password123!",
                "full_name": "A",
            },
        )
        assert res4.status_code == 422

        # 5. Valid phone and name registers successfully with valid OTP code
        from src.modules.communications.infrastructure.sms.factory import get_sms_provider
        unique_phone = f"0912{uuid.uuid4().int % 10000000:07d}"
        otp_req = await client.post(
            "/api/v1/auth/register/otp/request",
            json={
                "phone_number": unique_phone,
                "password": "Password123!",
                "full_name": "کاربر تستی معتبر",
            },
        )
        assert otp_req.status_code == 200
        sms_code = get_sms_provider().sent_messages[-1]["code"]

        res5 = await client.post(
            "/api/v1/auth/register",
            json={
                "phone_number": unique_phone,
                "password": "Password123!",
                "full_name": "کاربر تستی معتبر",
                "code": sms_code,
            },
        )
        assert res5.status_code == 201
        data = res5.json()
        assert data["user"]["phone_number"] == unique_phone
        assert data["user"]["full_name"] == "کاربر تستی معتبر"


@pytest.mark.asyncio
async def test_auth_register_otp_flow():
    import uuid
    from src.modules.communications.infrastructure.sms.factory import get_sms_provider

    unique_phone = f"0935{uuid.uuid4().int % 10000000:07d}"
    reg_data = {
        "full_name": "سارا محمدی",
        "phone_number": unique_phone,
        "password": "StrongPassword123!",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Request OTP for registration
        otp_res = await client.post("/api/v1/auth/register/otp/request", json=reg_data)
        assert otp_res.status_code == 200
        otp_json = otp_res.json()
        assert otp_json["identifier"] == unique_phone
        assert otp_json["channel"] in ("bale", "sms")
        assert otp_json.get("debug_code") is None
        valid_code = get_sms_provider().sent_messages[-1]["code"]

        # 2. Try verifying with wrong code
        fail_res = await client.post(
            "/api/v1/auth/register/otp/verify",
            json={**reg_data, "code": "000000"},
        )
        assert fail_res.status_code == 401

        # 3. Verify with correct code -> account created and JWT returned
        success_res = await client.post(
            "/api/v1/auth/register/otp/verify",
            json={**reg_data, "code": valid_code},
        )
        assert success_res.status_code == 201
        res_json = success_res.json()
        assert "access_token" in res_json
        assert res_json["user"]["phone_number"] == unique_phone
        assert res_json["user"]["full_name"] == "سارا محمدی"
        assert res_json["user"]["is_verified"] is True

        # 4. Requesting OTP again for now-existing user returns 409 Conflict
        dup_otp_res = await client.post("/api/v1/auth/register/otp/request", json=reg_data)
        assert dup_otp_res.status_code == 409


@pytest.mark.asyncio
async def test_account_lockout_after_five_failed_attempts():
    import uuid
    from src.modules.communications.infrastructure.sms.factory import get_sms_provider

    unique_phone = f"0918{uuid.uuid4().int % 10000000:07d}"
    password = "CorrectPassword123!"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register user with OTP
        await client.post(
            "/api/v1/auth/register/otp/request",
            json={
                "phone_number": unique_phone,
                "password": password,
                "full_name": "تست قفل حساب",
            },
        )
        code = get_sms_provider().sent_messages[-1]["code"]
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "phone_number": unique_phone,
                "password": password,
                "full_name": "تست قفل حساب",
                "code": code,
            },
        )
        assert reg_res.status_code == 201

        # 4 failed login attempts with wrong password -> 401
        for i in range(4):
            fail_login = await client.post(
                "/api/v1/auth/login",
                json={"identifier": unique_phone, "password": f"WrongPass{i}!"},
            )
            assert fail_login.status_code == 401

        # 5th failed attempt triggers lockout -> 403 Forbidden
        fifth_attempt = await client.post(
            "/api/v1/auth/login",
            json={"identifier": unique_phone, "password": "WrongPassword5!"},
        )
        assert fifth_attempt.status_code == 403
        assert "قفل" in fifth_attempt.json()["message"]

        # Subsequent attempt even with correct password is still locked out
        locked_correct = await client.post(
            "/api/v1/auth/login",
            json={"identifier": unique_phone, "password": password},
        )
        assert locked_correct.status_code == 403


@pytest.mark.asyncio
async def test_register_with_static_password_directly():
    """Verify that user can register directly with static password without requiring OTP."""
    import uuid
    unique_phone = f"0919{uuid.uuid4().int % 10000000:07d}"
    password = "DirectPassword123!"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register directly with static password (no code provided)
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "کاربر ثبت‌نام مستقیم",
                "phone_number": unique_phone,
                "password": password,
            },
        )
        assert reg_res.status_code == 201
        data = reg_res.json()
        assert data["user"]["phone_number"] == unique_phone
        assert "access_token" in data

        # Login immediately with static password
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"identifier": unique_phone, "password": password},
        )
        assert login_res.status_code == 200
        assert login_res.json()["user"]["phone_number"] == unique_phone






