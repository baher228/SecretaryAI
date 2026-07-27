from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from secretary_ai.domain.models import ChatRequest

if TYPE_CHECKING:
    from secretary_ai.core.config import Settings
    from secretary_ai.services.secretary import SecretaryService

logger = logging.getLogger(__name__)

try:
    from aiogram import Bot, Dispatcher, F
    from aiogram.filters import Command, CommandStart
    from aiogram.types import Message
except Exception:  # pragma: no cover
    Bot = None  # type: ignore[assignment]
    Dispatcher = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    Command = None  # type: ignore[assignment]
    CommandStart = None  # type: ignore[assignment]
    Message = object  # type: ignore[assignment,misc]


class TelegramTextBotService:
    """Optional aiogram bot merged into the main runtime."""

    def __init__(self, settings: Settings, secretary: SecretaryService) -> None:
        self.settings = settings
        self.secretary = secretary
        self._enabled = bool(settings.telegram_text_bot_enabled and settings.telegram_text_bot_token)
        self._allowed = {
            int(raw.strip())
            for raw in settings.telegram_text_bot_allowed_ids.split(",")
            if raw.strip().isdigit()
        }
        self._bot: Bot | None = None
        self._dispatcher: Dispatcher | None = None
        self._task: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        if not self._enabled:
            return
        if Bot is None or Dispatcher is None:
            logger.warning("telegram_text_bot_enabled=true but aiogram is not installed")
            return
        if self._task and not self._task.done():
            return
        self._bot = Bot(token=str(self.settings.telegram_text_bot_token))
        self._dispatcher = Dispatcher()
        self._register_handlers()
        self._task = asyncio.create_task(self._dispatcher.start_polling(self._bot))
        logger.info("Merged Telegram text bot started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("Telegram text bot stop error", exc_info=True)
        if self._bot is not None:
            await self._bot.session.close()
        self._task = None
        self._dispatcher = None
        self._bot = None

    def _register_handlers(self) -> None:
        assert self._dispatcher is not None

        @self._dispatcher.message(CommandStart())
        async def _start(message: Message) -> None:
            if not self._is_allowed(message):
                return
            await message.answer("Secretary AI text channel is active. Send text to create notifications.")

        @self._dispatcher.message(Command("status"))
        async def _status(message: Message) -> None:
            if not self._is_allowed(message):
                return
            calls = len(self.secretary.telegram.list_calls())
            await message.answer(f"Voice channel ready. Active/known calls: {calls}.")

        @self._dispatcher.message(Command("calls"))
        async def _calls(message: Message) -> None:
            if not self._is_allowed(message):
                return
            items = self.secretary.telegram.list_calls()[:5]
            if not items:
                await message.answer("No calls recorded yet.")
                return
            lines = [f"- {c.get('call_id')} ({c.get('status')})" for c in items]
            await message.answer("Recent calls:\n" + "\n".join(lines))

        @self._dispatcher.message(F.text)
        async def _chat(message: Message) -> None:
            if not self._is_allowed(message):
                return
            text = str(message.text or "").strip()
            if not text:
                return
            result = await self.secretary.chat_direct(ChatRequest(message=text))
            await message.answer(result.reply[:3900])

    def _is_allowed(self, message: Message) -> bool:
        user = getattr(message, "from_user", None)
        user_id = int(getattr(user, "id", 0) or 0)
        if not self._allowed:
            return True
        return user_id in self._allowed
