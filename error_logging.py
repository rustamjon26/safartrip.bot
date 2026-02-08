"""
Global error handler for aiogram 3.x.
Uses dp.errors.register() - the recommended approach for aiogram 3.x.
Catches exceptions and forwards error reports to admins with throttling.

Key safety features:
- Uses aiogram's native error handler (not middleware) to avoid recursion
- Recursion guard via contextvars
- All admin notification wrapped in try/except (never re-raises)
- Throttling: same error signature at most once per 30 seconds
- Traceback truncated to 3500 chars for Telegram limits
"""
import traceback
import time
import hashlib
import contextvars
from typing import Any

from aiogram import Bot, Router
from aiogram.types import Update, ErrorEvent

from config import ADMINS

# Recursion guard: prevents logging the same error twice in nested calls
_error_handling_in_progress: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_error_handling_in_progress", default=False
)

# Throttling: store (error_hash -> last_sent_timestamp)
_error_cache: dict[str, float] = {}
THROTTLE_SECONDS = 30
MAX_TRACEBACK_LENGTH = 3500  # Safe margin under Telegram's 4096 limit


def _get_error_hash(exc: BaseException, tb_str: str) -> str:
    """
    Generate a hash for error deduplication.
    Signature = exception_type + message (first 100 chars) + top stack frame file:line
    """
    try:
        exc_type = type(exc).__name__
        exc_msg = str(exc)[:100]
        
        # Extract top stack frame info from traceback
        top_frame = ""
        tb_lines = tb_str.strip().split("\n")
        for line in reversed(tb_lines):
            # Look for lines like: File "...", line X, in ...
            if 'File "' in line and ", line " in line:
                top_frame = line.strip()[:100]
                break
        
        sig = f"{exc_type}:{exc_msg}:{top_frame}"
        return hashlib.md5(sig.encode()).hexdigest()[:16]
    except Exception:
        # Fallback: just use exception type
        return hashlib.md5(type(exc).__name__.encode()).hexdigest()[:16]


def _should_send(error_hash: str) -> bool:
    """Check if we should send this error (throttle check)."""
    now = time.time()
    last_sent = _error_cache.get(error_hash, 0)
    
    if now - last_sent < THROTTLE_SECONDS:
        return False
    
    _error_cache[error_hash] = now
    # Cleanup old entries to prevent memory leak (keep last 100)
    if len(_error_cache) > 100:
        oldest_keys = sorted(_error_cache, key=_error_cache.get)[:50]
        for k in oldest_keys:
            _error_cache.pop(k, None)
    
    return True


def _extract_user_info(update: Update) -> dict[str, Any]:
    """Safely extract user/chat info from update."""
    info = {
        "update_type": "unknown",
        "user_id": None,
        "username": None,
        "chat_id": None,
    }
    
    try:
        if update.message:
            info["update_type"] = "message"
            if update.message.from_user:
                info["user_id"] = update.message.from_user.id
                info["username"] = update.message.from_user.username
            if update.message.chat:
                info["chat_id"] = update.message.chat.id
        elif update.callback_query:
            info["update_type"] = "callback_query"
            if update.callback_query.from_user:
                info["user_id"] = update.callback_query.from_user.id
                info["username"] = update.callback_query.from_user.username
            if update.callback_query.message:
                info["chat_id"] = update.callback_query.message.chat.id
        elif update.inline_query:
            info["update_type"] = "inline_query"
            if update.inline_query.from_user:
                info["user_id"] = update.inline_query.from_user.id
                info["username"] = update.inline_query.from_user.username
        elif update.edited_message:
            info["update_type"] = "edited_message"
            if update.edited_message.from_user:
                info["user_id"] = update.edited_message.from_user.id
                info["username"] = update.edited_message.from_user.username
            if update.edited_message.chat:
                info["chat_id"] = update.edited_message.chat.id
    except Exception:
        pass  # Return defaults if extraction fails
    
    return info


def _format_error_report(exc: BaseException, update: Update | None, tb_str: str) -> str:
    """Format error report for admin notification (safe, never raises)."""
    try:
        # Truncate traceback
        if len(tb_str) > MAX_TRACEBACK_LENGTH:
            tb_str = tb_str[:MAX_TRACEBACK_LENGTH] + "\n... [truncated]"
        
        # Escape HTML in traceback
        tb_str = (
            tb_str
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        
        # Get user info
        if update:
            info = _extract_user_info(update)
        else:
            info = {"update_type": "N/A", "user_id": "N/A", "username": None, "chat_id": "N/A"}
        
        exc_msg = str(exc)[:300]
        # Escape HTML in exception message
        exc_msg = exc_msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        report = (
            f"⚠️ <b>BOT ERROR</b>\n\n"
            f"<b>Type:</b> {type(exc).__name__}\n"
            f"<b>Message:</b> {exc_msg}\n\n"
            f"<b>Update:</b> {info['update_type']}\n"
            f"<b>User ID:</b> {info['user_id']}\n"
            f"<b>Username:</b> @{info['username'] or 'N/A'}\n"
            f"<b>Chat ID:</b> {info['chat_id']}\n\n"
            f"<b>Traceback:</b>\n<pre>{tb_str}</pre>"
        )
        
        # Final safety check on length
        if len(report) > 4000:
            report = report[:3900] + "\n... [message truncated]</pre>"
        
        return report
    except Exception:
        # Ultimate fallback
        return f"⚠️ <b>BOT ERROR</b>\n\n{type(exc).__name__}: {str(exc)[:200]}"


async def error_handler(event: ErrorEvent, bot: Bot) -> bool:
    """
    Global error handler for aiogram 3.x.
    Registered via router.errors() or dp.errors.register().
    
    Returns True to indicate error was handled (suppress further propagation).
    """
    # Recursion guard: if we're already handling an error, skip
    if _error_handling_in_progress.get():
        print("⚠️ Error handler recursion detected, skipping")
        return True
    
    # Set recursion guard
    token = _error_handling_in_progress.set(True)
    
    try:
        exc = event.exception
        update = event.update
        
        # Get traceback string safely
        try:
            tb_str = traceback.format_exception(type(exc), exc, exc.__traceback__)
            tb_str = "".join(tb_str)
        except Exception:
            tb_str = f"{type(exc).__name__}: {exc}"
        
        # Always log to console
        print(f"❌ Error processing update: {type(exc).__name__}: {exc}")
        print(tb_str)
        
        # Check throttle
        error_hash = _get_error_hash(exc, tb_str)
        if not _should_send(error_hash):
            print(f"⏳ Error throttled (hash: {error_hash})")
            return True
        
        # Format report
        report = _format_error_report(exc, update, tb_str)
        
        # Send to admins - FULLY WRAPPED, NEVER RAISES
        for admin_id in ADMINS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=report,
                    parse_mode="HTML",
                )
            except Exception as send_err:
                # Swallow ALL errors from sending - never re-raise
                print(f"⚠️ Failed to send error to admin {admin_id}: {send_err}")
        
        return True  # Error handled, don't propagate
        
    except Exception as handler_err:
        # If error handler itself fails, just log and don't crash
        print(f"❌ Error handler failed: {handler_err}")
        return True
        
    finally:
        # Reset recursion guard
        _error_handling_in_progress.reset(token)


def setup_error_handler(router: Router, bot: Bot) -> None:
    """
    Register the error handler on a router.
    Call this once in main.py with your dispatcher or main router.
    """
    @router.errors()
    async def _error_wrapper(event: ErrorEvent) -> bool:
        return await error_handler(event, bot)
