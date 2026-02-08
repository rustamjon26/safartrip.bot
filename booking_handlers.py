"""
User booking handlers for Guide, Taxi, and Hotel flows with partner selection.
"""
import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import db_postgres as db_pg
from states import GuideBooking, TaxiBooking, HotelBooking
from keyboards import get_main_menu, get_cancel_keyboard, get_confirm_keyboard
from booking_dispatch import dispatch_booking_to_partner
import db  # For get_user_lang

logger = logging.getLogger(__name__)

booking_router = Router()


# =============================================================================
# Helper functions
# =============================================================================

def build_partners_keyboard(partners: list[dict], partner_type: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with partner buttons."""
    buttons = []
    for p in partners:
        # Show connected status
        status = "✅" if p["telegram_id"] else "⏳"
        text = f"{status} {p['display_name']}"
        callback_data = f"p:{partner_type}:{p['id']}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])
    
    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_partner")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_booking_confirm_keyboard(booking_type: str) -> InlineKeyboardMarkup:
    """Build confirmation keyboard for booking."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm:{booking_type}:yes"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"confirm:{booking_type}:no"),
        ]
    ])


def build_partner_action_keyboard(booking_id: str) -> InlineKeyboardMarkup:
    """Build accept/reject keyboard for partner."""
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
    """Start guide booking - show available guides."""
    await state.clear()
    
    partners = await db_pg.fetch_partners_by_type("guide")
    
    if not partners:
        await message.answer(
            "😔 Hozircha faol gidlar yo'q.\n"
            "Iltimos, keyinroq qaytadan urinib ko'ring.",
            reply_markup=get_main_menu()
        )
        return
    
    await state.set_state(GuideBooking.selecting_partner)
    await message.answer(
        "🧑‍💼 <b>Gid tanlang:</b>\n\n"
        "✅ - Ulangan (buyurtma qabul qiladi)\n"
        "⏳ - Ulanmagan (kutish kerak)",
        parse_mode="HTML",
        reply_markup=build_partners_keyboard(partners, "guide")
    )


@booking_router.callback_query(F.data.startswith("p:guide:"))
async def guide_selected(callback: CallbackQuery, state: FSMContext):
    """Guide selected - start collecting booking details."""
    await callback.answer()
    
    partner_id = callback.data.split(":")[2]
    partner = await db_pg.get_partner_by_id(partner_id)
    
    if not partner:
        await callback.message.edit_text("❌ Gid topilmadi. Qaytadan urinib ko'ring.")
        await state.clear()
        return
    
    # Check if partner is connected
    if not partner["telegram_id"]:
        await callback.message.edit_text(
            f"⚠️ <b>{partner['display_name']}</b> hali ulanmagan.\n\n"
            "Iltimos, boshqa gidni tanlang yoki keyinroq qaytadan urinib ko'ring.",
            parse_mode="HTML",
            reply_markup=build_partners_keyboard(await db_pg.fetch_partners_by_type("guide"), "guide")
        )
        return
    
    # Save partner to state
    await state.update_data(
        partner_id=partner_id,
        partner_name=partner["display_name"],
        partner_telegram_id=partner["telegram_id"]
    )
    
    await state.set_state(GuideBooking.date)
    await callback.message.edit_text(
        f"✅ Gid tanlandi: <b>{partner['display_name']}</b>\n\n"
        "📅 <b>Sanani kiriting:</b>\n"
        "Misol: 15-fevral yoki 15-20 fevral",
        parse_mode="HTML"
    )


@booking_router.message(GuideBooking.date)
async def guide_date_entered(message: Message, state: FSMContext):
    """Process guide booking date."""
    text = message.text.strip() if message.text else ""
    if not text or len(text) < 3:
        await message.answer("❌ Iltimos, to'g'ri sana kiriting. Misol: 15-fevral")
        return
    
    await state.update_data(date=text)
    await state.set_state(GuideBooking.route)
    await message.answer(
        "📍 <b>Marshrutni kiriting:</b>\n"
        "Misol: Samarqand - Buxoro - Xiva",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@booking_router.message(GuideBooking.route)
async def guide_route_entered(message: Message, state: FSMContext):
    """Process guide booking route."""
    text = message.text.strip() if message.text else ""
    if not text or len(text) < 3:
        await message.answer("❌ Iltimos, marshrutni kiriting.")
        return
    
    await state.update_data(route=text)
    await state.set_state(GuideBooking.people_count)
    await message.answer(
        "👥 <b>Necha kishi:</b>",
        parse_mode="HTML"
    )


@booking_router.message(GuideBooking.people_count)
async def guide_people_entered(message: Message, state: FSMContext):
    """Process guide booking people count."""
    text = message.text.strip() if message.text else ""
    if not text:
        await message.answer("❌ Iltimos, odamlar sonini kiriting.")
        return
    
    await state.update_data(people_count=text)
    await state.set_state(GuideBooking.note)
    await message.answer(
        "📝 <b>Qo'shimcha izoh:</b>\n"
        "(yoki /skip bosing)",
        parse_mode="HTML"
    )


@booking_router.message(GuideBooking.note)
async def guide_note_entered(message: Message, state: FSMContext):
    """Process guide booking note and show confirmation."""
    text = message.text.strip() if message.text else ""
    note = "" if text == "/skip" else text
    
    await state.update_data(note=note)
    data = await state.get_data()
    
    # Show confirmation
    await state.set_state(GuideBooking.confirm)
    await message.answer(
        f"📋 <b>Buyurtmani tasdiqlang:</b>\n\n"
        f"👤 <b>Gid:</b> {data['partner_name']}\n"
        f"📅 <b>Sana:</b> {data['date']}\n"
        f"📍 <b>Marshrut:</b> {data['route']}\n"
        f"👥 <b>Odamlar:</b> {data['people_count']}\n"
        f"📝 <b>Izoh:</b> {note or '-'}",
        parse_mode="HTML",
        reply_markup=build_booking_confirm_keyboard("guide")
    )


@booking_router.callback_query(F.data == "confirm:guide:yes")
async def guide_confirm_yes(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Confirm guide booking - create in DB and dispatch to partner."""
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
    
    # Create booking
    booking_id = await db_pg.create_booking(
        service_type="guide",
        partner_id=data["partner_id"],
        user_telegram_id=user_id,
        payload=payload,
        status="new"
    )
    
    if not booking_id:
        await callback.message.edit_text(
            "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
            reply_markup=None
        )
        await state.clear()
        return
    
    # Dispatch to partner using universal function
    success, message = await dispatch_booking_to_partner(
        bot=bot,
        booking_id=booking_id,
        partner_id=data["partner_id"],
        service_type="guide",
        payload=payload,
        user_info=user_info,
    )
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Buyurtma yuborildi!</b>\n\n"
            f"🆔 ID: <code>{booking_id[:8]}...</code>\n"
            f"👤 <b>Gid:</b> {data['partner_name']}\n\n"
            f"Partner javobini kuting.",
            parse_mode="HTML",
            reply_markup=None
        )
    else:
        await callback.message.edit_text(
            f"⚠️ <b>Buyurtma yaratildi</b>\n\n"
            f"🆔 ID: <code>{booking_id[:8]}...</code>\n"
            f"👤 <b>Gid:</b> {data['partner_name']}\n\n"
            f"{message}",
            parse_mode="HTML",
            reply_markup=None
        )
    
    await state.clear()
    await callback.message.answer("Bosh menyu:", reply_markup=get_main_menu())


@booking_router.callback_query(F.data == "confirm:guide:no")
async def guide_confirm_no(callback: CallbackQuery, state: FSMContext):
    """Cancel guide booking."""
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ Buyurtma bekor qilindi.", reply_markup=None)
    await callback.message.answer("Bosh menyu:", reply_markup=get_main_menu())


# =============================================================================
# TAXI FLOW
# =============================================================================

@booking_router.message(F.text == "🚕 Transport")
async def start_taxi_booking(message: Message, state: FSMContext):
    """Start taxi booking - show available taxis."""
    await state.clear()
    
    partners = await db_pg.fetch_partners_by_type("taxi")
    
    if not partners:
        await message.answer(
            "😔 Hozircha faol taksilar yo'q.\n"
            "Iltimos, keyinroq qaytadan urinib ko'ring.",
            reply_markup=get_main_menu()
        )
        return
    
    await state.set_state(TaxiBooking.selecting_partner)
    await message.answer(
        "🚕 <b>Taksi tanlang:</b>\n\n"
        "✅ - Ulangan (buyurtma qabul qiladi)\n"
        "⏳ - Ulanmagan (kutish kerak)",
        parse_mode="HTML",
        reply_markup=build_partners_keyboard(partners, "taxi")
    )


@booking_router.callback_query(F.data.startswith("p:taxi:"))
async def taxi_selected(callback: CallbackQuery, state: FSMContext):
    """Taxi selected - start collecting booking details."""
    await callback.answer()
    
    partner_id = callback.data.split(":")[2]
    partner = await db_pg.get_partner_by_id(partner_id)
    
    if not partner:
        await callback.message.edit_text("❌ Taksi topilmadi. Qaytadan urinib ko'ring.")
        await state.clear()
        return
    
    # Check if partner is connected
    if not partner["telegram_id"]:
        await callback.message.edit_text(
            f"⚠️ <b>{partner['display_name']}</b> hali ulanmagan.\n\n"
            "Iltimos, boshqa taksini tanlang yoki keyinroq qaytadan urinib ko'ring.",
            parse_mode="HTML",
            reply_markup=build_partners_keyboard(await db_pg.fetch_partners_by_type("taxi"), "taxi")
        )
        return
    
    # Save partner to state
    await state.update_data(
        partner_id=partner_id,
        partner_name=partner["display_name"],
        partner_telegram_id=partner["telegram_id"]
    )
    
    await state.set_state(TaxiBooking.pickup_location)
    await callback.message.edit_text(
        f"✅ Taksi tanlandi: <b>{partner['display_name']}</b>\n\n"
        "📍 <b>Qayerdan (olib ketish manzili):</b>",
        parse_mode="HTML"
    )


@booking_router.message(TaxiBooking.pickup_location)
async def taxi_pickup_entered(message: Message, state: FSMContext):
    """Process taxi pickup location."""
    text = message.text.strip() if message.text else ""
    if not text or len(text) < 3:
        await message.answer("❌ Iltimos, manzilni kiriting.")
        return
    
    await state.update_data(pickup_location=text)
    await state.set_state(TaxiBooking.dropoff_location)
    await message.answer(
        "📍 <b>Qayerga (tushish manzili):</b>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@booking_router.message(TaxiBooking.dropoff_location)
async def taxi_dropoff_entered(message: Message, state: FSMContext):
    """Process taxi dropoff location."""
    text = message.text.strip() if message.text else ""
    if not text or len(text) < 3:
        await message.answer("❌ Iltimos, manzilni kiriting.")
        return
    
    await state.update_data(dropoff_location=text)
    await state.set_state(TaxiBooking.pickup_time)
    await message.answer(
        "🕐 <b>Qachon (vaqt):</b>\n"
        "Misol: Bugun 15:00 yoki Ertaga ertalab",
        parse_mode="HTML"
    )


@booking_router.message(TaxiBooking.pickup_time)
async def taxi_time_entered(message: Message, state: FSMContext):
    """Process taxi pickup time."""
    text = message.text.strip() if message.text else ""
    if not text:
        await message.answer("❌ Iltimos, vaqtni kiriting.")
        return
    
    await state.update_data(pickup_time=text)
    await state.set_state(TaxiBooking.passengers)
    await message.answer(
        "👥 <b>Necha yo'lovchi:</b>",
        parse_mode="HTML"
    )


@booking_router.message(TaxiBooking.passengers)
async def taxi_passengers_entered(message: Message, state: FSMContext):
    """Process taxi passengers count."""
    text = message.text.strip() if message.text else ""
    if not text:
        await message.answer("❌ Iltimos, yo'lovchilar sonini kiriting.")
        return
    
    await state.update_data(passengers=text)
    await state.set_state(TaxiBooking.note)
    await message.answer(
        "📝 <b>Qo'shimcha izoh:</b>\n"
        "(yoki /skip bosing)",
        parse_mode="HTML"
    )


@booking_router.message(TaxiBooking.note)
async def taxi_note_entered(message: Message, state: FSMContext):
    """Process taxi note and show confirmation."""
    text = message.text.strip() if message.text else ""
    note = "" if text == "/skip" else text
    
    await state.update_data(note=note)
    data = await state.get_data()
    
    # Show confirmation
    await state.set_state(TaxiBooking.confirm)
    await message.answer(
        f"📋 <b>Buyurtmani tasdiqlang:</b>\n\n"
        f"🚕 <b>Taksi:</b> {data['partner_name']}\n"
        f"📍 <b>Qayerdan:</b> {data['pickup_location']}\n"
        f"📍 <b>Qayerga:</b> {data['dropoff_location']}\n"
        f"🕐 <b>Vaqt:</b> {data['pickup_time']}\n"
        f"👥 <b>Yo'lovchilar:</b> {data['passengers']}\n"
        f"📝 <b>Izoh:</b> {note or '-'}",
        parse_mode="HTML",
        reply_markup=build_booking_confirm_keyboard("taxi")
    )


@booking_router.callback_query(F.data == "confirm:taxi:yes")
async def taxi_confirm_yes(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Confirm taxi booking - create in DB and dispatch to partner."""
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
    
    # Create booking
    booking_id = await db_pg.create_booking(
        service_type="taxi",
        partner_id=data["partner_id"],
        user_telegram_id=user_id,
        payload=payload,
        status="new"
    )
    
    if not booking_id:
        await callback.message.edit_text(
            "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
            reply_markup=None
        )
        await state.clear()
        return
    
    # Dispatch to partner using universal function
    success, message = await dispatch_booking_to_partner(
        bot=bot,
        booking_id=booking_id,
        partner_id=data["partner_id"],
        service_type="taxi",
        payload=payload,
        user_info=user_info,
    )
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Buyurtma yuborildi!</b>\n\n"
            f"🆔 ID: <code>{booking_id[:8]}...</code>\n"
            f"🚕 <b>Taksi:</b> {data['partner_name']}\n\n"
            f"Partner javobini kuting.",
            parse_mode="HTML",
            reply_markup=None
        )
    else:
        await callback.message.edit_text(
            f"⚠️ <b>Buyurtma yaratildi</b>\n\n"
            f"🆔 ID: <code>{booking_id[:8]}...</code>\n"
            f"🚕 <b>Taksi:</b> {data['partner_name']}\n\n"
            f"{message}",
            parse_mode="HTML",
            reply_markup=None
        )
    
    await state.clear()
    await callback.message.answer("Bosh menyu:", reply_markup=get_main_menu())


@booking_router.callback_query(F.data == "confirm:taxi:no")
async def taxi_confirm_no(callback: CallbackQuery, state: FSMContext):
    """Cancel taxi booking."""
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ Buyurtma bekor qilindi.", reply_markup=None)
    await callback.message.answer("Bosh menyu:", reply_markup=get_main_menu())


# =============================================================================
# Cancel handler for partner selection
# =============================================================================

@booking_router.callback_query(F.data == "cancel_partner")
async def cancel_partner_selection(callback: CallbackQuery, state: FSMContext):
    """Cancel partner selection."""
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ Bekor qilindi.", reply_markup=None)
    await callback.message.answer("Bosh menyu:", reply_markup=get_main_menu())


# =============================================================================
# HOTEL FLOW (with location sending)
# =============================================================================

@booking_router.message(F.text == "🏨 Mehmonxona bron")
async def start_hotel_booking(message: Message, state: FSMContext):
    """Start hotel booking - show available hotels."""
    await state.clear()
    
    partners = await db_pg.fetch_partners_by_type("hotel")
    
    if not partners:
        await message.answer(
            "😔 Hozircha faol mehmonxonalar yo'q.\n"
            "Iltimos, keyinroq qaytadan urinib ko'ring.",
            reply_markup=get_main_menu()
        )
        return
    
    await state.set_state(HotelBooking.selecting_partner)
    await message.answer(
        "🏨 <b>Mehmonxona tanlang:</b>\n\n"
        "✅ - Ulangan (buyurtma qabul qiladi)\n"
        "⏳ - Ulanmagan (kutish kerak)",
        parse_mode="HTML",
        reply_markup=build_partners_keyboard(partners, "hotel")
    )


@booking_router.callback_query(F.data.startswith("p:hotel:"))
async def hotel_selected(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Hotel selected - send location first, then start booking flow."""
    await callback.answer()
    
    partner_id = callback.data.split(":")[2]
    partner = await db_pg.get_partner_by_id(partner_id)
    
    if not partner:
        await callback.message.edit_text("❌ Mehmonxona topilmadi. Qaytadan urinib ko'ring.")
        await state.clear()
        return
    
    # Check if partner is connected
    if not partner["telegram_id"]:
        await callback.message.edit_text(
            f"⚠️ <b>{partner['display_name']}</b> hali ulanmagan.\n\n"
            "Iltimos, boshqa mehmonxonani tanlang yoki keyinroq qaytadan urinib ko'ring.",
            parse_mode="HTML",
            reply_markup=build_partners_keyboard(await db_pg.fetch_partners_by_type("hotel"), "hotel")
        )
        return
    
    # Save partner to state
    await state.update_data(
        partner_id=partner_id,
        partner_name=partner["display_name"],
        partner_telegram_id=partner["telegram_id"]
    )
    
    # Edit the selection message
    await callback.message.edit_text(
        f"✅ Mehmonxona tanlandi: <b>{partner['display_name']}</b>",
        parse_mode="HTML",
        reply_markup=None
    )
    
    # Send location if available
    lat = partner.get("latitude")
    lng = partner.get("longitude")
    address = partner.get("address") or ""
    
    try:
        if lat and lng:
            # Send Telegram location message
            await callback.message.answer_location(
                latitude=lat,
                longitude=lng
            )
            
            # Send location info message
            location_text = f"📍 <b>{partner['display_name']}</b> joylashuvi yuborildi."
            if address:
                location_text += f"\n\n🏠 <b>Manzil:</b> {address}"
            location_text += "\n\nEndi buyurtma berish uchun ma'lumotlarni kiriting."
            
            await callback.message.answer(location_text, parse_mode="HTML")
        elif address:
            # No coordinates, but have address
            await callback.message.answer(
                f"🏠 <b>Manzil:</b> {address}\n\n"
                "Endi buyurtma berish uchun ma'lumotlarni kiriting.",
                parse_mode="HTML"
            )
        else:
            # No location info at all
            await callback.message.answer(
                "📍 Joylashuv ma'lumoti mavjud emas.\n\n"
                "Endi buyurtma berish uchun ma'lumotlarni kiriting.",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Failed to send hotel location: {e}")
        await callback.message.answer(
            "📍 Joylashuvni yuborishda xatolik.\n\n"
            "Endi buyurtma berish uchun ma'lumotlarni kiriting.",
            parse_mode="HTML"
        )
    
    # Move to date_from step
    await state.set_state(HotelBooking.date_from)
    await callback.message.answer(
        "📅 <b>Kirish sanasi (check-in):</b>\n"
        "Misol: 15-fevral",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@booking_router.message(HotelBooking.date_from)
async def hotel_date_from_entered(message: Message, state: FSMContext):
    """Process hotel check-in date."""
    text = message.text.strip() if message.text else ""
    if not text or len(text) < 3:
        await message.answer("❌ Iltimos, to'g'ri sana kiriting. Misol: 15-fevral")
        return
    
    await state.update_data(date_from=text)
    await state.set_state(HotelBooking.date_to)
    await message.answer(
        "📅 <b>Chiqish sanasi (check-out):</b>\n"
        "Misol: 18-fevral",
        parse_mode="HTML"
    )


@booking_router.message(HotelBooking.date_to)
async def hotel_date_to_entered(message: Message, state: FSMContext):
    """Process hotel check-out date."""
    text = message.text.strip() if message.text else ""
    if not text or len(text) < 3:
        await message.answer("❌ Iltimos, to'g'ri sana kiriting. Misol: 18-fevral")
        return
    
    await state.update_data(date_to=text)
    await state.set_state(HotelBooking.guests)
    await message.answer(
        "👥 <b>Mehmonlar soni:</b>",
        parse_mode="HTML"
    )


@booking_router.message(HotelBooking.guests)
async def hotel_guests_entered(message: Message, state: FSMContext):
    """Process hotel guests count."""
    text = message.text.strip() if message.text else ""
    if not text:
        await message.answer("❌ Iltimos, mehmonlar sonini kiriting.")
        return
    
    await state.update_data(guests=text)
    await state.set_state(HotelBooking.room_type)
    await message.answer(
        "🛏 <b>Xona turi:</b>\n"
        "Misol: Standart, Lyuks, 2 xonali\n"
        "(yoki /skip bosing)",
        parse_mode="HTML"
    )


@booking_router.message(HotelBooking.room_type)
async def hotel_room_entered(message: Message, state: FSMContext):
    """Process hotel room type."""
    text = message.text.strip() if message.text else ""
    room_type = "" if text == "/skip" else text
    
    await state.update_data(room_type=room_type)
    await state.set_state(HotelBooking.note)
    await message.answer(
        "📝 <b>Qo'shimcha izoh:</b>\n"
        "(yoki /skip bosing)",
        parse_mode="HTML"
    )


@booking_router.message(HotelBooking.note)
async def hotel_note_entered(message: Message, state: FSMContext):
    """Process hotel note and show confirmation."""
    text = message.text.strip() if message.text else ""
    note = "" if text == "/skip" else text
    
    await state.update_data(note=note)
    data = await state.get_data()
    
    # Show confirmation
    await state.set_state(HotelBooking.confirm)
    await message.answer(
        f"📋 <b>Buyurtmani tasdiqlang:</b>\n\n"
        f"🏨 <b>Mehmonxona:</b> {data['partner_name']}\n"
        f"📅 <b>Kirish:</b> {data['date_from']}\n"
        f"📅 <b>Chiqish:</b> {data['date_to']}\n"
        f"👥 <b>Mehmonlar:</b> {data['guests']}\n"
        f"🛏 <b>Xona:</b> {data.get('room_type') or '-'}\n"
        f"📝 <b>Izoh:</b> {note or '-'}",
        parse_mode="HTML",
        reply_markup=build_booking_confirm_keyboard("hotel")
    )


@booking_router.callback_query(F.data == "confirm:hotel:yes")
async def hotel_confirm_yes(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Confirm hotel booking - create in DB and dispatch to partner."""
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
    
    # Create booking
    booking_id = await db_pg.create_booking(
        service_type="hotel",
        partner_id=data["partner_id"],
        user_telegram_id=user_id,
        payload=payload,
        status="new"
    )
    
    if not booking_id:
        await callback.message.edit_text(
            "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
            reply_markup=None
        )
        await state.clear()
        return
    
    # Dispatch to partner using universal function
    success, message = await dispatch_booking_to_partner(
        bot=bot,
        booking_id=booking_id,
        partner_id=data["partner_id"],
        service_type="hotel",
        payload=payload,
        user_info=user_info,
    )
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Buyurtma yuborildi!</b>\n\n"
            f"🆔 ID: <code>{booking_id[:8]}...</code>\n"
            f"🏨 <b>Mehmonxona:</b> {data['partner_name']}\n\n"
            f"Partner javobini kuting.",
            parse_mode="HTML",
            reply_markup=None
        )
    else:
        await callback.message.edit_text(
            f"⚠️ <b>Buyurtma yaratildi</b>\n\n"
            f"🆔 ID: <code>{booking_id[:8]}...</code>\n"
            f"🏨 <b>Mehmonxona:</b> {data['partner_name']}\n\n"
            f"{message}",
            parse_mode="HTML",
            reply_markup=None
        )
    
    await state.clear()
    await callback.message.answer("Bosh menyu:", reply_markup=get_main_menu())


@booking_router.callback_query(F.data == "confirm:hotel:no")
async def hotel_confirm_no(callback: CallbackQuery, state: FSMContext):
    """Cancel hotel booking."""
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ Buyurtma bekor qilindi.", reply_markup=None)
    await callback.message.answer("Bosh menyu:", reply_markup=get_main_menu())

