import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_market_rates_and_sync():
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
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Trigger market sync
        sync_res = await client.post("/api/v1/assets/market/sync", headers=headers)
        assert sync_res.status_code == 200
        sync_data = sync_res.json()
        assert sync_data["success"] is True
        assert sync_data["total_quotes_fetched"] > 0

        # 3. Get market rates board
        rates_res = await client.get("/api/v1/assets/market/rates", headers=headers)
        assert rates_res.status_code == 200
        rates_data = rates_res.json()

        assert len(rates_data["gold_and_coins"]) > 0
        assert len(rates_data["commodities"]) > 0
        assert len(rates_data["currencies"]) > 0
        assert len(rates_data["cryptocurrency"]) > 0

        # Verify differentiation between Global XAU Ounce (USD) and Iran Gold 18K (TOMAN)
        gold_symbols = {g["symbol"]: g for g in rates_data["gold_and_coins"]}
        assert "IR_GOLD_18K" in gold_symbols
        assert gold_symbols["IR_GOLD_18K"]["unit"] == "تومان"
        assert float(gold_symbols["IR_GOLD_18K"]["price"]) > 1000000

        # Check Global XAU Ounce
        assert "XAUUSD" in gold_symbols
        assert gold_symbols["XAUUSD"]["unit"] == "دلار"
        assert float(gold_symbols["XAUUSD"]["price"]) > 1000

        # Check base commodities (Copper Cu, Silver XAGUSD)
        comm_symbols = {c["symbol"]: c for c in rates_data["commodities"]}
        assert "CU" in comm_symbols
        assert comm_symbols["CU"]["unit"] == "دلار"
        assert float(comm_symbols["CU"]["price"]) > 0

        assert "XAGUSD" in comm_symbols
        assert comm_symbols["XAGUSD"]["unit"] == "دلار"

        # Check currency (USD in Toman)
        curr_symbols = {c["symbol"]: c for c in rates_data["currencies"]}
        assert "USD" in curr_symbols
        assert curr_symbols["USD"]["unit"] == "تومان"
        assert float(curr_symbols["USD"]["price"]) > 50000

        # 4. Check that AssetModel prices were synchronized
        assets_res = await client.get("/api/v1/assets", headers=headers)
        assert assets_res.status_code == 200
        assets_list = assets_res.json()
        asset_map = {a["symbol"].upper(): a for a in assets_list}

        # Check copper Cu
        assert "CU" in asset_map
        assert float(asset_map["CU"]["current_price"]) > 0

        # Check Iran 18K Gold
        assert "IR_GOLD_18K" in asset_map
        assert float(asset_map["IR_GOLD_18K"]["current_price"]) > 1000000
        assert asset_map["IR_GOLD_18K"]["currency"] == "TOMAN"

        # Check XAU / XAUUSD
        xau_asset = asset_map.get("XAUUSD") or asset_map.get("XAU")
        assert xau_asset is not None
        assert float(xau_asset["current_price"]) > 1000

        # 5. Immediate re-sync hits cooldown message
        second_sync = await client.post("/api/v1/assets/market/sync", headers=headers)
        assert second_sync.status_code == 200
        assert "شکیبا" in second_sync.json()["message"] or "تلاش" in second_sync.json()["message"]


@pytest.mark.asyncio
async def test_unauthenticated_public_market_rates():
    """Verify that guests/unauthenticated visitors can retrieve public market rates without credentials."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/assets/market/rates")
        assert res.status_code == 200
        data = res.json()
        assert "gold_and_coins" in data
        assert "commodities" in data
        assert "currencies" in data
        assert "cryptocurrency" in data
