import uuid
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


async def get_auth_headers(client: AsyncClient) -> dict[str, str]:
    from src.modules.communications.infrastructure.sms.factory import get_sms_provider

    email = f"endpoint_user_{uuid.uuid4().hex[:8]}@personal-fc.local"
    phone = f"0912{uuid.uuid4().int % 10000000:07d}"
    await client.post(
        "/api/v1/auth/register/otp/request",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Endpoint Tester",
            "phone_number": phone,
        },
    )
    code = get_sms_provider().sent_messages[-1]["code"]
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Endpoint Tester",
            "phone_number": phone,
            "code": code,
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/auth/onboarding/financial",
        headers=headers,
        json={
            "job": "Software Engineer",
            "monthly_income": "50000000.00",
            "liquid_assets": "100000000.00",
            "investment_assets": "300000000.00",
            "total_liabilities": "20000000.00",
            "financial_goals": ["خانه"],
        },
    )
    return headers


@pytest.mark.asyncio
async def test_overview_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_headers(client)
        response = await client.get("/api/v1/analytics/overview", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "net_worth" in data
        assert "total_assets" in data
        assert "liquid_cash" in data
        assert "asset_allocation" in data
        assert len(data["asset_allocation"]) > 0
        assert "attention_items" in data

        # Create an asset and a transaction to test recent_transactions and eager account loading
        sym = f"OV_{uuid.uuid4().hex[:6].upper()}"
        asset_res = await client.post(
            "/api/v1/assets",
            json={
                "symbol": sym,
                "name": "Overview Test Asset",
                "asset_class": "equity",
                "currency": "TOMAN",
                "initial_price": "50000.00",
                "is_active": True,
            },
        )
        assert asset_res.status_code == 201
        asset_id = asset_res.json()["id"]

        tx_res = await client.post(
            "/api/v1/transactions",
            headers=headers,
            json={
                "platform": "مفید",
                "asset_id": asset_id,
                "transaction_type": "BUY",
                "transaction_date": "2026-09-20T10:00:00Z",
                "quantity": "5.0000",
                "unit_price": "50000.00",
                "total_amount": "250000.00",
                "currency": "TOMAN",
            },
        )
        assert tx_res.status_code == 201

        # Test overview with transactions (verifies selectinload of t.account prevents MissingGreenlet)
        response2 = await client.get("/api/v1/analytics/overview", headers=headers)
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["recent_transactions"]) > 0
        assert data2["recent_transactions"][0]["account_name"] is not None


@pytest.mark.asyncio
async def test_accounts_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_headers(client)
        # Create
        create_payload = {
            "name": "Test Vault",
            "account_type": "savings",
            "institution": "Mellat",
            "currency": "TOMAN",
            "initial_balance": "5000000.00",
            "account_number_mask": "*9999",
        }
        res_create = await client.post("/api/v1/accounts", headers=headers, json=create_payload)
        assert res_create.status_code == 201
        acc_data = res_create.json()
        assert acc_data["name"] == "Test Vault"
        acc_id = acc_data["id"]

        # List
        response = await client.get("/api/v1/accounts", headers=headers)
        assert response.status_code == 200
        accounts = response.json()
        assert len(accounts) >= 1

        # Delete
        res_del = await client.delete(f"/api/v1/accounts/{acc_id}", headers=headers)
        assert res_del.status_code == 204


@pytest.mark.asyncio
async def test_assets_and_positions():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_headers(client)
        res_assets = await client.get("/api/v1/assets")
        assert res_assets.status_code == 200
        assets = res_assets.json()
        assert isinstance(assets, list)

        res_positions = await client.get("/api/v1/assets/positions", headers=headers)
        assert res_positions.status_code == 200
        positions = res_positions.json()
        assert isinstance(positions, list)

        # Create an asset and a BUY transaction to guarantee a position
        unique_sym = f"POS_{uuid.uuid4().hex[:6].upper()}"
        asset_res = await client.post(
            "/api/v1/assets",
            json={
                "symbol": unique_sym,
                "name": "Position Test Asset",
                "asset_class": "equity",
                "currency": "TOMAN",
                "initial_price": "100000.00",
                "is_active": True,
            },
        )
        assert asset_res.status_code == 201
        test_asset_id = asset_res.json()["id"]

        buy_res = await client.post(
            "/api/v1/transactions",
            headers=headers,
            json={
                "platform": "مفید",
                "asset_id": test_asset_id,
                "transaction_type": "BUY",
                "transaction_date": "2026-09-15T12:00:00Z",
                "quantity": "10.0000",
                "unit_price": "100000.00",
                "total_amount": "1000000.00",
                "currency": "TOMAN",
            },
        )
        assert buy_res.status_code == 201

        # Check positions list
        res_positions2 = await client.get("/api/v1/assets/positions", headers=headers)
        assert res_positions2.status_code == 200
        pos_list = res_positions2.json()
        target_pos = next((p for p in pos_list if p["asset_id"] == test_asset_id), None)
        assert target_pos is not None
        pos_id = target_pos["id"]

        # Edit/Update Position
        patch_res = await client.patch(
            f"/api/v1/assets/positions/{pos_id}",
            headers=headers,
            json={
                "quantity": "15.5000",
                "average_cost_basis": "105000.00",
            },
        )
        assert patch_res.status_code == 200
        updated_pos = patch_res.json()
        assert float(updated_pos["quantity"]) == 15.5
        assert float(updated_pos["average_cost_basis"]) == 105000.0

        # Delete Position
        del_res = await client.delete(f"/api/v1/assets/positions/{pos_id}", headers=headers)
        assert del_res.status_code == 204

        # Verify deletion
        res_positions3 = await client.get("/api/v1/assets/positions", headers=headers)
        assert not any(p["id"] == pos_id for p in res_positions3.json())


@pytest.mark.asyncio
async def test_asset_lifecycle_create_update_delete():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create asset
        unique_sym = f"TST_{uuid.uuid4().hex[:6].upper()}"
        create_res = await client.post(
            "/api/v1/assets",
            json={
                "symbol": unique_sym,
                "name": "Test Lifecycle Asset",
                "asset_class": "equity",
                "currency": "TOMAN",
                "initial_price": "150000.00",
                "is_active": True,
            },
        )
        assert create_res.status_code == 201
        asset_data = create_res.json()
        asset_id = asset_data["id"]

        # Update asset
        patch_res = await client.patch(
            f"/api/v1/assets/{asset_id}",
            json={"is_active": False, "notes": "Deactivated test"},
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["is_active"] is False

        # Delete asset
        del_res = await client.delete(f"/api/v1/assets/{asset_id}")
        assert del_res.status_code == 204

        # Confirm deleted
        get_res = await client.get(f"/api/v1/assets/{asset_id}")
        assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_liabilities_and_schedule():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_headers(client)

        # Test liability types endpoint
        res_types = await client.get("/api/v1/liabilities/types")
        assert res_types.status_code == 200
        types_data = res_types.json()
        assert len(types_data) >= 8
        type_codes = [t["code"] for t in types_data]
        assert "bank_loan" in type_codes
        assert "mortgage" in type_codes
        assert "bnpl" in type_codes
        assert "friend_borrowed" in type_codes

        # Test liability labels endpoint
        res_labels = await client.get("/api/v1/liabilities/labels")
        assert res_labels.status_code == 200
        labels_data = res_labels.json()
        assert labels_data.get("bank_loan") == "وام بانکی"
        assert labels_data.get("friend_borrowed") == "قرض گرفته‌شده از دوست (بدهی)"

        # Create liability
        liab_payload = {
            "name": "وام مسکن",
            "liability_type": "mortgage",
            "lender": "بانک مسکن",
            "original_principal": "50000000.00",
            "current_balance": "40000000.00",
            "interest_rate_percent": "18.0",
            "monthly_payment": "1500000.00",
            "start_date": "2026-01-01",
            "currency": "TOMAN",
        }
        res_create = await client.post("/api/v1/liabilities", headers=headers, json=liab_payload)
        assert res_create.status_code == 201
        created_liab = res_create.json()
        assert created_liab["type_config"] is not None
        assert created_liab["type_config"]["code"] == "mortgage"

        res = await client.get("/api/v1/liabilities", headers=headers)
        assert res.status_code == 200
        liabilities = res.json()
        assert len(liabilities) >= 1
        assert liabilities[0]["type_config"] is not None

        # Update liability (fill in missing data or update)
        update_payload = {
            "lender": "بانک مسکن مرکزی",
            "monthly_payment": "1600000.00",
        }
        res_update = await client.patch(
            f"/api/v1/liabilities/{created_liab['id']}", headers=headers, json=update_payload
        )
        assert res_update.status_code == 200
        updated_data = res_update.json()
        assert updated_data["lender"] == "بانک مسکن مرکزی"
        assert Decimal(updated_data["monthly_payment"]) == Decimal("1600000.00")

        # List payments
        res_payments = await client.get(
            f"/api/v1/liabilities/{created_liab['id']}/payments", headers=headers
        )
        assert res_payments.status_code == 200
        assert isinstance(res_payments.json(), list)

        # Schedule calculation
        res_sched = await client.get(
            "/api/v1/liabilities/calculate-schedule?principal=10000000&interest_rate=18.0&term_months=12"
        )
        assert res_sched.status_code == 200
        schedule = res_sched.json()
        assert len(schedule) == 12
        assert Decimal(str(schedule[-1]["remaining_balance"])) == Decimal("0.00")


@pytest.mark.asyncio
async def test_liability_types_crud():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_headers(client)

        import uuid
        custom_code = f"custom_type_{uuid.uuid4().hex[:6]}"
        payload = {
            "code": custom_code,
            "label": "وام قرض‌الحسنه اختصاصی",
            "short_label": "وام اختصاصی",
            "description": "تسهیلات ویژه سازمانی",
            "icon": "Users",
            "default_rate": "2.0",
            "default_term_months": 18,
            "is_friend": False,
            "direction": "debt",
            "display_order": 99,
            "is_active": True,
        }
        res = await client.post("/api/v1/liabilities/types", headers=headers, json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["code"] == custom_code
        assert data["label"] == "وام قرض‌الحسنه اختصاصی"

        # Duplicate should fail with 409
        res_dup = await client.post("/api/v1/liabilities/types", headers=headers, json=payload)
        assert res_dup.status_code == 409




@pytest.mark.asyncio
async def test_cashflow_summary():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_headers(client)
        res = await client.get("/api/v1/cashflow/summary", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "total_income" in data
        assert "total_expenses" in data
        assert "savings_rate_percent" in data


@pytest.mark.asyncio
async def test_scenarios_simulation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_headers(client)
        sim_payload = {
            "name": "Promotion + Loan Payoff",
            "horizon_months": 24,
            "monthly_income_delta": "15000000.00",
            "monthly_expense_delta": "-3000000.00",
            "asset_growth_rate_annual": "25.0",
            "new_loan_amount": "0",
            "one_time_windfall": "100000000.00",
        }
        res = await client.post("/api/v1/scenarios/simulate", headers=headers, json=sim_payload)
        assert res.status_code == 200
        data = res.json()
        assert len(data["monthly_projections"]) == 24
        assert Decimal(str(data["net_worth_delta"])) > 0


@pytest.mark.asyncio
async def test_ai_chat():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_headers(client)
        chat_payload = {
            "content": "Explain my current net worth and portfolio allocation.",
        }
        res = await client.post("/api/v1/ai/chat", headers=headers, json=chat_payload)
        assert res.status_code == 201
        data = res.json()
        assert data["role"] == "assistant"
        assert "Net Worth" in data["content"] or "Financial" in data["content"]


@pytest.mark.asyncio
async def test_wealth_trajectory_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_headers(client)
        res = await client.get("/api/v1/analytics/wealth-trajectory?history_days=90&forecast_months=12", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "timeline" in data
        assert len(data["timeline"]) > 0
        assert "baseline_investments" in data
        assert "baseline_liabilities" in data
        assert "ai_narrative" in data
        assert "loans" in data
        assert "investments" in data
        assert "incomes" in data

        # Verify historical vs forecast points
        hist_points = [p for p in data["timeline"] if not p["is_forecast"]]
        fore_points = [p for p in data["timeline"] if p["is_forecast"]]
        assert len(hist_points) >= 1
        assert len(fore_points) == 12

        # Verify liabilities decline or reach 0 over forecast
        if len(fore_points) > 1 and Decimal(str(fore_points[0]["total_liabilities"])) > 0:
            first_liab = Decimal(str(fore_points[0]["total_liabilities"]))
            last_liab = Decimal(str(fore_points[-1]["total_liabilities"]))
            assert last_liab <= first_liab

        # Verify investments ascend over forecast
        if len(fore_points) > 1 and Decimal(str(fore_points[0]["total_investments"])) > 0:
            first_inv = Decimal(str(fore_points[0]["total_investments"]))
            last_inv = Decimal(str(fore_points[-1]["total_investments"]))
            assert last_inv >= first_inv


@pytest.mark.asyncio
async def test_transaction_inactive_asset_validation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_headers(client)

        # Create an inactive asset
        sym = f"INACT_{uuid.uuid4().hex[:6].upper()}"
        asset_res = await client.post(
            "/api/v1/assets",
            json={
                "symbol": sym,
                "name": "Inactive Asset Test",
                "asset_class": "equity",
                "currency": "TOMAN",
                "initial_price": "10000.00",
                "is_active": False,
            },
        )
        assert asset_res.status_code == 201
        inactive_asset_id = asset_res.json()["id"]

        # Attempt creating a transaction using the inactive asset -> should be rejected with HTTP 400
        tx_res = await client.post(
            "/api/v1/transactions",
            headers=headers,
            json={
                "platform": "تست",
                "asset_id": inactive_asset_id,
                "transaction_type": "BUY",
                "transaction_date": "2026-09-25T10:00:00Z",
                "quantity": "1.0000",
                "unit_price": "10000.00",
                "total_amount": "10000.00",
                "currency": "TOMAN",
            },
        )
        assert tx_res.status_code == 400
        assert "غیرفعال" in tx_res.json()["error"]["message"]

