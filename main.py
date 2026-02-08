"""
Safar.uz Telegram Bot - Main Entry Point (Production Hardened)

Features:
- PostgreSQL persistence (partners + bookings)
- SQLite persistence (users + legacy orders)
- Multi-language support (UZ/RU/EN)
- Partner-based booking flow (Guide, Taxi)
- Admin commands (/orders, /order, /find, /filter, /export, /health, /partners)
- Rate limiting for anti-spam
- Automated daily database backups
- Global error logging with admin notifications
- Graceful shutdown handling
"""
import asyncio
import os
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

# Import config first to validate environment variables
from config import BOT_TOKEN, ADMINS, get_startup_info
from handlers import router
from admin_commands import admin_router
from partner_handlers import partner_router
from booking_handlers import booking_router
import db
import db_postgres as db_pg
import backup
from error_logging import setup_error_handler
from logging_config import setup_logging, get_logger

# Initialize logging
setup_logging()
logger = get_logger(__name__)

# Track bot start time for /health command
BOT_START_TIME: float = 0.0


def get_storage():
    """
    Get FSM storage based on environment.
    
    If REDIS_URL is set, uses RedisStorage for persistence across restarts.
    Falls back to MemoryStorage for local development.
    
    WARNING: MemoryStorage loses all FSM state on restart!
    """
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            logger.info("Using Redis storage for FSM persistence")
            return RedisStorage.from_url(redis_url)
        except ImportError:
            logger.warning("redis package not installed, falling back to MemoryStorage")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}, falling back to MemoryStorage")
    
    logger.warning("Using MemoryStorage - FSM state will be lost on restart!")
    return MemoryStorage()


async def healthcheck_db() -> tuple[bool, str]:
    """Check database connectivity. Returns (ok, message)."""
    try:
        count = await asyncio.to_thread(db.get_orders_count)
        return True, f"SQLite OK ({count} orders)"
    except Exception as e:
        return False, f"SQLite Error: {e}"


async def healthcheck_postgres() -> tuple[bool, str]:
    """Check PostgreSQL connectivity."""
    return await db_pg.healthcheck()


async def main():
    """Initialize and start the bot with production hardening."""
    global BOT_START_TIME
    import time
    BOT_START_TIME = time.time()
    
    # Startup banner
    startup_info = get_startup_info()
    print("=" * 60)
    print(f"🚀 Safar.uz Bot Starting | {startup_info}")
    print(f"📢 Admins: {ADMINS}")
    print("=" * 60)
    logger.info(f"Bot starting: {startup_info}", extra={"admins": ADMINS})
    
    # Initialize SQLite database (legacy)
    if not db.init_db():
        logger.error("FATAL: SQLite database initialization failed!")
        sys.exit(1)
    
    db_ok, db_msg = await healthcheck_db()
    if db_ok:
        logger.info(f"SQLite health check: {db_msg}")
    else:
        logger.warning(f"SQLite health check failed: {db_msg}")
    
    # Initialize PostgreSQL database (REQUIRED for partner features)
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        logger.info("Initializing PostgreSQL connection pool...")
        pg_ok = await db_pg.init_db_pool()
        if pg_ok:
            pg_health_ok, pg_health_msg = await healthcheck_postgres()
            logger.info(f"PostgreSQL health check: {pg_health_msg}")
            print(f"✅ PostgreSQL: {pg_health_msg}")
        else:
            logger.error("FATAL: PostgreSQL pool initialization failed!")
            logger.error("Check DATABASE_URL and network connectivity.")
            print("❌ PostgreSQL initialization FAILED - exiting")
            sys.exit(1)
    else:
        logger.warning("DATABASE_URL not set - partner booking features DISABLED")
        print("⚠️ DATABASE_URL not set - partner features disabled")
    
    # Ensure backup directory exists
    backup.ensure_backup_dir()
    
    # Initialize bot with default parse mode
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    
    # Initialize dispatcher with pluggable storage
    dp = Dispatcher(storage=get_storage())
    
    # Register global error handler
    setup_error_handler(dp, bot)
    
    # Register routers (order matters for priority)
    dp.include_router(admin_router)      # Admin commands first
    dp.include_router(partner_router)    # Partner /connect and callbacks
    dp.include_router(booking_router)    # Guide/Taxi booking flows
    dp.include_router(router)            # Legacy handlers

    # Delete any pending updates (clean start)
    await bot.delete_webhook(drop_pending_updates=True)
    
    logger.info("Bot initialized, starting polling...")
    print("✅ Bot is running! Press Ctrl+C to stop.")
    
    # Start backup scheduler as background task
    backup_task = asyncio.create_task(backup.backup_scheduler(bot))
    
    # Start polling with graceful shutdown
    try:
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        logger.info("Polling cancelled")
    except Exception as e:
        logger.error(f"Polling error: {e}", exc_info=True)
        raise
    finally:
        logger.info("Shutting down...")
        backup_task.cancel()
        with suppress(asyncio.CancelledError):
            await backup_task
        
        # Close PostgreSQL pool
        await db_pg.close_db_pool()
        
        await bot.session.close()
        logger.info("Bot stopped gracefully")
        print("👋 Bot stopped. Goodbye!")


if __name__ == "__main__":
    # Handle Windows event loop policy
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Interrupted by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
