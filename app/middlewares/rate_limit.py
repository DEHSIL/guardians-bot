from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.services.redis_service import RedisService


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, redis: RedisService, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self._limit = limit
        self._window_seconds = window_seconds

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = event.from_user if isinstance(event, (Message, CallbackQuery)) else None
        if user is None:
            return await handler(event, data)
        allowed = await self._redis.allow_request(
            key=f"guardians:bot:rate-limit:{user.id}", limit=self._limit, window_seconds=self._window_seconds
        )
        if allowed:
            return await handler(event, data)
        if isinstance(event, Message):
            await event.answer("Слишком много сообщений. Попробуйте немного позже.")
        elif isinstance(event, CallbackQuery):
            await event.answer("Слишком много запросов. Попробуйте позже.", show_alert=True)
        return None
