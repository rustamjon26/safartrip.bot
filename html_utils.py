"""
HTML safety utilities for Telegram messages.

Prevents "can't parse entities" errors by:
1. Always escaping user-provided text
2. Falling back to plain text when HTML parsing fails
"""

import html
import logging
from typing import Any, Optional

from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)


def escape_html(text: Any) -> str:
    """
    HTML-escape any value for safe Telegram HTML parsing.
    
    Args:
        text: Any value (will be converted to string)
    
    Returns:
        HTML-escaped string safe for parse_mode="HTML"
    """
    if text is None:
        return ""
    return html.escape(str(text), quote=False)


# Alias for convenience
h = escape_html


async def safe_send(
    message: Message,
    text: str,
    parse_mode: Optional[str] = "HTML",
    **kwargs
) -> Message:
    """
    Safely send a message with HTML fallback.
    
    If Telegram returns "can't parse entities", automatically
    retries with parse_mode=None (plain text).
    
    Args:
        message: Message object to reply to
        text: Message text
        parse_mode: Parse mode (default: HTML)
        **kwargs: Additional arguments for message.answer()
    
    Returns:
        Sent Message object
    """
    try:
        return await message.answer(text, parse_mode=parse_mode, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            logger.warning("HTML parse failed, falling back to plain text: %s", e)
            kwargs.pop("parse_mode", None)
            return await message.answer(text, parse_mode=None, **kwargs)
        raise


async def safe_edit(
    message: Message,
    text: str,
    parse_mode: Optional[str] = "HTML",
    **kwargs
) -> Message:
    """
    Safely edit a message with HTML fallback.
    
    If Telegram returns "can't parse entities", automatically
    retries with parse_mode=None (plain text).
    
    Args:
        message: Message object to edit
        text: New message text
        parse_mode: Parse mode (default: HTML)
        **kwargs: Additional arguments for message.edit_text()
    
    Returns:
        Edited Message object
    """
    try:
        return await message.edit_text(text, parse_mode=parse_mode, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            logger.warning("HTML parse failed in edit, falling back to plain text: %s", e)
            kwargs.pop("parse_mode", None)
            return await message.edit_text(text, parse_mode=None, **kwargs)
        raise


async def safe_send_photo(
    message: Message,
    photo: str,
    caption: Optional[str] = None,
    parse_mode: Optional[str] = "HTML",
    **kwargs
) -> Message:
    """
    Safely send a photo with caption, with HTML fallback.
    
    Args:
        message: Message object to reply to
        photo: Photo file_id or URL
        caption: Optional caption text
        parse_mode: Parse mode for caption (default: HTML)
        **kwargs: Additional arguments for message.answer_photo()
    
    Returns:
        Sent Message object
    """
    try:
        return await message.answer_photo(
            photo=photo,
            caption=caption,
            parse_mode=parse_mode,
            **kwargs
        )
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            logger.warning("HTML parse failed in photo caption, falling back: %s", e)
            kwargs.pop("parse_mode", None)
            return await message.answer_photo(
                photo=photo,
                caption=caption,
                parse_mode=None,
                **kwargs
            )
        raise
