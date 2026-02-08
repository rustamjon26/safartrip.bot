"""
Admin commands router for Telegram bot (Final Phase CMS).

Commands:
- /admin_help - Show admin commands list
- /admin_health - Database health check and CMS stats
- /admin_db_reset - Drop and recreate all DB tables (requires ALLOW_DB_RESET=true)
- /seed_listings - Seed sample listings

All messages use parse_mode=None to avoid HTML/Markdown parse errors.
"""
import logging
import os
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from config import ADMINS
import db_postgres as db_pg

logger = logging.getLogger(__name__)

# Create router
router = Router(name="admin_commands")

# Alias for main.py compatibility
admin_router = router

# Telegram message size limit (safe margin)
MAX_MESSAGE_LENGTH = 4000


# =============================================================================
# HELPERS
# =============================================================================

def is_admin(user_id: int) -> bool:
    """Check if user is an admin."""
    return user_id in ADMINS


def chunk_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split long text into chunks that fit Telegram message limits."""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    lines = text.split("\n")
    current_chunk = ""
    
    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks if chunks else [text[:max_length]]


def safe_get(d: dict, key: str, default=""):
    """Safely get value from dict."""
    try:
        val = d.get(key, default)
        return val if val is not None else default
    except Exception:
        return default


# =============================================================================
# /admin_help
# =============================================================================

@router.message(Command("admin_help"))
async def cmd_admin_help(message: Message):
    """Show admin commands list."""
    if not is_admin(message.from_user.id):
        return
    
    text = """ADMIN COMMANDS

/admin_help - Show this help
/admin_health - Database health check and CMS stats
/admin_db_reset - Drop and recreate all tables (requires ALLOW_DB_RESET=true)
/seed_listings - Seed sample listings for CMS browsing

USER COMMANDS
/browse - Start CMS browsing flow"""
    
    await message.answer(text, parse_mode=None)


# =============================================================================
# /admin_health
# =============================================================================

@admin_router.message(Command("admin_health"))
async def cmd_admin_health(message: Message):
    """Database health check and CMS statistics."""
    if not is_admin(message.from_user.id):
        return
    
    lines = ["🏥 ADMIN HEALTH CHECK", ""]
    
    # PostgreSQL connectivity
    try:
        pg_ok, pg_msg = await db_pg.healthcheck()
        status = "✅" if pg_ok else "❌"
        lines.append(f"PostgreSQL: {status} {pg_msg}")
    except Exception as e:
        lines.append(f"PostgreSQL: ❌ Error: {e}")
        await message.answer("\n".join(lines), parse_mode=None)
        return
    
    if not pg_ok:
        lines.append("")
        lines.append("⚠️ Database connection failed!")
        lines.append("Check DATABASE_URL and ensure PostgreSQL is running.")
        await message.answer("\n".join(lines), parse_mode=None)
        return
    
    # Connection pool status
    try:
        pool_status = db_pg.get_pool_status()
        if pool_status.get("status") == "initialized":
            lines.append("")
            lines.append("🔌 CONNECTION POOL")
            lines.append(f"  Size: {pool_status.get('size', 'N/A')}/{pool_status.get('max_size', 'N/A')}")
            lines.append(f"  Active: {pool_status.get('free_connections', 0)}")
            lines.append(f"  Idle: {pool_status.get('idle_connections', 0)}")
    except Exception as e:
        lines.append(f"  ⚠️ Pool status error: {e}")
    
    # Tables existence check
    try:
        tables = await db_pg.get_tables_list()
        lines.append("")
        lines.append("📊 DATABASE TABLES")
        if tables:
            for table in tables:
                icon = "✅" if table in ("listings", "bookings") else "📦"
                lines.append(f"  {icon} {table}")
        else:
            lines.append("  ⚠️ No tables found!")
    except Exception as e:
        lines.append(f"  ⚠️ Tables check error: {e}")
    
    # CMS Listings and Bookings counts
    try:
        listings_count = await db_pg.get_listings_count()
        bookings_count = await db_pg.get_bookings_count()
        bookings_by_status = await db_pg.get_bookings_by_status()
        listings_by_category = await db_pg.get_listings_by_category()
        
        lines.append("")
        lines.append("📋 CMS STATISTICS")
        lines.append(f"  Total listings (active): {listings_count}")
        
        if listings_by_category:
            category_icons = {"hotel": "🏨", "guide": "🧑‍💼", "taxi": "🚕", "place": "📍"}
            for category, count in listings_by_category.items():
                icon = category_icons.get(category, "📦")
                lines.append(f"    {icon} {category}: {count}")
        
        lines.append(f"  Total bookings: {bookings_count}")
        
        if bookings_by_status:
            status_line = ", ".join(f"{k}: {v}" for k, v in bookings_by_status.items())
            lines.append(f"    By status: {status_line}")
    except Exception as e:
        lines.append(f"  ⚠️ CMS stats error: {e}")
    
    # Warnings
    if listings_count == 0:
        lines.append("")
        lines.append("⚠️ No listings found!")
        lines.append("Create listings via /browse or admin listing wizard.")
    
    await message.answer("\n".join(lines), parse_mode=None)


# =============================================================================
# /admin_db_reset
# =============================================================================

@router.message(Command("admin_db_reset"))
async def cmd_admin_db_reset(message: Message):
    """Drop and recreate all database tables (DANGEROUS)."""
    if not is_admin(message.from_user.id):
        return
    
    # Check if allowed
    allow_reset = os.getenv("ALLOW_DB_RESET", "false").lower() == "true"
    
    if not allow_reset:
        await message.answer(
            "❌ Database reset is DISABLED.\n\n"
            "To enable, set environment variable:\n"
            "ALLOW_DB_RESET=true\n\n"
            "⚠️ WARNING: This will DELETE ALL DATA!\n\n"
            "In Railway, add this to your environment variables.",
            parse_mode=None
        )
        return
    
    # Actually perform the reset
    await message.answer("🔄 Resetting database...", parse_mode=None)
    
    try:
        success = await db_pg.reset_schema()
        
        if success:
            await message.answer(
                "✅ Database reset complete!\n\n"
                "All tables have been dropped and recreated.\n"
                "The database is now empty.",
                parse_mode=None
            )
        else:
            await message.answer(
                "❌ Database reset failed!\n\n"
                "Check logs for details.",
                parse_mode=None
            )
    except Exception as e:
        logger.error(f"Error in admin_db_reset: {e}")
        await message.answer(f"❌ Reset error: {e}", parse_mode=None)


# =============================================================================
# /seed_listings
# =============================================================================

@router.message(Command("seed_listings"))
async def cmd_seed_listings(message: Message):
    """Seed sample listings into database for CMS browsing."""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer("🔄 Seeding listings...", parse_mode=None)
    
    try:
        # Check if seed_sample_listings function exists
        if not hasattr(db_pg, 'seed_sample_listings'):
            await message.answer(
                "❌ Seed function not available.\n\n"
                "Create listings manually via the admin wizard.",
                parse_mode=None
            )
            return
        
        count = await db_pg.seed_sample_listings()
        
        # Get actual count from DB
        listings_count = await db_pg.get_listings_count()
        
        text = (
            f"✅ Seeding completed!\n\n"
            f"Inserted: {count}\n"
            f"Total active listings: {listings_count}\n\n"
            f"💡 Users can now browse listings via /browse command"
        )
        
        await message.answer(text, parse_mode=None)
        
    except Exception as e:
        logger.error(f"Error seeding listings: {e}")
        await message.answer(f"❌ Seeding failed: {e}", parse_mode=None)
