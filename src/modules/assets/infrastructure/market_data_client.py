from decimal import Decimal
from typing import Any

import httpx

from src.app.core.settings import get_settings
from src.app.observability.logging import get_logger

logger = get_logger("assets.market_data_client")
settings = get_settings()


class MarketDataClient:
    """HTTP Client for BRS Market Data APIs.

    Fetches Commodities, Cryptocurrencies, Gold & Forex rates.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.BRS_API_KEY
        self.timeout = 15.0

    async def fetch_commodities(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch precious metals (Gold, Silver, Platinum), base metals (Copper, Aluminum), and energy."""
        if settings.MARKET_DATA_PROVIDER == "mock" or not self.api_key:
            return {
                "metal_precious": [
                    {"symbol": "XAUUSD", "name": "انس طلا جهانی", "price": "2650.50", "unit": "دلار", "change_percent": 0.45},
                    {"symbol": "XAGUSD", "name": "نقره جهانی", "price": "31.50", "unit": "دلار", "change_percent": -0.20},
                ],
                "metal_base": [
                    {"symbol": "CU", "name": "مس جهانی", "price": "9800.00", "unit": "دلار", "change_percent": 1.10},
                ],
                "energy": [
                    {"symbol": "BRENT", "name": "نفت برنت", "price": "75.20", "unit": "دلار", "change_percent": 0.30},
                ],
            }

        url = f"{settings.BRS_COMMODITY_URL}?key={self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    return data
                logger.warning("Unexpected response format from Commodity API: %s", data)
                return {}
        except Exception as e:
            logger.error("Failed to fetch commodities from BRS API: %s", str(e))
            return {}

    async def fetch_cryptocurrency(self) -> list[dict[str, Any]]:
        """Fetch live cryptocurrency prices (USD and Toman)."""
        if settings.MARKET_DATA_PROVIDER == "mock" or not self.api_key:
            return [
                {"name_en": "bitcoin", "name": "بیت‌کوین", "price": "68000.00", "price_toman": "4080000000", "change_percent": 1.8},
                {"name_en": "ethereum", "name": "اتریوم", "price": "3500.00", "price_toman": "210000000", "change_percent": 2.1},
                {"name_en": "tether", "name": "تتر", "price": "1.00", "price_toman": "60000", "change_percent": 0.0},
            ]

        url = f"{settings.BRS_CRYPTO_URL}?key={self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return data
                logger.warning("Unexpected response format from Crypto API: %s", data)
                return []
        except Exception as e:
            logger.error("Failed to fetch cryptocurrencies from BRS API: %s", str(e))
            return []

    async def fetch_gold_and_currency(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch Iranian domestic gold (18K, 24K, melted, coins) and foreign currencies (USD, EUR, etc.)."""
        if settings.MARKET_DATA_PROVIDER == "mock" or not self.api_key:
            return {
                "currency": [
                    {"symbol": "USD", "name": "دلار آمریکا", "name_en": "US Dollar", "price": "60000", "unit": "تومان", "change_percent": 0.1},
                    {"symbol": "EUR", "name": "یورو", "name_en": "Euro", "price": "65000", "unit": "تومان", "change_percent": 0.05},
                ],
                "gold": [
                    {"symbol": "IR_GOLD_18K", "name": "طلای ۱۸ عیار", "name_en": "Gold 18K", "price": "4200000", "unit": "تومان", "change_percent": 0.25},
                    {"symbol": "XAUUSD", "name": "انس طلای جهانی", "name_en": "Gold Ounce", "price": "2650.50", "unit": "دلار", "change_percent": 0.45},
                ],
            }

        url = f"{settings.BRS_GOLD_CURRENCY_URL}?key={self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    return data
                logger.warning("Unexpected response format from Gold & Currency API: %s", data)
                return {}
        except Exception as e:
            logger.error("Failed to fetch gold and currencies from BRS API: %s", str(e))
            return {}

