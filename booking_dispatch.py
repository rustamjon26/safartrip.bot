"""
booking_dispatch.py - Marketplace Booking Dispatch (Owner + Admin)

Features:
- Dispatch booking to listing OWNER (partner) for accept/reject
- Send monitoring copy to ADMINS
- Owner-only accept/reject security (atomic DB ops)
- Background timeout checker (5-min, notifies admins with partner contact)
"""

import asyncio
import html
import logging
from typing import Optional

from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from config import ADMINS
import db_postgres as db

logger = logging.getLogger(__name__)

booking_dispatch_router = Router(name="booking_dispatch")

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
            except Exception:
                pass
        logger.error(f"Failed to send message to {chat_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error sending to {chat_id}: {e}")
        return None


# =============================================================================
# Build Booking Summary Text
# =============================================================================

def _build_booking_text(booking: dict, prefix: str = "") -> str:
    """Build booking summary text used for both owner and admin messages."""
    payload = booking.get("payload", {})

    lines = [prefix] if prefix else []
    lines.append(f"📌 {h(booking.get('listing_title', 'Listing'))}")

    if booking.get("price_from"):
        lines.append(f"💰 {booking['price_from']:,} {booking.get('currency', 'UZS')}")

    # Guest info
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

    return "\n".join(lines)


def _get_owner_id(booking: dict) -> int:
    """Safely extract owner_user_id with fallback, avoiding 0/None."""
    owner = booking.get("owner_user_id") or booking.get("telegram_admin_id")
    return int(owner) if owner else 0


# =============================================================================
# Dispatch to Owner (Partner)
# =============================================================================

async def dispatch_booking_to_owner(bot: Bot, booking_id: str) -> bool:
    """
    Send booking details to the listing OWNER for accept/reject.
    Uses mark_booking_dispatched() to atomically set status, dispatched_at, and partner_message_id.
    On failure (owner unreachable), immediately alerts admins.
    """
    booking = await db.get_booking(booking_id)
    if not booking:
        logger.error(f"Booking {booking_id} not found for owner dispatch")
        return False

    owner_id = _get_owner_id(booking)
    if not owner_id:
        logger.error(f"No owner for booking {booking_id}")
        return False

    text = _build_booking_text(
        booking,
        prefix="📬 <b>Sizga zakaz keldi!</b>\nQabul qilasizmi?\n",
    )
    text += "\n\n⏳ 5 daqiqa ichida javob bering!"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"bk:ok:{booking_id[:8]}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"bk:no:{booking_id[:8]}"),
        ]
    ])

    message_id = await safe_send_html(bot, owner_id, text, keyboard)

    if message_id:
        # Atomic: set status=sent, dispatched_at=NOW(), partner_message_id
        await db.mark_booking_dispatched(booking_id, message_id)
        logger.info(f"Booking {booking_id[:8]} dispatched to owner {owner_id}")
        return True

    # --- Owner unreachable: bot blocked or never started ---
    logger.warning(f"Owner {owner_id} unreachable for booking {booking_id[:8]}")

    # Try to get owner contact info for admin alert
    owner_info = await db.get_user_by_telegram_id(owner_id)
    owner_phone = owner_info.get("phone", "—") if owner_info else "—"
    owner_name = ""
    if owner_info:
        owner_name = f"{owner_info.get('first_name', '')} {owner_info.get('last_name', '')}".strip()
    owner_name = owner_name or "—"

    for admin_id in ADMINS:
        await safe_send_html(
            bot,
            admin_id,
            f"🚫 <b>Partner topilmadi / bot bloklangan!</b>\n\n"
            f"📌 {h(booking.get('listing_title', ''))}\n"
            f"👤 Partner: {h(owner_name)}\n"
            f"🆔 TG ID: <code>{owner_id}</code>\n"
            f"📱 Telefon: {h(owner_phone)}\n\n"
            f"📞 <b>Iltimos, partnerga telefon qiling!</b>",
        )

    return False


# =============================================================================
# Dispatch Monitoring Copy to Admins
# =============================================================================

async def dispatch_booking_to_admins(bot: Bot, booking_id: str, status: str = "PENDING_PARTNER") -> None:
    """Send a monitoring copy of the booking to all ADMINS (no action buttons)."""
    booking = await db.get_booking(booking_id)
    if not booking:
        return

    owner_id = _get_owner_id(booking)
    text = _build_booking_text(
        booking,
        prefix=f"📋 <b>Yangi bron (monitoring)</b>\n🔖 Status: {h(status)}\n👤 Partner: <code>{owner_id}</code>\n",
    )

    for admin_id in ADMINS:
        # Don't duplicate if admin IS the owner — they already got the actionable msg
        if owner_id and admin_id == owner_id:
            continue
        await safe_send_html(bot, admin_id, text)


# =============================================================================
# Owner Accept/Reject Callbacks (NO AdminFilter — owner can be non-admin)
# =============================================================================

@booking_dispatch_router.callback_query(F.data.startswith("bk:ok:"))
async def accept_booking(callback: CallbackQuery, bot: Bot):
    """Owner accepts booking. Uses atomic DB update to prevent race conditions."""
    bid_short = callback.data.split(":")[2]
    booking = await find_booking_by_short_id(bid_short)

    if not booking:
        await callback.answer("Bron topilmadi", show_alert=True)
        return

    # Security: only the owner can accept
    owner_id = _get_owner_id(booking)
    if not owner_id or callback.from_user.id != owner_id:
        await callback.answer("⛔ Faqat egasi qabul qilishi mumkin", show_alert=True)
        return

    # Check if already processed (show informative message)
    if booking["status"] not in ("pending_partner", "sent"):
        status_text = {
            "accepted": "allaqachon qabul qilingan",
            "rejected": "allaqachon rad etilgan",
            "timeout": "vaqti o'tgan",
        }.get(booking["status"], booking["status"])
        await callback.answer(f"Bu bron {status_text}", show_alert=True)
        return

    # Atomic accept: WHERE id=? AND status IN (...) AND owner_user_id=?
    # Returns False if another handler already changed the status (race condition)
    success = await db.accept_booking_atomic(booking["id"], owner_id)

    if not success:
        await callback.answer("Bu bron allaqachon jarayonda", show_alert=True)
        return

    await callback.answer("✅ Qabul qilindi!")

    # Edit partner message — remove buttons
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ <b>Qabul qilindi!</b>",
            parse_mode="HTML",
        )
    except Exception:
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

    # Notify admins
    for admin_id in ADMINS:
        if owner_id and admin_id == owner_id:
            continue
        await safe_send_html(
            bot,
            admin_id,
            f"✅ Bron <b>qabul qilindi</b>\n"
            f"📌 {h(booking.get('listing_title', ''))}\n"
            f"👤 Partner: <code>{owner_id}</code>",
        )

    logger.info(f"Booking {booking['id'][:8]} accepted by owner {owner_id}")


@booking_dispatch_router.callback_query(F.data.startswith("bk:no:"))
async def reject_booking(callback: CallbackQuery, bot: Bot):
    """Owner rejects booking. Uses atomic DB update to prevent race conditions."""
    bid_short = callback.data.split(":")[2]
    booking = await find_booking_by_short_id(bid_short)

    if not booking:
        await callback.answer("Bron topilmadi", show_alert=True)
        return

    # Security: only the owner can reject
    owner_id = _get_owner_id(booking)
    if not owner_id or callback.from_user.id != owner_id:
        await callback.answer("⛔ Faqat egasi rad etishi mumkin", show_alert=True)
        return

    if booking["status"] not in ("pending_partner", "sent"):
        await callback.answer("Bu bron allaqachon jarayonda", show_alert=True)
        return

    # Atomic reject
    success = await db.reject_booking_atomic(booking["id"], owner_id)

    if not success:
        await callback.answer("Bu bron allaqachon jarayonda", show_alert=True)
        return

    await callback.answer("❌ Rad etildi")

    # Edit partner message — remove buttons
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ <b>Rad etildi</b>",
            parse_mode="HTML",
        )
    except Exception:
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

    # Notify admins
    for admin_id in ADMINS:
        if owner_id and admin_id == owner_id:
            continue
        await safe_send_html(
            bot,
            admin_id,
            f"❌ Bron <b>rad etildi</b>\n"
            f"📌 {h(booking.get('listing_title', ''))}\n"
            f"👤 Partner: <code>{owner_id}</code>",
        )

    logger.info(f"Booking {booking['id'][:8]} rejected by owner {owner_id}")


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
                       b.owner_user_id, b.partner_message_id,
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
    Background task: every 30s find pending_partner/sent bookings > 5 min old.
    Mark as timeout atomically (CTE), notify user + admins with partner contact.
    The CTE ensures each booking times out exactly once even with multiple workers.
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
                owner_id = booking.get("owner_user_id", 0)
                owner_phone = booking.get("owner_phone") or "—"
                owner_name = f"{booking.get('owner_first_name', '')} {booking.get('owner_last_name', '')}".strip() or "—"

                # Notify user
                await safe_send_html(
                    bot,
                    user_id,
                    f"⏰ <b>Vaqt tugadi</b>\n\n"
                    f"📌 {h(title)}\n\n"
                    f"Javob bo'lmadi, keyinroq urinib ko'ring.\n"
                    f"/browse - Boshqa variantlar",
                )

                # Notify admins: partner didn't respond — call them
                for admin_id in ADMINS:
                    await safe_send_html(
                        bot,
                        admin_id,
                        f"⚠️ <b>Partner javob bermadi!</b>\n\n"
                        f"📌 {h(title)}\n"
                        f"👤 Partner: {h(owner_name)}\n"
                        f"🆔 TG ID: <code>{owner_id}</code>\n"
                        f"📱 Telefon: {h(owner_phone)}\n\n"
                        f"📞 <b>Iltimos, partnerga telefon qiling!</b>",
                    )

                logger.info(f"Booking {booking['id'][:8]} timed out, owner={owner_id}")

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
