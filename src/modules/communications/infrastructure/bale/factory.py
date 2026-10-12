from src.app.core.settings import Settings, get_settings
from src.modules.communications.infrastructure.bale.base import BaseBaleProvider
from src.modules.communications.infrastructure.bale.mock_provider import MockBaleProvider
from src.modules.communications.infrastructure.bale.safir import BaleSafirProvider

_bale_instance: BaseBaleProvider | None = None


def get_bale_provider(settings: Settings | None = None) -> BaseBaleProvider:
    """Factory function for Bale Messenger provider singleton."""
    global _bale_instance
    if _bale_instance is not None:
        return _bale_instance

    if settings is None:
        settings = get_settings()

    provider_name = settings.BALE_PROVIDER.lower().strip()

    if provider_name == "safir" and settings.BALE_API_ACCESS_KEY and settings.BALE_BOT_ID > 0:
        _bale_instance = BaleSafirProvider(
            api_access_key=settings.BALE_API_ACCESS_KEY,
            bot_id=settings.BALE_BOT_ID,
            base_url=settings.BALE_BASE_URL,
        )
    else:
        _bale_instance = MockBaleProvider()

    return _bale_instance


def reset_bale_provider() -> None:
    """Reset provider singleton instance (primarily for tests)."""
    global _bale_instance
    _bale_instance = None
