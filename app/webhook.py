"""Vercel entry point. Updates finish before the HTTP response is returned."""
import asyncio
import secrets
from contextlib import asynccontextmanager
from hmac import compare_digest

from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import Field, SecretStr

from app.core.config import Settings
from app.main import setup_application


class WebhookSettings(Settings):
    webhook_secret: SecretStr = Field(min_length=16, max_length=256)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = WebhookSettings()
    async with setup_application(settings) as (bot, dispatcher):
        app.state.bot = bot
        app.state.dispatcher = dispatcher
        app.state.webhook_secret = settings.webhook_secret.get_secret_value()
        yield


app = FastAPI(title="Guardians Telegram webhook", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    expected = request.app.state.webhook_secret
    if not x_telegram_bot_api_secret_token or not compare_digest(
        x_telegram_bot_api_secret_token.encode(), expected.encode()
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    try:
        update = Update.model_validate(await request.json())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Telegram update") from exc

    bot = request.app.state.bot
    dispatcher = request.app.state.dispatcher
    redis = dispatcher.storage.redis
    key = f"guardians:bot:webhook:{bot.id}:{update.update_id}"
    # Persist successful update IDs across concurrent instances and Telegram retries.
    if await redis.get(key) == "done":
        return {"ok": True}
    lock = secrets.token_hex(16)
    if not await redis.set(key, lock, nx=True, ex=90):
        raise HTTPException(status_code=503, detail="Update is already being processed")
    try:
        async with asyncio.timeout(8):
            await dispatcher.feed_update(bot, update)
        await redis.set(key, "done", ex=86400)
    finally:
        await redis.eval(
            "if redis.call('GET', KEYS[1]) == ARGV[1] then "
            "return redis.call('DEL', KEYS[1]) else return 0 end",
            1, key, lock,
        )
    return {"ok": True}
