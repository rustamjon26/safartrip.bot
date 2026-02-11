"""Centralized configuration for Safar.uz bot.

All secrets must come from environment variables.
This module loads .env for LOCAL development only.
In production, prefer real environment variables.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

# IMPORTANT: override=False ensures Railway/system env vars take precedence
# over any accidentally deployed .env file
load_dotenv(override=False)


def get_startup_info() -> str:
    """
    Get one-line startup info for logging.
    Returns: "Python X.Y.Z | git:abc1234 | mode:polling"
    """
    import sys
    import subprocess

    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # Try to get git commit (safe to fail)
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2
        ).decode().strip()
    except Exception:
        git_sha = "unknown"

    mode = "webhook" if os.getenv("WEBHOOK_URL") else "polling"

    return f"Python {python_ver} | git:{git_sha} | mode:{mode}"


def _require_env(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(
            f"❌ Required environment variable '{name}' is missing or empty. "
            f"Set it in your .env or server environment."
        )
    return val


# =============================================================================
# Aiogram bot
# =============================================================================
BOT_TOKEN: str = _require_env("BOT_TOKEN")

_admins_raw = os.getenv("ADMINS", "").strip()
ADMINS: list[int] = [int(x.strip()) for x in _admins_raw.split(",") if x.strip().isdigit()]
if not ADMINS:
    raise RuntimeError(
        "❌ ADMINS environment variable is empty/invalid. "
        "Set comma-separated Telegram user IDs, e.g. ADMINS=123,456"
    )
