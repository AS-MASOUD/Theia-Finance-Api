import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.settings import get_settings
from src.app.database.models import AssetModel
from src.app.observability.logging import get_logger
from src.modules.assets.application.dtos import (
    MarketQuoteDTO,
    MarketRatesResponse,
    MarketSyncResultResponse,
)
from src.modules.assets.infrastructure.market_data_client import MarketDataClient

logger = get_logger("assets.market_sync_service")
settings = get_settings()

CRYPTO_TICKER_MAP = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "tether": "USDT",
    "binance coin": "BNB",
    "xrp": "XRP",
    "solana": "SOL",
    "cardano": "ADA",
    "dogecoin": "DOGE",
    "tron": "TRX",
    "toncoin": "TON",
    "avalanche": "AVAX",
    "chainlink": "LINK",
    "polkadot": "DOT",
    "shiba inu": "SHIB",
    "litecoin": "LTC",
    "bitcoin cash": "BCH",
    "uniswap": "UNI",
    "stellar": "XLM",
    "monero": "XMR",
    "dai": "DAI",
}


def _safe_decimal(val: Any, default: Decimal = Decimal("0")) -> Decimal:
    if val is None:
        return default
    try:
        clean = str(val).replace(",", "").strip()
        return Decimal(clean)
    except Exception:
        return default


class MarketSyncService:
    """Service to fetch, consolidate, and synchronize market rates across Commodities, Gold, Forex, and Crypto."""

    _cached_rates: MarketRatesResponse | None = None
    _last_sync_time: datetime | None = None
    _sync_lock = asyncio.Lock()

    def __init__(self, client: MarketDataClient | None = None):
        self.client = client or MarketDataClient()

    async def get_market_rates(self, db: AsyncSession | None = None) -> MarketRatesResponse:
        """Return the current cached market rates. If cache is empty, triggers a sync."""
        if MarketSyncService._cached_rates is not None:
            return MarketSyncService._cached_rates

        if db is not None:
            await self.sync_market_prices(db)
            if MarketSyncService._cached_rates is not None:
                return MarketSyncService._cached_rates

        # Fallback empty response
        return MarketRatesResponse(
            gold_and_coins=[],
            commodities=[],
            currencies=[],
            cryptocurrency=[],
            last_sync_time=None,
        )

    async def sync_market_prices(self, db: AsyncSession) -> MarketSyncResultResponse:
        """Fetch all 3 market APIs concurrently, update AssetModel prices, and refresh cache."""
        async with MarketSyncService._sync_lock:
            now = datetime.now(UTC)
            logger.info("Starting background market price synchronization from BRS API...")

            # 1. Concurrently fetch all market APIs
            comm_task = self.client.fetch_commodities()
            gold_curr_task = self.client.fetch_gold_and_currency()
            crypto_task = self.client.fetch_cryptocurrency()
            stocks_task = self.client.fetch_stocks()

            comm_data, gold_curr_data, crypto_data, stocks_data = await asyncio.gather(
                comm_task, gold_curr_task, crypto_task, stocks_task, return_exceptions=True
            )

            if isinstance(comm_data, Exception):
                logger.error("Commodities fetch failed: %s", comm_data)
                comm_data = {}
            if isinstance(gold_curr_data, Exception):
                logger.error("Gold & Currency fetch failed: %s", gold_curr_data)
                gold_curr_data = {}
            if isinstance(crypto_data, Exception):
                logger.error("Crypto fetch failed: %s", crypto_data)
                crypto_data = []
            if isinstance(stocks_data, Exception):
                logger.error("Stocks fetch failed: %s", stocks_data)
                stocks_data = []

            # 2. Extract USD/TOMAN base exchange rate
            usd_toman_rate: Decimal | None = None
            currencies_list = gold_curr_data.get("currency", []) if isinstance(gold_curr_data, dict) else []
            for c in currencies_list:
                sym = str(c.get("symbol", "")).upper()
                if sym == "USD":
                    usd_toman_rate = _safe_decimal(c.get("price"))
                    break
            if not usd_toman_rate or usd_toman_rate <= Decimal("0"):
                # fallback to USDT rate or standard
                for c in currencies_list:
                    if str(c.get("symbol", "")).upper() == "USDT_IRT":
                        usd_toman_rate = _safe_decimal(c.get("price"))
                        break

            # 3. Build categorized market quote DTOs
            gold_and_coins: list[MarketQuoteDTO] = []
            commodities: list[MarketQuoteDTO] = []
            currencies: list[MarketQuoteDTO] = []
            cryptos: list[MarketQuoteDTO] = []

            # Price lookup for AssetModel matching: symbol -> (price_usd, price_toman)
            price_catalog: dict[str, dict[str, Decimal]] = {}

            # Process Domestic Gold & Coins
            raw_gold = gold_curr_data.get("gold", []) if isinstance(gold_curr_data, dict) else []
            for item in raw_gold:
                sym = str(item.get("symbol", "")).strip().upper()
                name = str(item.get("name", "")).strip()
                name_en = item.get("name_en")
                price = _safe_decimal(item.get("price"))
                unit = str(item.get("unit", "تومان")).strip()
                chg = float(item.get("change_percent", 0.0) or 0.0)

                # Differentiate Global XAU Ounce vs Iran Domestic Gold
                if sym == "XAUUSD":
                    # Global Gold Ounce is in USD
                    price_usd = price
                    price_toman = (price * usd_toman_rate) if usd_toman_rate else None
                    unit = "دلار"
                else:
                    # Iran Gold (18k, 24k, melted, coins) is in TOMAN
                    price_toman = price
                    price_usd = (price / usd_toman_rate) if usd_toman_rate and usd_toman_rate > 0 else Decimal("0")

                quote = MarketQuoteDTO(
                    symbol=sym,
                    name=name,
                    name_en=name_en,
                    category="gold_coin",
                    price=price,
                    unit=unit,
                    change_percent=chg,
                    price_toman=price_toman,
                    updated_at=now,
                )
                gold_and_coins.append(quote)
                price_catalog[sym] = {"usd": price_usd, "toman": price_toman or Decimal("0")}

                # Add common aliases
                if sym == "IR_GOLD_18K":
                    price_catalog["GOLD18K"] = price_catalog[sym]
                    price_catalog["GOLD_18K"] = price_catalog[sym]
                elif sym == "XAUUSD":
                    price_catalog["XAU"] = price_catalog[sym]
                elif sym == "IR_COIN_EMAMI":
                    price_catalog["COIN_EMAMI"] = price_catalog[sym]

            # Process Commodities (Precious metals, Base metals, Energy)
            if isinstance(comm_data, dict):
                for cat_key, cat_name in [
                    ("metal_precious", "فلزات گرانبها"),
                    ("metal_base", "فلزات پایه"),
                    ("energy", "انرژی و نفت"),
                ]:
                    items = comm_data.get(cat_key, [])
                    for item in items:
                        sym = str(item.get("symbol", "")).strip().upper()
                        name = str(item.get("name", "")).strip()
                        price = _safe_decimal(item.get("price"))
                        unit = str(item.get("unit", "دلار")).strip()
                        chg = float(item.get("change_percent", 0.0) or 0.0)

                        price_usd = price
                        price_toman = (price * usd_toman_rate) if usd_toman_rate else None

                        quote = MarketQuoteDTO(
                            symbol=sym,
                            name=name,
                            name_en=sym,
                            category="commodity",
                            price=price,
                            unit=unit,
                            change_percent=chg,
                            price_toman=price_toman,
                            updated_at=now,
                        )
                        commodities.append(quote)
                        price_catalog[sym] = {"usd": price_usd, "toman": price_toman or Decimal("0")}

                        # Aliases
                        if sym == "CU":
                            price_catalog["COPPER"] = price_catalog[sym]
                        elif sym == "XAGUSD":
                            price_catalog["XAG"] = price_catalog[sym]
                            price_catalog["SILVER"] = price_catalog[sym]
                        elif sym == "XAUUSD":
                            price_catalog["XAU"] = price_catalog[sym]

            # Process Currencies
            for item in currencies_list:
                sym = str(item.get("symbol", "")).strip().upper()
                name = str(item.get("name", "")).strip()
                name_en = item.get("name_en")
                price = _safe_decimal(item.get("price"))
                unit = str(item.get("unit", "تومان")).strip()
                chg = float(item.get("change_percent", 0.0) or 0.0)

                quote = MarketQuoteDTO(
                    symbol=sym,
                    name=name,
                    name_en=name_en,
                    category="currency",
                    price=price,
                    unit=unit,
                    change_percent=chg,
                    price_toman=price,
                    updated_at=now,
                )
                currencies.append(quote)
                price_catalog[sym] = {
                    "usd": (price / usd_toman_rate) if (usd_toman_rate and usd_toman_rate > 0) else Decimal("1"),
                    "toman": price,
                }
                # Also store canonical IRR pair symbol
                price_catalog[f"{sym}_IRR"] = price_catalog[sym]
                if sym == "USD":
                    price_catalog["DOLLAR"] = price_catalog[sym]

            # Process Cryptocurrencies
            if isinstance(crypto_data, list):
                for item in crypto_data[:50]:  # Top 50 cryptos
                    name_en = str(item.get("name_en", "")).strip()
                    name = str(item.get("name", "")).strip() or name_en
                    p_usd = _safe_decimal(item.get("price"))
                    p_toman = _safe_decimal(item.get("price_toman"))
                    chg = float(item.get("change_percent", 0.0) or 0.0)

                    # Determine ticker symbol
                    sym = CRYPTO_TICKER_MAP.get(name_en.lower()) or name_en.upper().replace(" ", "")

                    # Ensure realistic Toman price for stablecoins and cryptos
                    if sym == "USDT" or name_en.lower() == "tether":
                        p_toman = (usd_toman_rate + Decimal("250")) if usd_toman_rate else Decimal("95100")
                    elif (not p_toman or p_toman < Decimal("70000")) and usd_toman_rate and p_usd > Decimal("0"):
                        p_toman = p_usd * usd_toman_rate

                    quote = MarketQuoteDTO(
                        symbol=sym,
                        name=name,
                        name_en=name_en,
                        category="crypto",
                        price=p_usd,
                        unit="دلار",
                        change_percent=chg,
                        price_toman=p_toman,
                        updated_at=now,
                    )
                    cryptos.append(quote)
                    price_catalog[sym] = {"usd": p_usd, "toman": p_toman}
                    price_catalog[f"{sym}_USD"] = {"usd": p_usd, "toman": p_toman}
                    if sym == "USDT":
                        price_catalog["USDT_IRT"] = {"usd": p_usd, "toman": p_toman}
                        price_catalog["TETHER"] = {"usd": p_usd, "toman": p_toman}

            # Process Equities and Indices
            stocks_list: list[MarketQuoteDTO] = []
            if isinstance(stocks_data, list):
                for item in stocks_data:
                    sym = str(item.get("symbol", "")).strip().upper()
                    name = str(item.get("name", "")).strip()
                    name_en = item.get("name_en")
                    price = _safe_decimal(item.get("price"))
                    unit = str(item.get("unit", "ریال")).strip()
                    chg = float(item.get("change_percent", 0.0) or 0.0)
                    p_toman = (price / Decimal("10")) if unit == "ریال" else price

                    quote = MarketQuoteDTO(
                        symbol=sym,
                        name=name,
                        name_en=name_en,
                        category="stock",
                        price=price,
                        unit=unit,
                        change_percent=chg,
                        price_toman=p_toman,
                        updated_at=now,
                    )
                    stocks_list.append(quote)
                    price_catalog[sym] = {"usd": Decimal("0"), "toman": p_toman}
                    if sym == "TEDPIX":
                        price_catalog["BOURSE"] = price_catalog[sym]

            # Update cache
            rates_resp = MarketRatesResponse(
                gold_and_coins=gold_and_coins,
                commodities=commodities,
                currencies=currencies,
                cryptocurrency=cryptos,
                stocks=stocks_list,
                usd_toman_rate=usd_toman_rate,
                last_sync_time=now,
                sync_source="BRS API",
            )
            MarketSyncService._cached_rates = rates_resp
            MarketSyncService._last_sync_time = now

            # 4. Synchronize with AssetModel in Database
            updated_count = 0
            stmt_assets = select(AssetModel)
            res_assets = await db.execute(stmt_assets)
            existing_assets = list(res_assets.scalars().all())
            existing_symbols = {a.symbol.upper(): a for a in existing_assets}

            for asset in existing_assets:
                lookup_sym = asset.symbol.upper()
                if lookup_sym in price_catalog:
                    entry = price_catalog[lookup_sym]
                    if asset.currency == "TOMAN":
                        new_price = entry["toman"]
                    else:
                        new_price = entry["usd"]

                    if new_price and new_price > Decimal("0"):
                        asset.current_price = new_price
                        asset.price_updated_at = now
                        updated_count += 1

            # 5. Ensure core standard market assets exist in AssetModel for portfolio tracking
            core_assets = [
                ("IR_GOLD_18K", "طلای ۱۸ عیار", "commodity", "TOMAN"),
                ("XAUUSD", "انس جهانی طلا", "commodity", "USD"),
                ("IR_COIN_EMAMI", "سکه بهار آزادی (امامی)", "commodity", "TOMAN"),
                ("IR_GOLD_MELTED", "طلای آب‌شده نقدی", "commodity", "TOMAN"),
                ("CU", "مس جهانی (Copper)", "commodity", "USD"),
                ("XAGUSD", "انس نقره جهانی (Silver)", "commodity", "USD"),
                ("USD", "اسکناس دلار آمریکا", "cash", "TOMAN"),
                ("USDT", "تتر (USDT)", "crypto", "TOMAN"),
            ]

            for sym, name, a_class, curr in core_assets:
                if sym.upper() not in existing_symbols:
                    # Also check alias (e.g. XAU)
                    if sym == "XAUUSD" and "XAU" in existing_symbols:
                        continue
                    initial_p = Decimal("0")
                    if sym.upper() in price_catalog:
                        initial_p = (
                            price_catalog[sym.upper()]["toman"]
                            if curr == "TOMAN"
                            else price_catalog[sym.upper()]["usd"]
                        )

                    new_asset = AssetModel(
                        symbol=sym.upper(),
                        name=name,
                        asset_class=a_class,
                        currency=curr,
                        current_price=initial_p,
                        price_updated_at=now if initial_p > Decimal("0") else None,
                        notes=f"بروزرسانی خودکار نرخ بازار ({curr})",
                    )
                    db.add(new_asset)
                    existing_symbols[sym.upper()] = new_asset
                    updated_count += 1

            await db.commit()
            total_quotes = len(gold_and_coins) + len(commodities) + len(currencies) + len(cryptos)
            logger.info(
                "Market price synchronization complete. Updated %d assets, %d total quotes cached.",
                updated_count,
                total_quotes,
            )

            return MarketSyncResultResponse(
                success=True,
                message="بروزرسانی نرخ‌های لحظه‌ای کالاها، طلا، ارز و رمزارز با موفقیت انجام شد.",
                updated_assets_count=updated_count,
                total_quotes_fetched=total_quotes,
                last_sync_time=now,
            )
