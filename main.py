"""
main.py - Safar.uz Telegram Bot Entry Point (Final Phase)

Unified CMS architecture:
- listings table for all categories
- bookings table with 5-minute timeout
- Partner admin management via /add, /my_listings
- User browsing via /browse

Railway + PostgreSQL (asyncpg)
"""

import asyncio
import logging
import os
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

# Configuration — single source of truth
from config import BOT_TOKEN, ADMINS


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Import modules
import db_postgres as db
from listing_wizard import listing_wizard_router
from listings_user_flow import user_flow_router
from booking_dispatch import booking_dispatch_router, start_timeout_checker, stop_timeout_checker


def get_storage():
    """Get FSM storage. Uses Redis if REDIS_URL set, else MemoryStorage."""
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            logger.info("Using Redis storage for FSM")
            return RedisStorage.from_url(redis_url)
        except Exception as e:
            logger.warning(f"Redis unavailable, using memory: {e}")
    return MemoryStorage()


async def main():
    """Main bot entry point."""
    logger.info("Starting Safar.uz Bot (Final Phase)...")
    logger.info(f"Admins: {ADMINS}")
    
    # Initialize database
    if not await db.init_pool():
        logger.error("Failed to initialize database pool!")
        sys.exit(1)
    
    if not await db.ensure_schema():
        logger.error("Failed to ensure database schema!")
        sys.exit(1)
    
    # Create bot and dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    
    storage = get_storage()
    dp = Dispatcher(storage=storage)
    
    # Register routers (order matters)
    dp.include_router(listing_wizard_router)    # /add, /my_listings
    dp.include_router(user_flow_router)         # /browse, booking flow
    dp.include_router(booking_dispatch_router)  # Partner accept/reject
    
    # Add /start and /help handlers
    from aiogram.types import Message
    from aiogram.filters import Command
    
    @dp.message(Command("start"))
    async def cmd_start(message: Message):
        """Handle /start command."""
        await message.answer(
            "🏔 <b>Safar.uz</b>\n\n"
            "Zomin sayohatlaringiz uchun eng yaxshi takliflar!\n\n"
            "📋 <b>Buyruqlar:</b>\n"
            "/browse - Listinglarni ko'rish\n"
            "/add - Yangi listing qo'shish (partnyorlar uchun)\n"
            "/my_listings - Listinglaringizni boshqarish\n"
            "/help - Yordam",
            parse_mode="HTML",
        )
    
    @dp.message(Command("help"))
    async def cmd_help(message: Message):
        """Handle /help command."""
        await message.answer(
            "📚 <b>Yordam</b>\n\n"
            "<b>Foydalanuvchilar uchun:</b>\n"
            "/browse - Mehmonxonalar, gidlar, taksini ko'rish\n"
            "Listingni tanlab, bron qilishingiz mumkin\n\n"
            "<b>Partnyorlar uchun:</b>\n"
            "/add - Yangi listing qo'shish\n"
            "/my_listings - Listinglaringizni boshqarish\n\n"
            "<b>Admin:</b>\n"
            "/health - Tizim holati",
            parse_mode="HTML",
        )
    
    @dp.message(Command("health"))
    async def cmd_health(message: Message):
        """Health check command."""
        if message.from_user.id not in ADMINS:
            return
        
        ok, msg = await db.healthcheck()
        status = "✅" if ok else "❌"
        
        listings_count = await db.get_listings_count()
        bookings_count = await db.get_bookings_count()
        bookings_by_status = await db.get_bookings_by_status()
        
        lines = [
            "🏥 <b>HEALTH CHECK</b>",
            "",
            f"PostgreSQL: {status} {msg}",
            "",
            f"📋 Listings (active): {listings_count}",
            f"📝 Bookings (total): {bookings_count}",
        ]
        
        if bookings_by_status:
            status_line = ", ".join(f"{k}: {v}" for k, v in bookings_by_status.items())
            lines.append(f"📊 By status: {status_line}")
        
        await message.answer("\n".join(lines), parse_mode="HTML")
    
    # Clean start
    await bot.delete_webhook(drop_pending_updates=True)
    
    logger.info("Bot initialized, starting polling...")
    print("✅ Bot is running! Press Ctrl+C to stop.")
    
    # Start timeout checker
    timeout_task = start_timeout_checker(bot)
    logger.info("Timeout checker started (30s interval)")
    
    # Start polling
    try:
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        logger.info("Polling cancelled")
    except Exception as e:
        logger.error(f"Polling error: {e}", exc_info=True)
        raise
    finally:
        logger.info("Shutting down...")
        
        await stop_timeout_checker()
        
        timeout_task.cancel()
        with suppress(asyncio.CancelledError):
            await timeout_task
        
        await db.close_pool()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped.")
