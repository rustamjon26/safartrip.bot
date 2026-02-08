"""Centralized configuration for Safar.uz bot.

All secrets must come from environment variables.
This module loads .env for LOCAL development only.
In production, prefer real environment variables.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()  # safe for local; no-op if .env absent


def _require_env(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(
            f"❌ Required environment variable '{name}' is missing or empty. "
            f"Set it in your .env or server environment."
        )
    return val


def _require_int(name: str) -> int:
    raw = _require_env(name)
    try:
        return int(raw)
    except ValueError as e:
        raise RuntimeError(
            f"❌ Environment variable '{name}' must be an integer, got: {raw}"
        ) from e


# =============================================================================
# Aiogram bot (main bot)
# =============================================================================
BOT_TOKEN: str = _require_env("BOT_TOKEN")

_admins_raw = os.getenv("ADMINS", "").strip()
ADMINS = [int(x.strip()) for x in _admins_raw.split(",") if x.strip().isdigit()]
if not ADMINS:
    raise RuntimeError(
        "❌ ADMINS environment variable is empty/invalid. "
        "Set comma-separated Telegram user IDs, e.g. ADMINS=123,456"
    )


# =============================================================================
# Pyrogram admin bot (optional: bot/bot.py)
# =============================================================================
# Only validated when you call get_pyrogram_config().
API_ID = os.getenv("API_ID", "").strip()
API_HASH = os.getenv("API_HASH", "").strip()


def get_pyrogram_config() -> dict:
    if not API_ID or not API_HASH:
        raise RuntimeError(
            "❌ Pyrogram admin bot requires API_ID and API_HASH. "
            "Get them from https://my.telegram.org/apps and set in .env"
        )
    return {
        "api_id": int(API_ID),
        "api_hash": API_HASH,
        "bot_token": BOT_TOKEN,
    }
