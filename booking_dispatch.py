"""
booking_dispatch.py - Booking Dispatch + Partner Callbacks + Timeout (Final Phase)

Features:
- Dispatch booking to listing's telegram_admin_id
- Partner accept/reject callbacks
- User notifications
- Background timeout checker task
"""

import asyncio
import html
import logging
from typing import Optional

from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from aiogram.filters import BaseFilter
from config import ADMINS
import db_postgres as db

logger = logging.getLogger(__name__)

booking_dispatch_router = Router(name="booking_dispatch")


# =============================================================================
# Router-Level Admin Guard
# =============================================================================

class AdminFilter(BaseFilter):
    """Block non-admin users from this router."""
    async def __call__(self, event) -> bool:
        user = getattr(event, "from_user", None)
        if user and user.id in ADMINS:
            return True
        return False


booking_dispatch_router.message.filter(AdminFilter())
booking_dispatch_router.callback_query.filter(AdminFilter())

# Background task reference
_timeout_task: Optional[asyncio.Task] = None
_bot_ref: Optional[Bot] = None


# =============================================================================
# HTML Safety
# =============================================================================

def h(text) -> str:
    """HTML-escape any value."""
    if text is None:
        return ""
    return html.escape(str(text), quote=False)


async def safe_send_html(bot: Bot, chat_id: int, text: str, reply_markup=None) -> Optional[int]:
    """Send HTML message with fallback. Returns message_id or None."""
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return msg.message_id
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            try:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=None,
                    reply_markup=reply_markup,
                )
                return msg.message_id
            except:
                pass
        logger.error(f"Failed to send message to {chat_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error sending to {chat_id}: {e}")
        return None


# =============================================================================
# Dispatch Booking to Partner Admin
# =============================================================================

async def dispatch_booking_to_admin(bot: Bot, booking_id: str) -> bool:
    """
    Send booking details to the listing's admin for accept/reject.
    
    Returns:
        True if sent successfully
    """
    booking = await db.get_booking(booking_id)
    if not booking:
        logger.error(f"Booking {booking_id} not found for dispatch")
        return False
    
    admin_id = booking.get("telegram_admin_id")
    if not admin_id:
        logger.error(f"No admin ID for booking {booking_id}")
        return False
    
    payload = booking.get("payload", {})
    
    # Build message
    lines = [
        "📬 <b>Yangi bron!</b>",
        "",
        f"📌 {h(booking.get('listing_title', 'Listing'))}",
    ]
    
    if booking.get("price_from"):
        lines.append(f"💰 {booking['price_from']:,} {booking.get('currency', 'UZS')}")
    
    # Guest info: backward compatible (old bookings have 'name', new have 'guest_names')
    guest_names = payload.get("guest_names")
    if guest_names and isinstance(guest_names, list):
        guest_count = payload.get("guest_count", len(guest_names))
        names_str = ", ".join(h(n) for n in guest_names)
        lines.append("")
        lines.append(f"👥 Mehmonlar ({guest_count}): {names_str}")
    else:
        lines.append("")
        lines.append(f"👤 Ism: {h(payload.get('name', '—'))}")
    
    lines.extend([
        f"📱 Telefon: {h(payload.get('phone', '—'))}",
        f"📅 Sana: {h(payload.get('date', '—'))}",
    ])
    
    if payload.get("note"):
        lines.append(f"📝 Izoh: {h(payload['note'])}")
    
    lines.extend([
        "",
        "⏳ 5 daqiqa ichida javob bering!",
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"bk:ok:{booking_id[:8]}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"bk:no:{booking_id[:8]}"),
        ]
    ])
    
    message_id = await safe_send_html(bot, admin_id, "\n".join(lines), keyboard)
    
    if message_id:
        # Update status to 'sent'
        await db.update_booking_status(booking_id, "sent")
        logger.info(f"Booking {booking_id[:8]} dispatched to admin {admin_id}")
        return True
    
    return False


# =============================================================================
# Partner Accept/Reject Callbacks
# =============================================================================

@booking_dispatch_router.callback_query(F.data.startswith("bk:ok:"))
async def accept_booking(callback: CallbackQuery, bot: Bot):
    """Partner accepts booking."""
    await callback.answer()
    
    bid_short = callback.data.split(":")[2]
    
    # Find full booking
    booking = await find_booking_by_short_id(bid_short)
    if not booking:
        await callback.answer("Bron topilmadi", show_alert=True)
        return
    
    # Check if already processed
    if booking["status"] not in ("new", "sent"):
        status_text = {
            "accepted": "allaqachon qabul qilingan",
            "rejected": "allaqachon rad etilgan",
            "timeout": "vaqti o'tgan",
        }.get(booking["status"], booking["status"])
        
        await callback.answer(f"Bu bron {status_text}", show_alert=True)
        return
    
    # Update status
    success = await db.update_booking_status(booking["id"], "accepted")
    
    if success:
        # Notify partner
        try:
            await callback.message.edit_text(
                callback.message.text + "\n\n✅ <b>Qabul qilindi!</b>",
                parse_mode="HTML",
            )
        except:
            pass
        
        # Notify user
        user_id = booking["user_telegram_id"]
        await safe_send_html(
            bot,
            user_id,
            f"✅ <b>Bron tasdiqlandi!</b>\n\n"
            f"📌 {h(booking.get('listing_title', ''))}\n\n"
            f"Tez orada siz bilan bog'lanishadi.",
        )
        
        logger.info(f"Booking {booking['id'][:8]} accepted")
    else:
        await callback.answer("Xatolik yuz berdi", show_alert=True)


@booking_dispatch_router.callback_query(F.data.startswith("bk:no:"))
async def reject_booking(callback: CallbackQuery, bot: Bot):
    """Partner rejects booking."""
    await callback.answer()
    
    bid_short = callback.data.split(":")[2]
    
    booking = await find_booking_by_short_id(bid_short)
    if not booking:
        await callback.answer("Bron topilmadi", show_alert=True)
        return
    
    if booking["status"] not in ("new", "sent"):
        await callback.answer("Bu bron allaqachon jarayonda", show_alert=True)
        return
    
    success = await db.update_booking_status(booking["id"], "rejected")
    
    if success:
        # Notify partner
        try:
            await callback.message.edit_text(
                callback.message.text + "\n\n❌ <b>Rad etildi</b>",
                parse_mode="HTML",
            )
        except:
            pass
        
        # Notify user
        user_id = booking["user_telegram_id"]
        await safe_send_html(
            bot,
            user_id,
            f"❌ <b>Bron rad etildi</b>\n\n"
            f"📌 {h(booking.get('listing_title', ''))}\n\n"
            f"Boshqa variantlarni ko'rish: /browse",
        )
        
        logger.info(f"Booking {booking['id'][:8]} rejected")
    else:
        await callback.answer("Xatolik yuz berdi", show_alert=True)


async def find_booking_by_short_id(bid_short: str) -> Optional[dict]:
    """Find booking by short ID prefix."""
    if not db._pool:
        return None
    
    try:
        async with db._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT b.id, b.listing_id, b.user_telegram_id, b.payload,
                       b.status, b.expires_at, b.created_at,
                       l.title as listing_title, l.category, l.telegram_admin_id,
                       l.price_from, l.currency
                FROM bookings b
                JOIN listings l ON b.listing_id = l.id
                WHERE b.id::text LIKE $1
                """,
                bid_short + "%",
            )
            if row:
                return db._row_to_booking(row)
    except Exception as e:
        logger.error(f"Error finding booking: {e}")
    
    return None


# =============================================================================
# Timeout Checker Background Task
# =============================================================================

async def timeout_checker_loop(bot: Bot):
    """
    Background task that checks for expired bookings every 30 seconds.
    Uses atomic UPDATE RETURNING to be safe with multiple workers.
    """
    global _bot_ref
    _bot_ref = bot
    
    logger.info("Timeout checker started")
    
    while True:
        try:
            await asyncio.sleep(30)
            
            expired = await db.fetch_expired_bookings()
            
            for booking in expired:
                user_id = booking["user_telegram_id"]
                title = booking.get("listing_title", "")
                
                await safe_send_html(
                    bot,
                    user_id,
                    f"⏰ <b>Vaqt tugadi</b>\n\n"
                    f"📌 {h(title)}\n\n"
                    f"Javob bo'lmadi, keyinroq urinib ko'ring.\n"
                    f"/browse - Boshqa variantlar",
                )
                
                logger.info(f"Booking {booking['id'][:8]} timed out")
                
        except asyncio.CancelledError:
            logger.info("Timeout checker cancelled")
            break
        except Exception as e:
            logger.error(f"Error in timeout checker: {e}")
            await asyncio.sleep(5)


def start_timeout_checker(bot: Bot) -> asyncio.Task:
    """Start the timeout checker background task."""
    global _timeout_task
    _timeout_task = asyncio.create_task(timeout_checker_loop(bot))
    return _timeout_task


async def stop_timeout_checker():
    """Stop the timeout checker."""
    global _timeout_task
    if _timeout_task:
        _timeout_task.cancel()
        try:
            await _timeout_task
        except asyncio.CancelledError:
            pass
        _timeout_task = None
        logger.info("Timeout checker stopped")
