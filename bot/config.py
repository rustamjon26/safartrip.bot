"""Bot package config helper.

Re-exports root config so imports inside bot/ can stay clean.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import BOT_TOKEN, ADMINS, API_ID, API_HASH, get_pyrogram_config  # noqa: F401,E402

__all__ = ["BOT_TOKEN", "ADMINS", "API_ID", "API_HASH", "get_pyrogram_config"]
