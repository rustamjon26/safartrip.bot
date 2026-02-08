"""
Universal booking dispatch system.

Sends booking requests to partners and handles failures gracefully.
Notifies admins when partner is not connected.
"""
import os
import logging
from datetime import datetime
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import db_postgres as db_pg
from config import ADMINS

logger = logging.getLogger(__name__)


# =============================================================================
# MESSAGE TEMPLATES
# =============================================================================

def format_guide_message(booking_id: str, payload: dict, user_info: dict) -> str:
    """Format guide booking message for partner."""
    return (
        f"🧭 <b>YANGI GID SO'ROVI</b> #{booking_id[:8]}\n\n"
        f"👤 <b>Mijoz:</b> {user_info.get('name', '—')}\n"
        f"📱 <b>Telefon:</b> {user_info.get('phone', '—')}\n"
        f"🆔 <b>Username:</b> {user_info.get('username', '—')}\n\n"
        f"📅 <b>Sana:</b> {payload.get('date', '—')}\n"
        f"📍 <b>Marshrut:</b> {payload.get('route', '—')}\n"
        f"👥 <b>Odamlar:</b> {payload.get('people_count', '—')}\n"
        f"📝 <b>Izoh:</b> {payload.get('note') or '—'}"
    )


def format_hotel_message(booking_id: str, payload: dict, user_info: dict, partner_name: str) -> str:
    """Format hotel booking message for partner."""
    return (
        f"🏨 <b>YANGI MEHMONXONA BUYURTMASI</b> #{booking_id[:8]}\n\n"
        f"👤 <b>Mijoz:</b> {user_info.get('name', '—')}\n"
        f"📱 <b>Telefon:</b> {user_info.get('phone', '—')}\n"
        f"🆔 <b>Username:</b> {user_info.get('username', '—')}\n\n"
        f"📅 <b>Kirish:</b> {payload.get('date_from', '—')}\n"
        f"📅 <b>Chiqish:</b> {payload.get('date_to', '—')}\n"
        f"👥 <b>Mehmonlar:</b> {payload.get('guests', '—')}\n"
        f"🛏 <b>Xona:</b> {payload.get('room_type') or '—'}\n"
        f"📝 <b>Izoh:</b> {payload.get('note') or '—'}"
    )


def format_taxi_message(booking_id: str, payload: dict, user_info: dict) -> str:
    """Format taxi booking message for partner."""
    return (
        f"🚖 <b>YANGI TAKSI SO'ROVI</b> #{booking_id[:8]}\n\n"
        f"👤 <b>Mijoz:</b> {user_info.get('name', '—')}\n"
        f"📱 <b>Telefon:</b> {user_info.get('phone', '—')}\n"
        f"🆔 <b>Username:</b> {user_info.get('username', '—')}\n\n"
        f"📍 <b>Qayerdan:</b> {payload.get('pickup_location', '—')}\n"
        f"📍 <b>Qayerga:</b> {payload.get('dropoff_location', '—')}\n"
        f"🕐 <b>Vaqt:</b> {payload.get('pickup_time', '—')}\n"
        f"👥 <b>Yo'lovchilar:</b> {payload.get('passengers', '—')}\n"
        f"📝 <b>Izoh:</b> {payload.get('note') or '—'}"
    )


def build_partner_action_keyboard(booking_id: str) -> InlineKeyboardMarkup:
    """Build accept/reject keyboard for partner."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"bk:ok:{booking_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"bk:no:{booking_id}"),
        ]
    ])


# =============================================================================
# ADMIN NOTIFICATIONS
# =============================================================================

async def notify_admins_booking_failed(
    bot: Bot,
    booking_id: str,
    partner_id: str,
    partner_name: str,
    partner_type: str,
    reason: str
):
    """Notify admins when booking delivery fails."""
    admin_message = (
        f"⚠️ <b>Buyurtma yetkazilmadi</b>\n\n"
        f"🆔 Buyurtma: <code>{booking_id[:8]}...</code>\n"
        f"👤 Partner: {partner_name} ({partner_type})\n"
        f"🔗 Partner ID: <code>{partner_id[:8]}...</code>\n"
        f"❌ Sabab: {reason}\n\n"
        f"Iltimos, mijoz bilan bog'laning."
    )
    
    for admin_id in ADMINS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


# =============================================================================
# UNIVERSAL DISPATCH FUNCTION
# =============================================================================

async def dispatch_booking_to_partner(
    bot: Bot,
    booking_id: str,
    partner_id: str,
    service_type: str,
    payload: dict,
    user_info: dict,
) -> tuple[bool, str]:
    """
    Universal function to dispatch booking to partner.
    
    Args:
        bot: Aiogram Bot instance
        booking_id: UUID string of the booking
        partner_id: UUID string of the partner
        service_type: 'guide', 'hotel', or 'taxi'
        payload: Booking details dict
        user_info: Dict with 'name', 'phone', 'username'
    
    Returns:
        (success: bool, message: str)
    """
    # Load partner from DB
    partner = await db_pg.get_partner_by_id(partner_id)
    
    if not partner:
        logger.error(f"Partner {partner_id} not found for booking {booking_id}")
        await db_pg.set_booking_status(booking_id, "failed_partner_not_found")
        return False, "Partner topilmadi"
    
    partner_telegram_id = partner.get("telegram_id")
    partner_name = partner.get("display_name", "Partner")
    partner_type = partner.get("type", service_type)
    
    # Check if partner is connected
    if not partner_telegram_id:
        logger.warning(f"Partner {partner_name} not connected, booking {booking_id}")
        
        # Update booking status
        await db_pg.set_booking_status(booking_id, "failed_no_partner_connection")
        
        # Notify admins
        await notify_admins_booking_failed(
            bot=bot,
            booking_id=booking_id,
            partner_id=partner_id,
            partner_name=partner_name,
            partner_type=partner_type,
            reason="Partner Telegram hisobiga ulanmagan"
        )
        
        return False, "Partner hali ulanmagan. Jamoamiz siz bilan bog'lanadi."
    
    # Format message based on service type
    if service_type == "guide":
        message_text = format_guide_message(booking_id, payload, user_info)
    elif service_type == "hotel":
        message_text = format_hotel_message(booking_id, payload, user_info, partner_name)
    elif service_type == "taxi":
        message_text = format_taxi_message(booking_id, payload, user_info)
    else:
        message_text = f"📋 <b>Yangi buyurtma</b> #{booking_id[:8]}\n\n{payload}"
    
    # Send to partner
    try:
        await bot.send_message(
            chat_id=partner_telegram_id,
            text=message_text,
            parse_mode="HTML",
            reply_markup=build_partner_action_keyboard(booking_id)
        )
        
        # For hotels, also send location if available
        if service_type == "hotel":
            lat = partner.get("latitude")
            lng = partner.get("longitude")
            address = partner.get("address")
            
            if lat and lng:
                try:
                    # Send location to partner (so they see where booking is for)
                    pass  # Partner already knows their hotel location
                except Exception:
                    pass
            
            # If hotel has an address, include Google Maps link in a follow-up
            if lat and lng:
                maps_link = f"https://maps.google.com/maps?q={lat},{lng}"
                await bot.send_message(
                    chat_id=partner_telegram_id,
                    text=f"📍 <a href='{maps_link}'>Xaritada ko'rish</a>",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
        
        # Update booking status
        await db_pg.update_booking_sent(booking_id)
        
        logger.info(f"Booking {booking_id} dispatched to partner {partner_name}")
        return True, "Buyurtma partnerga yuborildi"
        
    except Exception as e:
        logger.error(f"Failed to send booking {booking_id} to partner: {e}")
        
        # Update status
        await db_pg.set_booking_status(booking_id, "failed_send_error")
        
        # Notify admins
        await notify_admins_booking_failed(
            bot=bot,
            booking_id=booking_id,
            partner_id=partner_id,
            partner_name=partner_name,
            partner_type=partner_type,
            reason=f"Xabar yuborishda xatolik: {str(e)[:50]}"
        )
        
        return False, "Xabar yuborishda xatolik. Jamoamiz siz bilan bog'lanadi."
