import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.shared.domain.currency import Currency


class AssetBase(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=150)
    asset_class: str = Field(
        ..., description="equity, fixed_income, commodity, real_estate, crypto, cash"
    )
    currency: Currency = Field(default=Currency.TOMAN)
    is_active: bool = Field(default=False, description="Whether the asset is actively monitored and tradeable")
    notes: str | None = None


class AssetCreate(AssetBase):
    initial_price: Decimal = Field(default=Decimal("0.0000"), ge=0)


class AssetUpdate(BaseModel):
    symbol: str | None = None
    name: str | None = None
    asset_class: str | None = None
    currency: Currency | None = None
    current_price: Decimal | None = Field(None, ge=0)
    is_active: bool | None = None
    notes: str | None = None


class AssetResponse(AssetBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    current_price: Decimal
    price_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AssetPositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    asset_id: uuid.UUID
    quantity: Decimal
    average_cost_basis: Decimal
    current_price: Decimal
    current_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percent: Decimal
    asset_symbol: str
    asset_name: str
    asset_class: str
    currency: str


class AssetPositionUpdate(BaseModel):
    quantity: Decimal | None = Field(None, ge=0)
    average_cost_basis: Decimal | None = Field(None, ge=0)


class MarketQuoteDTO(BaseModel):
    symbol: str
    name: str
    name_en: str | None = None
    category: str  # gold_coin, commodity, currency, crypto
    price: Decimal
    unit: str  # تومان, دلار
    change_percent: float | None = None
    price_toman: Decimal | None = None
    updated_at: datetime | None = None


class MarketRatesResponse(BaseModel):
    gold_and_coins: list[MarketQuoteDTO]
    commodities: list[MarketQuoteDTO]
    currencies: list[MarketQuoteDTO]
    cryptocurrency: list[MarketQuoteDTO]
    stocks: list[MarketQuoteDTO] = Field(default_factory=list)
    usd_toman_rate: Decimal | None = None
    last_sync_time: datetime | None = None
    sync_source: str = "BRS API"


class MarketSyncResultResponse(BaseModel):
    success: bool
    message: str
    updated_assets_count: int
    total_quotes_fetched: int
    last_sync_time: datetime | None = None


class AssetClassResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    label: str
    description: str | None = None
    icon: str
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AssetClassCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    icon: str = Field(default="Layers", max_length=50)
    display_order: int = Field(default=0)
    is_active: bool = Field(default=True)

