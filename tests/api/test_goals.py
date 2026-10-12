import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app

@pytest.mark.asyncio
async def test_goals_crud_and_onboarding_compatibility():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Register a user
        from src.modules.communications.infrastructure.sms.factory import get_sms_provider

        email = f"goal_user_{uuid.uuid4().hex[:8]}@personal-fc.local"
        phone = f"0912{uuid.uuid4().int % 10000000:07d}"
        await client.post(
            "/api/v1/auth/register/otp/request",
            json={
                "email": email,
                "password": "SecurePassword123!",
                "full_name": "Goal User",
                "phone_number": phone,
            },
        )
        code = get_sms_provider().sent_messages[-1]["code"]
        reg = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "SecurePassword123!",
                "full_name": "Goal User",
                "phone_number": phone,
                "code": code,
            },
        )
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Complete financial onboarding with string goals (e.g. ['خرید خانه', 'خودرو'])
        onboard = await client.post(
            "/api/v1/auth/onboarding/financial",
            headers=headers,
            json={
                "job": "Software Engineer",
                "monthly_income": "60000000.00",
                "liquid_assets": "100000000.00",
                "investment_assets": "300000000.00",
                "total_liabilities": "20000000.00",
                "financial_goals": ["خرید خانه", "خودرو شخصی"],
            },
        )
        assert onboard.status_code == 200

        # 3. GET /goals must succeed (no 500 error on onboarding string goals!)
        res_list = await client.get("/api/v1/goals", headers=headers)
        assert res_list.status_code == 200
        goals_data = res_list.json()
        assert len(goals_data) == 2
        assert goals_data[0]["name"] == "خرید خانه"

        # 4. POST /goals to create a new structured goal
        create_payload = {
            "name": "صندوق اضطراری ۶ ماهه",
            "category": "emergency_fund",
            "target_amount": "120000000",
            "current_amount": "20000000",
            "monthly_contribution": "10000000",
            "target_date": "2027-12-31",
            "currency": "TOMAN",
            "status": "in_progress",
            "notes": "برای موارد غیرمترقبه",
        }
        res_create = await client.post("/api/v1/goals", headers=headers, json=create_payload)
        assert res_create.status_code == 201
        new_goal = res_create.json()
        assert new_goal["name"] == "صندوق اضطراری ۶ ماهه"
        assert float(new_goal["target_amount"]) == 120000000.0
        assert float(new_goal["remaining_amount"]) == 100000000.0
        goal_id = new_goal["id"]

        # 5. GET /goals again, now 3 goals
        res_list2 = await client.get("/api/v1/goals", headers=headers)
        assert res_list2.status_code == 200
        assert len(res_list2.json()) == 3

        # 6. PATCH /goals/{id}
        res_patch = await client.patch(
            f"/api/v1/goals/{goal_id}",
            headers=headers,
            json={"current_amount": "30000000"},
        )
        assert res_patch.status_code == 200
        patched = res_patch.json()
        assert float(patched["current_amount"]) == 30000000.0

        # 7. DELETE /goals/{id}
        res_del = await client.delete(f"/api/v1/goals/{goal_id}", headers=headers)
        assert res_del.status_code == 204

        # 8. GET /goals after delete, back to 2 goals
        res_list3 = await client.get("/api/v1/goals", headers=headers)
        assert res_list3.status_code == 200
        assert len(res_list3.json()) == 2


@pytest.mark.asyncio
async def test_goal_categories_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. GET /goals/categories
        res = await client.get("/api/v1/goals/categories")
        assert res.status_code == 200
        categories = res.json()
        assert isinstance(categories, list)

        # 2. POST /goals/categories
        code = f"custom_cat_{uuid.uuid4().hex[:6]}"
        create_res = await client.post(
            "/api/v1/goals/categories",
            json={
                "code": code,
                "label": "دسته تستی",
                "description": "توضیحات تست",
                "icon": "Target",
                "display_order": 99,
                "is_active": True,
            },
        )
        assert create_res.status_code == 201
        created = create_res.json()
        assert created["code"] == code
        assert created["label"] == "دسته تستی"
