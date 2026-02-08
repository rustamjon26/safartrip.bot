"""
booking_handlers.py

User booking handlers for Guide, Taxi, and Hotel flows with partner selection.
✅ Fixes: Telegram "can't parse entities" (HTML safe), robust edit_text fallback,
✅ Hotel: sends location (lat/lng) + address safely
✅ Works with db_postgres.py async layer + dispatch_booking_to_partner()
"""

import logging
import html
from typing import Any

from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

import db_postgres as db_pg
from states import GuideBooking, TaxiBooking, HotelBooking
from keyboards import get_main_menu, get_cancel_keyboard
from booking_dispatch import dispatch_booking_to_partner

logger = logging.getLogger(__name__)
booking_router = Router()

# =============================================================================
# HTML-safe helpers (prevents "can't parse entities")
# =============================================================================

def h(text: Any) -> str:
    """HTML-escape any value (safe for Telegram parse_mode=HTML)."""
    if text is None:
        return ""
    return html.escape(str(text), quote=False)

async def safe_edit_text(message: Message, text: str, **kwargs):
    """
    Safe edit_text:
    - If HTML entities parsing fails, auto-fallback to plain text (parse_mode=None).
    """
    try:
        return await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e):
            logger.warning("Telegram entity parse failed; fallback to parse_mode=None. Error=%s", e)
            kwargs.pop("parse_mode", None)
            return await message.edit_text(text, parse_mode=None, **kwargs)
        raise

async def safe_answer(message: Message, text: str, **kwargs):
    """
    Safe answer:
    - Same fallback logic as edit_text.
    """
    try:
        return await message.answer(text, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e):
            logger.warning("Telegram entity parse failed in answer(); fallback to parse_mode=None. Error=%s", e)
            kwargs.pop("parse_mode", None)
            return await message.answer(text, parse_mode=None, **kwargs)
        raise


# =============================================================================
# Keyboards
# =============================================================================

def build_partners_keyboard(partners: list[dict], partner_type: str) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    for p in partners:
        status = "✅" if p.get("telegram_id") else "⏳"
        text = f"{status} {p.get('display_name', '—')}"
        callback_data = f"p:{partner_type}:{p.get('id')}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_partner")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_booking_confirm_keyboard(booking_type: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm:{booking_type}:yes"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"confirm:{booking_type}:no"),
        ]
    ])

def build_partner_action_keyboard(booking_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"bk:ok:{booking_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"bk:no:{booking_id}"),
        ]
    ])


# =============================================================================
# GUIDE FLOW
# =============================================================================

@booking_router.message(F.text == "🧑‍💼 Gid")
async def start_guide_booking(message: Message, state: FSMContext):
    await state.clear()

    partners = await db_pg.fetch_partners_by_type("guide")
    logger.info("guide partners=%s", len(partners))

    if not partners:
        await safe_answer(
            message,
            "😔 Hozircha faol gidlar yo'q.\n"
            "Iltimos, keyinroq qaytadan urinib ko'ring.\n\n"
            "<i>Admin: /seed_partners va /admin_health buyruqlarini tekshiring</i>",
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        return

    await state.set_state(GuideBooking.selecting_partner)
    await safe_answer(
        message,
        "🧑‍💼 <b>Gid tanlang:</b>\n\n"
        "✅ - Ulangan (buyurtma qabul qiladi)\n"
        "⏳ - Ulanmagan (kutish kerak)",
        parse_mode="HTML",
        reply_markup=build_partners_keyboard(partners, "guide")
    )

@booking_router.callback_query(F.data.startswith("p:guide:"))
async def guide_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    parts = (callback.data or "").split(":")
    partner_id = parts[2] if len(parts) >= 3 else ""
    partner = await db_pg.get_partner_by_id(partner_id)

    if not partner:
        await safe_edit_text(callback.message, "❌ Gid topilmadi. Qaytadan urinib ko'ring.", reply_markup=None)
        await state.clear()
        return

    if not partner.get("telegram_id"):
        partners = await db_pg.fetch_partners_by_type("guide")
        await safe_edit_text(
            callback.message,
            f"⚠️ <b>{h(partner.get('display_name'))}</b> hali ulanmagan.\n\n"
            "Iltimos, boshqa gidni tanlang yoki keyinroq qaytadan urinib ko'ring.",
            parse_mode="HTML",
            reply_markup=build_partners_keyboard(partners, "guide")
        )
        return

    await state.update_data(
        partner_id=partner_id,
        partner_name=partner.get("display_name", "—"),
        partner_telegram_id=partner.get("telegram_id")
    )

    await state.set_state(GuideBooking.date)
    await safe_edit_text(
        callback.message,
        f"✅ Gid tanlandi: <b>{h(partner.get('display_name'))}</b>\n\n"
        "📅 <b>Sanani kiriting:</b>\n"
        "Misol: 15-fevral yoki 15-20 fevral",
        parse_mode="HTML",
        reply_markup=None
    )

@booking_router.message(GuideBooking.date)
async def guide_date_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 3:
        await safe_answer(message, "❌ Iltimos, to'g'ri sana kiriting. Misol: 15-fevral")
        return

    await state.update_data(date=text)
    await state.set_state(GuideBooking.route)
    await safe_answer(
        message,
        "📍 <b>Marshrutni kiriting:</b>\nMisol: Samarqand - Buxoro - Xiva",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@booking_router.message(GuideBooking.route)
async def guide_route_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 3:
        await safe_answer(message, "❌ Iltimos, marshrutni kiriting.")
        return

    await state.update_data(route=text)
    await state.set_state(GuideBooking.people_count)
    await safe_answer(message, "👥 <b>Necha kishi:</b>", parse_mode="HTML")

@booking_router.message(GuideBooking.people_count)
async def guide_people_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await safe_answer(message, "❌ Iltimos, odamlar sonini kiriting.")
        return

    await state.update_data(people_count=text)
    await state.set_state(GuideBooking.note)
    await safe_answer(
        message,
        "📝 <b>Qo'shimcha izoh:</b>\n(yoki /skip bosing)",
        parse_mode="HTML"
    )

@booking_router.message(GuideBooking.note)
async def guide_note_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    note = "" if text == "/skip" else text

    await state.update_data(note=note)
    data = await state.get_data()

    await state.set_state(GuideBooking.confirm)
    await safe_answer(
        message,
        "📋 <b>Buyurtmani tasdiqlang:</b>\n\n"
        f"👤 <b>Gid:</b> {h(data.get('partner_name'))}\n"
        f"📅 <b>Sana:</b> {h(data.get('date'))}\n"
        f"📍 <b>Marshrut:</b> {h(data.get('route'))}\n"
        f"👥 <b>Odamlar:</b> {h(data.get('people_count'))}\n"
        f"📝 <b>Izoh:</b> {h(note) or '-'}",
        parse_mode="HTML",
        reply_markup=build_booking_confirm_keyboard("guide")
    )

@booking_router.callback_query(F.data == "confirm:guide:yes")
async def guide_confirm_yes(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()

    data = await state.get_data()
    user = callback.from_user
    user_id = user.id if user else 0

    payload = {
        "date": data.get("date", ""),
        "route": data.get("route", ""),
        "people_count": data.get("people_count", ""),
        "note": data.get("note", ""),
    }

    user_info = {
        "name": user.full_name if user else "—",
        "username": f"@{user.username}" if user and user.username else "—",
        "phone": data.get("phone", "—"),
    }

    booking_id = await db_pg.create_booking(
        service_type="guide",
        partner_id=data["partner_id"],
        user_telegram_id=user_id,
        payload=payload,
        status="new",
    )

    if not booking_id:
        await safe_edit_text(callback.message, "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.", reply_markup=None)
        await state.clear()
        return

    success, msg = await dispatch_booking_to_partner(
        bot=bot,
        booking_id=booking_id,
        partner_id=data["partner_id"],
        service_type="guide",
        payload=payload,
        user_info=user_info,
    )

    if success:
        await safe_edit_text(
            callback.message,
            "✅ <b>Buyurtma yuborildi!</b>\n\n"
            f"🆔 ID: <code>{h(booking_id[:8])}...</code>\n"
            f"👤 <b>Gid:</b> {h(data.get('partner_name'))}\n\n"
            "Partner javobini kuting.",
            parse_mode="HTML",
            reply_markup=None
        )
    else:
        await safe_edit_text(
            callback.message,
            "⚠️ <b>Buyurtma yaratildi</b>\n\n"
            f"🆔 ID: <code>{h(booking_id[:8])}...</code>\n"
            f"👤 <b>Gid:</b> {h(data.get('partner_name'))}\n\n"
            f"{h(msg)}",
            parse_mode="HTML",
            reply_markup=None
        )

    await state.clear()
    await safe_answer(callback.message, "Bosh menyu:", reply_markup=get_main_menu())

@booking_router.callback_query(F.data == "confirm:guide:no")
async def guide_confirm_no(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await safe_edit_text(callback.message, "❌ Buyurtma bekor qilindi.", reply_markup=None)
    await safe_answer(callback.message, "Bosh menyu:", reply_markup=get_main_menu())


# =============================================================================
# TAXI FLOW
# =============================================================================

@booking_router.message(F.text == "🚕 Transport")
async def start_taxi_booking(message: Message, state: FSMContext):
    await state.clear()

    partners = await db_pg.fetch_partners_by_type("taxi")
    if not partners:
        await safe_answer(
            message,
            "😔 Hozircha faol taksilar yo'q.\nIltimos, keyinroq qaytadan urinib ko'ring.",
            reply_markup=get_main_menu()
        )
        return

    await state.set_state(TaxiBooking.selecting_partner)
    await safe_answer(
        message,
        "🚕 <b>Taksi tanlang:</b>\n\n"
        "✅ - Ulangan (buyurtma qabul qiladi)\n"
        "⏳ - Ulanmagan (kutish kerak)",
        parse_mode="HTML",
        reply_markup=build_partners_keyboard(partners, "taxi")
    )

@booking_router.callback_query(F.data.startswith("p:taxi:"))
async def taxi_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    parts = (callback.data or "").split(":")
    partner_id = parts[2] if len(parts) >= 3 else ""
    partner = await db_pg.get_partner_by_id(partner_id)

    if not partner:
        await safe_edit_text(callback.message, "❌ Taksi topilmadi. Qaytadan urinib ko'ring.", reply_markup=None)
        await state.clear()
        return

    if not partner.get("telegram_id"):
        partners = await db_pg.fetch_partners_by_type("taxi")
        await safe_edit_text(
            callback.message,
            f"⚠️ <b>{h(partner.get('display_name'))}</b> hali ulanmagan.\n\n"
            "Iltimos, boshqa taksini tanlang yoki keyinroq qaytadan urinib ko'ring.",
            parse_mode="HTML",
            reply_markup=build_partners_keyboard(partners, "taxi")
        )
        return

    await state.update_data(
        partner_id=partner_id,
        partner_name=partner.get("display_name", "—"),
        partner_telegram_id=partner.get("telegram_id")
    )

    await state.set_state(TaxiBooking.pickup_location)
    await safe_edit_text(
        callback.message,
        f"✅ Taksi tanlandi: <b>{h(partner.get('display_name'))}</b>\n\n"
        "📍 <b>Qayerdan (olib ketish manzili):</b>",
        parse_mode="HTML",
        reply_markup=None
    )

@booking_router.message(TaxiBooking.pickup_location)
async def taxi_pickup_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 3:
        await safe_answer(message, "❌ Iltimos, manzilni kiriting.")
        return

    await state.update_data(pickup_location=text)
    await state.set_state(TaxiBooking.dropoff_location)
    await safe_answer(
        message,
        "📍 <b>Qayerga (tushish manzili):</b>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@booking_router.message(TaxiBooking.dropoff_location)
async def taxi_dropoff_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 3:
        await safe_answer(message, "❌ Iltimos, manzilni kiriting.")
        return

    await state.update_data(dropoff_location=text)
    await state.set_state(TaxiBooking.pickup_time)
    await safe_answer(
        message,
        "🕐 <b>Qachon (vaqt):</b>\nMisol: Bugun 15:00 yoki Ertaga ertalab",
        parse_mode="HTML"
    )

@booking_router.message(TaxiBooking.pickup_time)
async def taxi_time_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await safe_answer(message, "❌ Iltimos, vaqtni kiriting.")
        return

    await state.update_data(pickup_time=text)
    await state.set_state(TaxiBooking.passengers)
    await safe_answer(message, "👥 <b>Necha yo'lovchi:</b>", parse_mode="HTML")

@booking_router.message(TaxiBooking.passengers)
async def taxi_passengers_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await safe_answer(message, "❌ Iltimos, yo'lovchilar sonini kiriting.")
        return

    await state.update_data(passengers=text)
    await state.set_state(TaxiBooking.note)
    await safe_answer(
        message,
        "📝 <b>Qo'shimcha izoh:</b>\n(yoki /skip bosing)",
        parse_mode="HTML"
    )

@booking_router.message(TaxiBooking.note)
async def taxi_note_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    note = "" if text == "/skip" else text

    await state.update_data(note=note)
    data = await state.get_data()

    await state.set_state(TaxiBooking.confirm)
    await safe_answer(
        message,
        "📋 <b>Buyurtmani tasdiqlang:</b>\n\n"
        f"🚕 <b>Taksi:</b> {h(data.get('partner_name'))}\n"
        f"📍 <b>Qayerdan:</b> {h(data.get('pickup_location'))}\n"
        f"📍 <b>Qayerga:</b> {h(data.get('dropoff_location'))}\n"
        f"🕐 <b>Vaqt:</b> {h(data.get('pickup_time'))}\n"
        f"👥 <b>Yo'lovchilar:</b> {h(data.get('passengers'))}\n"
        f"📝 <b>Izoh:</b> {h(note) or '-'}",
        parse_mode="HTML",
        reply_markup=build_booking_confirm_keyboard("taxi")
    )

@booking_router.callback_query(F.data == "confirm:taxi:yes")
async def taxi_confirm_yes(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()

    data = await state.get_data()
    user = callback.from_user
    user_id = user.id if user else 0

    payload = {
        "pickup_location": data.get("pickup_location", ""),
        "dropoff_location": data.get("dropoff_location", ""),
        "pickup_time": data.get("pickup_time", ""),
        "passengers": data.get("passengers", ""),
        "note": data.get("note", ""),
    }

    user_info = {
        "name": user.full_name if user else "—",
        "username": f"@{user.username}" if user and user.username else "—",
        "phone": data.get("phone", "—"),
    }

    booking_id = await db_pg.create_booking(
        service_type="taxi",
        partner_id=data["partner_id"],
        user_telegram_id=user_id,
        payload=payload,
        status="new",
    )

    if not booking_id:
        await safe_edit_text(callback.message, "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.", reply_markup=None)
        await state.clear()
        return

    success, msg = await dispatch_booking_to_partner(
        bot=bot,
        booking_id=booking_id,
        partner_id=data["partner_id"],
        service_type="taxi",
        payload=payload,
        user_info=user_info,
    )

    if success:
        await safe_edit_text(
            callback.message,
            "✅ <b>Buyurtma yuborildi!</b>\n\n"
            f"🆔 ID: <code>{h(booking_id[:8])}...</code>\n"
            f"🚕 <b>Taksi:</b> {h(data.get('partner_name'))}\n\n"
            "Partner javobini kuting.",
            parse_mode="HTML",
            reply_markup=None
        )
    else:
        await safe_edit_text(
            callback.message,
            "⚠️ <b>Buyurtma yaratildi</b>\n\n"
            f"🆔 ID: <code>{h(booking_id[:8])}...</code>\n"
            f"🚕 <b>Taksi:</b> {h(data.get('partner_name'))}\n\n"
            f"{h(msg)}",
            parse_mode="HTML",
            reply_markup=None
        )

    await state.clear()
    await safe_answer(callback.message, "Bosh menyu:", reply_markup=get_main_menu())

@booking_router.callback_query(F.data == "confirm:taxi:no")
async def taxi_confirm_no(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await safe_edit_text(callback.message, "❌ Buyurtma bekor qilindi.", reply_markup=None)
    await safe_answer(callback.message, "Bosh menyu:", reply_markup=get_main_menu())


# =============================================================================
# HOTEL FLOW (with safe location sending)
# =============================================================================

@booking_router.message(F.text == "🏨 Mehmonxona bron")
async def start_hotel_booking(message: Message, state: FSMContext):
    await state.clear()

    partners = await db_pg.fetch_partners_by_type("hotel")
    if not partners:
        await safe_answer(
            message,
            "😔 Hozircha faol mehmonxonalar yo'q.\nIltimos, keyinroq qaytadan urinib ko'ring.",
            reply_markup=get_main_menu()
        )
        return

    await state.set_state(HotelBooking.selecting_partner)
    await safe_answer(
        message,
        "🏨 <b>Mehmonxona tanlang:</b>\n\n"
        "✅ - Ulangan (buyurtma qabul qiladi)\n"
        "⏳ - Ulanmagan (kutish kerak)",
        parse_mode="HTML",
        reply_markup=build_partners_keyboard(partners, "hotel")
    )

@booking_router.callback_query(F.data.startswith("p:hotel:"))
async def hotel_selected(callback: CallbackQuery, state: FSMContext):
    """
    Hotel selected:
    1) validate partner + connected
    2) save to state
    3) edit selection message safely
    4) send location/address safely
    5) go to HotelBooking.date_from
    """
    await callback.answer()

    parts = (callback.data or "").split(":")
    partner_id = parts[2] if len(parts) >= 3 else ""
    partner = await db_pg.get_partner_by_id(partner_id)

    if not partner:
        await safe_edit_text(callback.message, "❌ Mehmonxona topilmadi. Qaytadan urinib ko'ring.", reply_markup=None)
        await state.clear()
        return

    if not partner.get("telegram_id"):
        partners = await db_pg.fetch_partners_by_type("hotel")
        await safe_edit_text(
            callback.message,
            f"⚠️ <b>{h(partner.get('display_name'))}</b> hali ulanmagan.\n\n"
            "Iltimos, boshqa mehmonxonani tanlang yoki keyinroq qaytadan urinib ko'ring.",
            parse_mode="HTML",
            reply_markup=build_partners_keyboard(partners, "hotel")
        )
        return

    await state.update_data(
        partner_id=partner_id,
        partner_name=partner.get("display_name", "—"),
        partner_telegram_id=partner.get("telegram_id")
    )

    await safe_edit_text(
        callback.message,
        f"✅ Mehmonxona tanlandi: <b>{h(partner.get('display_name'))}</b>",
        parse_mode="HTML",
        reply_markup=None
    )

    lat = partner.get("latitude")
    lng = partner.get("longitude")
    address = (partner.get("address") or "").strip()

    # Note: lat/lng could be 0.0, so check against None
    has_coords = (lat is not None) and (lng is not None)

    try:
        if has_coords:
            await callback.message.answer_location(latitude=float(lat), longitude=float(lng))
            txt = f"📍 <b>{h(partner.get('display_name'))}</b> joylashuvi yuborildi."
            if address:
                txt += f"\n\n🏠 <b>Manzil:</b> {h(address)}"
            txt += "\n\nEndi buyurtma berish uchun ma'lumotlarni kiriting."
            await safe_answer(callback.message, txt, parse_mode="HTML")
        elif address:
            await safe_answer(
                callback.message,
                f"🏠 <b>Manzil:</b> {h(address)}\n\nEndi buyurtma berish uchun ma'lumotlarni kiriting.",
                parse_mode="HTML"
            )
        else:
            await safe_answer(
                callback.message,
                "📍 Joylashuv ma'lumoti mavjud emas.\n\nEndi buyurtma berish uchun ma'lumotlarni kiriting.",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.exception("Failed to send hotel location/address: %s", e)
        await safe_answer(
            callback.message,
            "📍 Joylashuvni yuborishda xatolik.\n\nEndi buyurtma berish uchun ma'lumotlarni kiriting.",
            parse_mode="HTML"
        )

    await state.set_state(HotelBooking.date_from)
    await safe_answer(
        callback.message,
        "📅 <b>Kirish sanasi (check-in):</b>\nMisol: 15-fevral",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@booking_router.message(HotelBooking.date_from)
async def hotel_date_from_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 3:
        await safe_answer(message, "❌ Iltimos, to'g'ri sana kiriting. Misol: 15-fevral")
        return
    await state.update_data(date_from=text)
    await state.set_state(HotelBooking.date_to)
    await safe_answer(message, "📅 <b>Chiqish sanasi (check-out):</b>\nMisol: 18-fevral", parse_mode="HTML")

@booking_router.message(HotelBooking.date_to)
async def hotel_date_to_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 3:
        await safe_answer(message, "❌ Iltimos, to'g'ri sana kiriting. Misol: 18-fevral")
        return
    await state.update_data(date_to=text)
    await state.set_state(HotelBooking.guests)
    await safe_answer(message, "👥 <b>Mehmonlar soni:</b>", parse_mode="HTML")

@booking_router.message(HotelBooking.guests)
async def hotel_guests_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await safe_answer(message, "❌ Iltimos, mehmonlar sonini kiriting.")
        return
    await state.update_data(guests=text)
    await state.set_state(HotelBooking.room_type)
    await safe_answer(
        message,
        "🛏 <b>Xona turi:</b>\nMisol: Standart, Lyuks, 2 xonali\n(yoki /skip bosing)",
        parse_mode="HTML"
    )

@booking_router.message(HotelBooking.room_type)
async def hotel_room_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    room_type = "" if text == "/skip" else text
    await state.update_data(room_type=room_type)
    await state.set_state(HotelBooking.note)
    await safe_answer(message, "📝 <b>Qo'shimcha izoh:</b>\n(yoki /skip bosing)", parse_mode="HTML")

@booking_router.message(HotelBooking.note)
async def hotel_note_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    note = "" if text == "/skip" else text

    await state.update_data(note=note)
    data = await state.get_data()

    await state.set_state(HotelBooking.confirm)
    await safe_answer(
        message,
        "📋 <b>Buyurtmani tasdiqlang:</b>\n\n"
        f"🏨 <b>Mehmonxona:</b> {h(data.get('partner_name'))}\n"
        f"📅 <b>Kirish:</b> {h(data.get('date_from'))}\n"
        f"📅 <b>Chiqish:</b> {h(data.get('date_to'))}\n"
        f"👥 <b>Mehmonlar:</b> {h(data.get('guests'))}\n"
        f"🛏 <b>Xona:</b> {h(data.get('room_type')) or '-'}\n"
        f"📝 <b>Izoh:</b> {h(note) or '-'}",
        parse_mode="HTML",
        reply_markup=build_booking_confirm_keyboard("hotel")
    )

@booking_router.callback_query(F.data == "confirm:hotel:yes")
async def hotel_confirm_yes(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()

    data = await state.get_data()
    user = callback.from_user
    user_id = user.id if user else 0

    payload = {
        "date_from": data.get("date_from", ""),
        "date_to": data.get("date_to", ""),
        "guests": data.get("guests", ""),
        "room_type": data.get("room_type", ""),
        "note": data.get("note", ""),
    }

    user_info = {
        "name": user.full_name if user else "—",
        "username": f"@{user.username}" if user and user.username else "—",
        "phone": data.get("phone", "—"),
    }

    booking_id = await db_pg.create_booking(
        service_type="hotel",
        partner_id=data["partner_id"],
        user_telegram_id=user_id,
        payload=payload,
        status="new",
    )

    if not booking_id:
        await safe_edit_text(callback.message, "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.", reply_markup=None)
        await state.clear()
        return

    success, msg = await dispatch_booking_to_partner(
        bot=bot,
        booking_id=booking_id,
        partner_id=data["partner_id"],
        service_type="hotel",
        payload=payload,
        user_info=user_info,
    )

    if success:
        await safe_edit_text(
            callback.message,
            "✅ <b>Buyurtma yuborildi!</b>\n\n"
            f"🆔 ID: <code>{h(booking_id[:8])}...</code>\n"
            f"🏨 <b>Mehmonxona:</b> {h(data.get('partner_name'))}\n\n"
            "Partner javobini kuting.",
            parse_mode="HTML",
            reply_markup=None
        )
    else:
        await safe_edit_text(
            callback.message,
            "⚠️ <b>Buyurtma yaratildi</b>\n\n"
            f"🆔 ID: <code>{h(booking_id[:8])}...</code>\n"
            f"🏨 <b>Mehmonxona:</b> {h(data.get('partner_name'))}\n\n"
            f"{h(msg)}",
            parse_mode="HTML",
            reply_markup=None
        )

    await state.clear()
    await safe_answer(callback.message, "Bosh menyu:", reply_markup=get_main_menu())

@booking_router.callback_query(F.data == "confirm:hotel:no")
async def hotel_confirm_no(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await safe_edit_text(callback.message, "❌ Buyurtma bekor qilindi.", reply_markup=None)
    await safe_answer(callback.message, "Bosh menyu:", reply_markup=get_main_menu())


# =============================================================================
# Cancel handler
# =============================================================================

@booking_router.callback_query(F.data == "cancel_partner")
async def cancel_partner_selection(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await safe_edit_text(callback.message, "❌ Bekor qilindi.", reply_markup=None)
    await safe_answer(callback.message, "Bosh menyu:", reply_markup=get_main_menu())
