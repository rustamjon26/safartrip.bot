"""
timeout_scheduler.py - Background task for booking timeout handling.

Runs every 30 seconds to find and process expired bookings:
1. Query bookings where expires_at < NOW() and status in ('new', 'sent_to_partner')
2. Mark them as 'timeout'
3. Notify users about the timeout

IMPORTANT: This task survives bot restarts by being started on startup.
"""

import asyncio
import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import db_postgres as db_pg
from html_utils import h

logger = logging.getLogger(__name__)

# Task reference for graceful shutdown
_timeout_task: Optional[asyncio.Task] = None

# Check interval in seconds
CHECK_INTERVAL_SECONDS = 30


async def process_expired_bookings(bot: Bot) -> int:
    """
    Find and process all expired bookings.
    
    Returns:
        Number of bookings marked as timed out
    """
    expired = await db_pg.get_expired_bookings()
    
    if not expired:
        return 0
    
    processed = 0
    
    for booking in expired:
        booking_id = booking["id"]
        user_telegram_id = booking["user_telegram_id"]
        listing_title = booking.get("listing_title") or "Xizmat"
        
        # Mark as timeout
        success = await db_pg.mark_booking_timeout(booking_id)
        
        if not success:
            logger.warning(f"Failed to mark booking {booking_id} as timeout")
            continue
        
        # Notify user
        try:
            await bot.send_message(
                chat_id=user_telegram_id,
                text=(
                    f"⏰ <b>Vaqt tugadi</b>\n\n"
                    f"Sizning <b>{h(listing_title)}</b> bo'yicha buyurtmangizga "
                    f"belgilangan vaqt ichida javob bo'lmadi.\n\n"
                    f"Iltimos, keyinroq qaytadan urinib ko'ring yoki "
                    f"boshqa xizmatni tanlang."
                ),
                parse_mode="HTML",
            )
            logger.info(f"Notified user {user_telegram_id} about booking {booking_id} timeout")
        except TelegramAPIError as e:
            logger.error(f"Failed to notify user {user_telegram_id} about timeout: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error notifying user about timeout: {e}")
        
        processed += 1
    
    return processed


async def timeout_checker_loop(bot: Bot):
    """
    Background loop that periodically checks for expired bookings.
    
    Runs every CHECK_INTERVAL_SECONDS (30s by default).
    Handles errors gracefully and continues running.
    """
    logger.info(f"Timeout checker started, interval={CHECK_INTERVAL_SECONDS}s")
    
    while True:
        try:
            processed = await process_expired_bookings(bot)
            if processed > 0:
                logger.info(f"Processed {processed} expired bookings")
        except asyncio.CancelledError:
            logger.info("Timeout checker cancelled")
            raise
        except Exception as e:
            logger.exception(f"Error in timeout checker loop: {e}")
        
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Timeout checker sleep cancelled")
            raise


def start_timeout_scheduler(bot: Bot) -> asyncio.Task:
    """
    Start the timeout scheduler as a background task.
    
    Call this function during bot startup to ensure expired bookings
    are processed even after restarts.
    
    Args:
        bot: Aiogram Bot instance for sending notifications
    
    Returns:
        The asyncio.Task object (can be cancelled for graceful shutdown)
    """
    global _timeout_task
    
    if _timeout_task is not None and not _timeout_task.done():
        logger.warning("Timeout scheduler already running")
        return _timeout_task
    
    _timeout_task = asyncio.create_task(timeout_checker_loop(bot))
    logger.info("Timeout scheduler task created")
    
    return _timeout_task


async def stop_timeout_scheduler():
    """
    Stop the timeout scheduler gracefully.
    
    Call this function during bot shutdown.
    """
    global _timeout_task
    
    if _timeout_task is None:
        return
    
    if not _timeout_task.done():
        _timeout_task.cancel()
        try:
            await _timeout_task
        except asyncio.CancelledError:
            pass
        logger.info("Timeout scheduler stopped")
    
    _timeout_task = None
