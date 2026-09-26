import asyncio
import logging
from contextlib import asynccontextmanager, AsyncExitStack
from typing import AsyncIterator

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.types import BotCommand
from redis.asyncio import Redis, from_url

from app.core.config import Settings, get_settings
from app.handlers import common
from app.handlers import registration
from app.handlers import sos
from app.handlers import contacts, patrol
from app.middlewares.api_middleware import APIMiddleware
from app.middlewares.rate_limit import RateLimitMiddleware
from app.services.api_client import APIClient
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def application(settings: Settings) -> AsyncIterator[tuple[Bot, Dispatcher]]:
    async with AsyncExitStack() as stack:
        redis: Redis = from_url(str(settings.redis_url), decode_responses=True)
        stack.push_async_callback(redis.aclose)
        await redis.ping()
        storage = RedisStorage(redis=redis, key_builder=DefaultKeyBuilder(prefix="guardians:bot:fsm", with_bot_id=True))
        headers = {"Accept": "application/json", "X-API-Key": settings.backend_api_token.get_secret_value()}
        http_client = await stack.enter_async_context(httpx.AsyncClient(
            base_url=str(settings.backend_base_url).rstrip("/"),
            timeout=httpx.Timeout(settings.request_timeout_seconds), headers=headers,
        ))
        response = await http_client.get("/ready")
        response.raise_for_status()
        # A read-only request also verifies the shared API key before polling.
        response = await http_client.get("/api/v1/users/0")
        if response.status_code != 404:
            response.raise_for_status()
        bot = Bot(token=settings.bot_token.get_secret_value(),
                  default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        stack.push_async_callback(bot.session.close)
        dispatcher = Dispatcher(storage=storage)
        redis_service = RedisService(redis)
        dispatcher.update.outer_middleware(APIMiddleware(APIClient(http_client)))
        dispatcher.message.outer_middleware(RateLimitMiddleware(
            redis_service, settings.rate_limit_requests, settings.rate_limit_window_seconds))
        dispatcher.callback_query.outer_middleware(RateLimitMiddleware(
            redis_service, settings.rate_limit_requests, settings.rate_limit_window_seconds))
        dispatcher.include_routers(common.router, registration.router, contacts.router, sos.router, patrol.router)
        yield bot, dispatcher


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    async with application(settings) as (bot, dispatcher):
        await bot.set_my_commands([
            BotCommand(command="start", description="РќР°С‡Р°С‚СЊ СЂР°Р±РѕС‚Сѓ"),
            BotCommand(command="register", description="РЎРѕР·РґР°С‚СЊ РїСЂРѕС„РёР»СЊ"),
            BotCommand(command="profile", description="РњРѕР№ РїСЂРѕС„РёР»СЊ"),
            BotCommand(command="cancel_sos", description="Отменить активный SOS"),
            BotCommand(command="help", description="РЎРїСЂР°РІРєР°"),
        ])
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Bot polling started")
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
