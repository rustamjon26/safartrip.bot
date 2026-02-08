"""
Automated daily database backup module.
"""
import asyncio
from datetime import datetime
from pathlib import Path

import db
from config import ADMINS

# Backup folder path
BACKUP_DIR = Path(__file__).parent / "backups"


def ensure_backup_dir():
    """Create backups directory if it doesn't exist."""
    BACKUP_DIR.mkdir(exist_ok=True)


def get_today_backup_path() -> Path:
    """Get backup file path for today."""
    today = datetime.now().strftime("%Y%m%d")
    return BACKUP_DIR / f"bot_{today}.db"


def backup_exists_today() -> bool:
    """Check if today's backup already exists."""
    return get_today_backup_path().exists()


async def perform_backup(bot=None) -> bool:
    """
    Perform database backup.
    
    Args:
        bot: Optional Bot instance for admin notification
        
    Returns:
        True if backup successful or already exists
    """
    ensure_backup_dir()
    
    # Check if already backed up today
    if backup_exists_today():
        print(f"ℹ️ Backup for today already exists: {get_today_backup_path().name}")
        return True
    
    backup_path = get_today_backup_path()
    
    # Perform backup using SQLite backup API
    success = db.backup_database(backup_path)
    
    if success:
        print(f"✅ Database backed up: {backup_path.name}")
        
        # Optionally notify admins
        if bot:
            for admin_id in ADMINS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=f"💾 Kunlik backup yaratildi: <code>{backup_path.name}</code>",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    print(f"⚠️ Failed to notify admin {admin_id}: {e}")
    else:
        print(f"❌ Backup failed: {backup_path.name}")
    
    return success


def _seconds_until_next_run(target_hour: int = 0, target_minute: int = 5) -> float:
    """
    Calculate seconds until next target time.
    
    Default: 00:05 local time (5 minutes after midnight).
    If target time has passed today, calculates time until tomorrow's target.
    """
    from datetime import timedelta
    
    now = datetime.now()
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # If target time already passed today, schedule for tomorrow
    if target <= now:
        target = target + timedelta(days=1)
    
    return (target - now).total_seconds()


async def backup_scheduler(bot=None):
    """
    Background task for daily backups at 00:05 local time.
    
    Features:
    - Stable timing (sleeps until exact target time, no drift)
    - Automatic cleanup of old backups (keeps last 7 days)
    - All operations wrapped in try/except to prevent crashes
    
    Args:
        bot: Bot instance for notifications
    """
    print("🔄 Backup scheduler started")
    
    # Perform initial backup on startup
    try:
        await perform_backup(bot)
        cleanup_old_backups(keep_days=7)
    except Exception as e:
        print(f"⚠️ Initial backup failed: {e}")
    
    while True:
        # Calculate sleep time until next 00:05
        sleep_seconds = _seconds_until_next_run(target_hour=0, target_minute=5)
        hours_until = sleep_seconds / 3600
        print(f"💤 Next backup in {hours_until:.1f} hours (at 00:05)")
        
        await asyncio.sleep(sleep_seconds)
        
        # Perform scheduled backup
        try:
            await perform_backup(bot)
            cleanup_old_backups(keep_days=7)
        except Exception as e:
            print(f"⚠️ Scheduled backup failed: {e}")



def cleanup_old_backups(keep_days: int = 7):
    """
    Remove backups older than keep_days.
    Called optionally to save disk space.
    """
    ensure_backup_dir()
    
    cutoff = datetime.now().timestamp() - (keep_days * 24 * 60 * 60)
    
    for backup_file in BACKUP_DIR.glob("bot_*.db"):
        if backup_file.stat().st_mtime < cutoff:
            try:
                backup_file.unlink()
                print(f"🗑️ Deleted old backup: {backup_file.name}")
            except Exception as e:
                print(f"⚠️ Failed to delete {backup_file.name}: {e}")
