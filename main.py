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
from aiogram.fsm.context import FSMContext

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
from listings_user_flow import user_flow_router, start_registration, build_main_menu
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
    async def cmd_start(message: Message, state: FSMContext):
        """Handle /start command. Checks registration."""
        user_id = message.from_user.id
        
        # Check if user exists
        user = await db.get_user_by_telegram_id(user_id)
        if not user:
            await start_registration(message, state)
            return

        lines = [
            "Assalomu alaykum! <b>SafarTrip.uz</b> botiga xush kelibsiz.",
            "",
            "📍 <b>Hudud:</b> Zomin",
            "",
            "Bu yerda siz mehmonxonalar, dam olish maskanlari va gid xizmatlarini oson topishingiz va band qilishingiz mumkin.",
            "",
            "Zomin bo'yicha eng yaxshi takliflar shu yerda!",
            "<i>(Boshqa hududlar tez orada qo'shiladi)</i>",
            "",
            "📋 <b>Buyruqlar:</b>",
            "/browse - Listinglarni ko'rish (Sayohatni boshlash)",
            "/help - Yordam",
        ]
        if user_id in ADMINS:
            lines.append("/add - Yangi listing qo'shish")
            lines.append("/my_listings - Listinglaringizni boshqarish")
        await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=build_main_menu(user_id))
    
    @dp.message(Command("help"))
    async def cmd_help(message: Message):
        """Handle /help command."""
        user_id = message.from_user.id
        lines = [
            "📚 <b>Yordam</b>",
            "",
            "<b>Foydalanuvchilar uchun:</b>",
            "/browse - Mehmonxonalar, gidlar, taksini ko'rish",
            "Listingni tanlab, bron qilishingiz mumkin.",
            "",
            "<i>SafarTrip.uz — Sayohatni oson rejalashtiring.</i>",
        ]
        if user_id in ADMINS:
            lines.extend([
                "",
                "<b>Admin uchun:</b>",
                "/add - Yangi listing qo'shish",
                "/my_listings - Listinglaringizni boshqarish",
                "/health - Tizim holati",
            ])
        await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=build_main_menu(user_id))
    
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
        
        await db.close_pool()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped.")
