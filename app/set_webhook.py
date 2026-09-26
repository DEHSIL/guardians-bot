"""Run manually after deploying the production bot domain."""
import argparse
import asyncio
import re
from urllib.parse import urlsplit

from aiogram import Bot

from app.webhook import WebhookSettings


async def configure(base_url: str) -> None:
    url = urlsplit(base_url)
    if url.scheme != "https" or not url.hostname or url.path not in ("", "/") or url.query or url.fragment or url.username:
        raise ValueError("Provide an HTTPS domain without a path or query string")
    settings = WebhookSettings()
    secret = settings.webhook_secret.get_secret_value()
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", secret):
        raise ValueError("WEBHOOK_SECRET must contain 16-256 letters, digits, underscores or hyphens")
    async with Bot(token=settings.bot_token.get_secret_value()) as bot:
        await bot.set_webhook(
            base_url.rstrip("/") + "/telegram/webhook",
            secret_token=secret,
            allowed_updates=["message", "edited_message", "callback_query"],
            max_connections=1,
            drop_pending_updates=False,
        )
    print("Production Telegram webhook configured")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="https://your-bot.vercel.app")
    asyncio.run(configure(parser.parse_args().base_url))
