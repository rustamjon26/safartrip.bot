"""
Safar.uz Telegram Bot - Main Entry Point (MVP+ with Admin Features)
A travel services booking bot with:
- SQLite persistence (users + orders)
- Multi-language support (UZ/RU/EN)
- Admin status management via inline buttons
- Admin commands (/orders, /order, /find, /filter, /export)
- Rate limiting for anti-spam
- Automated daily database backups
- Global error logging with admin notifications
"""
import asyncio
import os
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

# Import config first to validate environment variables
from config import BOT_TOKEN, ADMINS
from handlers import router
from admin_commands import admin_router
import db
import backup
from error_logging import setup_error_handler


def get_storage():
    """
    Get FSM storage based on environment.
    
    If REDIS_URL is set, uses RedisStorage for persistence across restarts.
    Falls back to MemoryStorage for local development.
    """
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            print(f"✅ Using Redis storage for FSM persistence")
            return RedisStorage.from_url(redis_url)
        except ImportError:
            print("⚠️ redis package not installed, falling back to MemoryStorage")
        except Exception as e:
            print(f"⚠️ Failed to connect to Redis: {e}, falling back to MemoryStorage")
    return MemoryStorage()


async def main():
    """Initialize and start the bot."""
    print("🚀 Starting Safar.uz Bot (MVP+ with Admin Features)...")
    print(f"📢 Configured admins: {ADMINS}")
    
    # Initialize database
    db.init_db()
    
    # Ensure backup directory exists
    backup.ensure_backup_dir()
    
    # Initialize bot with default parse mode
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    
    # Initialize dispatcher with pluggable storage
    # Uses Redis if REDIS_URL is set, otherwise MemoryStorage
    dp = Dispatcher(storage=get_storage())
    
    # Register global error handler ONCE on dispatcher
    # Uses aiogram 3.x native error handling (not middleware)
    setup_error_handler(dp, bot)
    
    # Register routers (admin_router first for command priority)
    dp.include_router(admin_router)
    dp.include_router(router)

    # Delete any pending updates (clean start)
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("✅ Bot is running! Press Ctrl+C to stop.")
    
    # Start backup scheduler as background task
    backup_task = asyncio.create_task(backup.backup_scheduler(bot))
    
    # Start polling
    try:
        await dp.start_polling(bot)
    finally:
        backup_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    # Handle Windows event loop policy
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped. Goodbye!")
