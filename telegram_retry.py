"""
Telegram API retry utilities with exponential backoff.

Handles:
- TelegramRetryAfter (429): Wait specified time + buffer
- TelegramAPIError: Exponential backoff retry
"""
import asyncio
from typing import TypeVar, Awaitable

from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError

T = TypeVar("T")


async def retry_telegram(
    coro: Awaitable[T],
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> T:
    """
    Execute a Telegram API coroutine with retry logic.
    
    Args:
        coro: Awaitable to execute
        max_retries: Maximum retry attempts
        base_delay: Base delay for exponential backoff
    
    Returns:
        Result of the coroutine
    
    Raises:
        Original exception after max retries exhausted
    """
    last_error: Exception | None = None
    
    for attempt in range(max_retries):
        try:
            return await coro
        except TelegramRetryAfter as e:
            wait_time = e.retry_after + 1
            print(f"⏳ Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_time)
            last_error = e
        except TelegramAPIError as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"⚠️ Telegram API error, retrying in {delay}s: {e}")
            await asyncio.sleep(delay)
            last_error = e
    
    raise last_error or RuntimeError("Retry failed unexpectedly")
