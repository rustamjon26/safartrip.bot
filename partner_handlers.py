"""
Partner-related handlers: /connect command, partner accept/reject callbacks.
"""
import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandObject

import db_postgres as db_pg
from config import ADMINS

logger = logging.getLogger(__name__)

partner_router = Router()


# =============================================================================
# /connect <code> - Partner connection
# =============================================================================

@partner_router.message(Command("connect"))
async def cmd_connect(message: Message, command: CommandObject):
    """
    Partner connects their Telegram account using their connect_code.
    Usage: /connect <code>
    """
    user_id = message.from_user.id if message.from_user else 0
    
    if not command.args or not command.args.strip():
        await message.answer(
            "❌ <b>Foydalanish:</b> /connect &lt;kod&gt;\n\n"
            "Misol: <code>/connect ABC123</code>\n\n"
            "Kodni admin sizga beradi.",
            parse_mode="HTML"
        )
        return
    
    connect_code = command.args.strip()
    
    # Try to connect
    partner = await db_pg.connect_partner(connect_code, user_id)
    
    if not partner:
        await message.answer(
            "❌ <b>Noto'g'ri kod</b>\n\n"
            "Bu kod topilmadi yoki faol emas. "
            "Iltimos, admin bilan bog'laning.",
            parse_mode="HTML"
        )
        return
    
    # Success
    type_display = {
        "guide": "🧑‍💼 Gid",
        "taxi": "🚕 Taksi",
        "hotel": "🏨 Mehmonxona",
    }.get(partner["type"], partner["type"])
    
    await message.answer(
        f"✅ <b>Muvaffaqiyatli ulandi!</b>\n\n"
        f"👤 <b>Ism:</b> {partner['display_name']}\n"
        f"🏷 <b>Turi:</b> {type_display}\n\n"
        f"Endi siz buyurtmalar olishingiz mumkin!",
        parse_mode="HTML"
    )
    logger.info(f"Partner connected: {partner['display_name']} (code={connect_code}, tg_id={user_id})")


# =============================================================================
# Booking accept/reject callbacks (for partners)
# =============================================================================

@partner_router.callback_query(F.data.startswith("bk:"))
async def handle_booking_action(callback: CallbackQuery, bot: Bot):
    """
    Handle partner accept/reject booking callback.
    Format: bk:ok:<booking_id> or bk:no:<booking_id>
    """
    await callback.answer()
    
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        return
    
    action = parts[1]  # "ok" or "no"
    booking_id = parts[2]
    
    # Get booking - try listing-based first, then legacy
    booking = await db_pg.get_booking_with_listing(booking_id)
    if not booking:
        booking = await db_pg.get_booking(booking_id)
    
    if not booking:
        await callback.message.edit_text(
            "❌ Buyurtma topilmadi.",
            reply_markup=None
        )
        return
    
    # Check if already handled or timed out
    if booking["status"] in ("accepted", "rejected", "timeout"):
        status_map = {
            "accepted": "✅ Qabul qilingan",
            "rejected": "❌ Rad etilgan", 
            "timeout": "⏰ Vaqt tugagan",
        }
        status_text = status_map.get(booking["status"], booking["status"])
        await callback.message.edit_text(
            f"⚠️ Bu buyurtma allaqachon ko'rib chiqilgan.\n\nHolat: {status_text}",
            reply_markup=None
        )
        return
    
    # Update status
    new_status = "accepted" if action == "ok" else "rejected"
    success = await db_pg.set_booking_status(booking_id, new_status)
    
    if not success:
        await callback.message.edit_text(
            "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
            reply_markup=None
        )
        return
    
    # Notify partner (current message)
    status_emoji = "✅" if action == "ok" else "❌"
    status_text = "Qabul qilindi" if action == "ok" else "Rad etildi"
    await callback.message.edit_text(
        f"{status_emoji} <b>Buyurtma {status_text}</b>\n\n"
        f"Buyurtma ID: <code>{booking_id[:8]}...</code>",
        parse_mode="HTML",
        reply_markup=None
    )
    
    # Notify user
    user_telegram_id = booking["user_telegram_id"]
    payload = booking["payload"]
    
    # Get partner info
    partner = await db_pg.get_partner_by_id(booking["partner_id"])
    partner_name = partner["display_name"] if partner else "Partner"
    
    if action == "ok":
        user_message = (
            f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
            f"👤 <b>Partner:</b> {partner_name}\n"
            f"🆔 Buyurtma: <code>{booking_id[:8]}...</code>\n\n"
            f"Partner tez orada siz bilan bog'lanadi."
        )
    else:
        user_message = (
            f"❌ <b>Buyurtmangiz rad etildi</b>\n\n"
            f"👤 <b>Partner:</b> {partner_name}\n"
            f"🆔 Buyurtma: <code>{booking_id[:8]}...</code>\n\n"
            f"Iltimos, boshqa partnerni tanlang yoki keyinroq urinib ko'ring."
        )
    
    try:
        await bot.send_message(
            chat_id=user_telegram_id,
            text=user_message,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_telegram_id}: {e}")
    
    logger.info(f"Booking {booking_id} -> {new_status} by partner")
