import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database.models import UserModel
from src.app.database.session import get_db_session
from src.modules.assets.application.dtos import (
    AssetClassCreate,
    AssetClassResponse,
    AssetCreate,
    AssetPositionResponse,
    AssetPositionUpdate,
    AssetResponse,
    AssetUpdate,
    MarketRatesResponse,
    MarketSyncResultResponse,
)
from src.modules.assets.application.market_sync_service import MarketSyncService
from src.modules.assets.application.services import AssetService
from src.modules.assets.infrastructure.scheduler import market_scheduler
from src.modules.auth.presentation.dependencies import get_current_user, get_optional_current_user

assets_router = APIRouter(prefix="/assets", tags=["Assets"])
market_sync_service = MarketSyncService()


def get_asset_service(db: AsyncSession = Depends(get_db_session)) -> AssetService:
    return AssetService(db)


@assets_router.get("/market/rates", response_model=MarketRatesResponse)
async def get_market_rates(
    db: AsyncSession = Depends(get_db_session),
    current_user: UserModel | None = Depends(get_optional_current_user),
) -> MarketRatesResponse:
    """Retrieve the latest synchronized market rates for commodities, gold, currency, and crypto.

    Served from fast cache updated periodically ~5 times a day by background task.
    Accessible to both authenticated users and public guests.
    """
    return await market_sync_service.get_market_rates(db=db)


@assets_router.post("/market/sync", response_model=MarketSyncResultResponse)
async def trigger_market_sync(
    current_user: UserModel = Depends(get_current_user),
) -> MarketSyncResultResponse:
    """Manual market rate sync is restricted. Background scheduler updates automatically 5 times a day."""
    if not getattr(current_user, "is_superuser", False) and getattr(current_user, "role", "") not in ("admin", "sysmanager"):
        cached = await market_sync_service.get_market_rates()
        return MarketSyncResultResponse(
            success=False,
            message="بروزرسانی دستی توسط کاربر مجاز نمی‌باشد. نرخ‌ها به صورت خودکار ۵ بار در شبانه‌روز همگام‌سازی می‌شوند.",
            updated_assets_count=0,
            total_quotes_fetched=len(cached.gold_and_coins) + len(cached.commodities) + len(cached.currencies) + len(cached.cryptocurrency),
            last_sync_time=cached.last_sync_time,
        )
    return await market_scheduler.trigger_manual_sync()

@assets_router.get("/classes", response_model=list[AssetClassResponse])
async def list_asset_classes(
    service: AssetService = Depends(get_asset_service),
) -> list[AssetClassResponse]:
    """List all active asset class definitions (equity, crypto, commodity, etc.)."""
    classes = await service.list_asset_classes()
    return [AssetClassResponse.model_validate(c) for c in classes]


@assets_router.post("/classes", response_model=AssetClassResponse, status_code=status.HTTP_201_CREATED)
async def create_asset_class(
    payload: AssetClassCreate,
    service: AssetService = Depends(get_asset_service),
) -> AssetClassResponse:
    """Create a new asset class definition."""
    asset_class = await service.create_asset_class(payload)
    return AssetClassResponse.model_validate(asset_class)


@assets_router.get("", response_model=list[AssetResponse])
async def list_assets(
    asset_class: str | None = None,
    is_active: bool | None = None,
    service: AssetService = Depends(get_asset_service),
) -> list[AssetResponse]:
    assets = await service.list_assets(asset_class=asset_class, is_active=is_active)
    return [AssetResponse.model_validate(a) for a in assets]


@assets_router.get("/positions", response_model=list[AssetPositionResponse])
async def list_positions(
    account_id: uuid.UUID | None = None,
    service: AssetService = Depends(get_asset_service),
    current_user: UserModel = Depends(get_current_user),
) -> list[AssetPositionResponse]:
    return await service.list_positions(user_id=current_user.id, account_id=account_id)


@assets_router.patch("/positions/{position_id}", response_model=AssetPositionResponse)
async def update_position(
    position_id: uuid.UUID,
    payload: AssetPositionUpdate,
    service: AssetService = Depends(get_asset_service),
    current_user: UserModel = Depends(get_current_user),
) -> AssetPositionResponse:
    return await service.update_position(
        position_id=position_id, payload=payload, user_id=current_user.id
    )


@assets_router.delete("/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    position_id: uuid.UUID,
    service: AssetService = Depends(get_asset_service),
    current_user: UserModel = Depends(get_current_user),
) -> None:
    await service.delete_position(position_id=position_id, user_id=current_user.id)


@assets_router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: uuid.UUID,
    service: AssetService = Depends(get_asset_service),
) -> AssetResponse:
    asset = await service.get_asset(asset_id)
    return AssetResponse.model_validate(asset)


@assets_router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: AssetCreate,
    service: AssetService = Depends(get_asset_service),
) -> AssetResponse:
    asset = await service.create_asset(payload)
    return AssetResponse.model_validate(asset)


@assets_router.patch("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: uuid.UUID,
    payload: AssetUpdate,
    service: AssetService = Depends(get_asset_service),
) -> AssetResponse:
    asset = await service.update_asset(asset_id, payload)
    return AssetResponse.model_validate(asset)


@assets_router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: uuid.UUID,
    service: AssetService = Depends(get_asset_service),
) -> None:
    await service.delete_asset(asset_id)
