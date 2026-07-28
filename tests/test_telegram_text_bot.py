from types import SimpleNamespace

from secretary_ai.core.config import Settings
from secretary_ai.services.telegram_text_bot import TelegramTextBotService


def _secretary() -> SimpleNamespace:
    return SimpleNamespace()


def test_text_bot_fails_closed_without_allowlist() -> None:
    service = TelegramTextBotService(
        Settings(
            telegram_text_bot_enabled=True,
            telegram_text_bot_token="token",
            telegram_text_bot_allowed_ids="",
        ),
        _secretary(),  # type: ignore[arg-type]
    )

    assert service.enabled is False
    assert service._is_allowed(SimpleNamespace(from_user=SimpleNamespace(id=123))) is False


def test_text_bot_accepts_only_allowlisted_user() -> None:
    service = TelegramTextBotService(
        Settings(
            telegram_text_bot_enabled=True,
            telegram_text_bot_token="token",
            telegram_text_bot_allowed_ids="123, 456",
        ),
        _secretary(),  # type: ignore[arg-type]
    )

    assert service.enabled is True
    assert service._is_allowed(SimpleNamespace(from_user=SimpleNamespace(id=123))) is True
    assert service._is_allowed(SimpleNamespace(from_user=SimpleNamespace(id=999))) is False
