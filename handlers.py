"""
Message handlers for the bot (MVP+ with all features).
Audited and fixed for crash-resistance:
- All .lower()/.strip() calls guarded for None
- Contact handlers properly ordered (FSM state handler first)
- Callback data validation with graceful error handling
- Cancel detection safe for non-text updates
"""
from datetime import datetime
from keyboards import build_calendar

import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from states import BookingForm, LanguageSelection
from keyboards import (
    get_main_menu, get_cancel_keyboard, get_phone_keyboard,
    get_confirm_keyboard, get_language_keyboard, get_user_order_inline_keyboard,
    SERVICE_BUTTONS, SERVICE_NAMES
)
from admin_keyboards import get_order_status_keyboard, parse_status_callback, STATUS_DISPLAY
from config import ADMINS
from i18n import t, btn
import db
import rate_limit
from hotels_data import HOTELS, find_hotel
from keyboards import hotel_inline_kb
from aiogram.types import InputMediaPhoto



# Create router for handlers
router = Router()


def normalize_phone(phone: str | None) -> str:
    """Normalize phone to +<digits> format. Safe for None input."""
    if not phone:
        return ""
    # Remove all except digits and +
    cleaned = re.sub(r"[^\d+]", "", phone)
    # Ensure starts with +
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


def validate_phone_strict(phone: str | None) -> bool:
    """Validate phone number format strictly (+998 with 9 digits). Safe for None."""
    if not phone:
        return False
    # Remove all non-digits except +
    cleaned = re.sub(r"[^\d+]", "", phone)
    # Accept +998 followed by 9 digits
    return bool(re.match(r"^\+998\d{9}$", cleaned))


def validate_phone_contact(phone: str | None) -> bool:
    """
    Validate phone from shared contact (more lenient).
    Accepts any phone with 11-16 digits after +. Safe for None.
    """
    if not phone:
        return False
    cleaned = normalize_phone(phone)
    # Accept + followed by 11-16 digits (covers most international formats)
    return bool(re.match(r"^\+\d{11,16}$", cleaned))


def normalize_confirmation(text: str | None, lang: str) -> str | None:
    """Normalize user confirmation input to HA/YOQ or None if invalid. Safe for None."""
    if not text or not isinstance(text, str):
        return None
    
    text_lower = text.lower().strip()
    
    # Accept various forms of "yes" in all languages
    yes_variants = ("ha", "✅ ha", "xa", "да", "✅ да", "yes", "✅ yes", "h", "y")
    if text_lower in yes_variants:
        return "HA"
    
    # Accept various forms of "no"
    no_variants = ("yo'q", "yoq", "yo`q", "❌ yo'q", "нет", "❌ нет", "no", "❌ no", "yoʻq", "n")
    if text_lower in no_variants:
        return "YOQ"
    
    return None


def is_cancel_button(text: str | None) -> bool:
    """Check if text is a cancel button in any language. Safe for None input."""
    if not text or not isinstance(text, str):
        return False
    try:
        cancel_texts = ("❌ bekor qilish", "❌ отмена", "❌ cancel")
        return text.lower().strip() in cancel_texts
    except (AttributeError, TypeError):
        return False


def is_operator_button(text: str | None) -> bool:
    """Check if text is operator button in any language. Safe for None input."""
    if not text or not isinstance(text, str):
        return False
    return text in ("☎️ Operator", "☎️ Оператор")


def is_help_button(text: str | None) -> bool:
    """Check if text is help button in any language. Safe for None input."""
    if not text or not isinstance(text, str):
        return False
    return text in ("ℹ️ Yordam", "ℹ️ Помощь", "ℹ️ Help")


def is_language_button(text: str | None) -> bool:
    """Check if text is language button in any language. Safe for None input."""
    if not text or not isinstance(text, str):
        return False
    return text in ("🌐 Til", "🌐 Язык", "🌐 Language")


def is_my_orders_button(text: str | None) -> bool:
    """Check if text is my orders button in any language. Safe for None input."""
    if not text or not isinstance(text, str):
        return False
    return text in ("📜 Mening buyurtmalarim", "📜 Мои заказы", "📜 My orders")


def safe_get_user_id(message: Message) -> int | None:
    """Safely get user_id from message. Returns None if not available."""
    try:
        if message.from_user:
            return message.from_user.id
    except Exception:
        pass
    return None


def safe_get_lang(user_id: int | None) -> str:
    """Safely get user language, defaulting to 'uz' on any error."""
    if not user_id:
        return "uz"
    try:
        return db.get_user_lang(user_id)
    except Exception:
        return "uz"


# ============== START COMMAND ==============

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command - show main menu."""
    await state.clear()
    
    user = message.from_user
    user_id = safe_get_user_id(message)
    
    if not user_id:
        return  # Can't proceed without user
    
    # Upsert user in database (safe)
    try:
        db.upsert_user(user_id, user.username if user else None)
    except Exception as e:
        print(f"⚠️ DB error in upsert_user: {e}")
    
    # Get user's language
    lang = safe_get_lang(user_id)
    
    await message.answer(
        t("start_greeting", lang),
        reply_markup=get_main_menu(lang),
        parse_mode="HTML",
    )


# ============== CANCEL HANDLER (highest priority in FSM) ==============

@router.message(F.text.func(is_cancel_button), StateFilter("*"))
async def cancel_booking(message: Message, state: FSMContext):
    """Cancel current booking flow and return to main menu."""
    current_state = await state.get_state()
    user_id = safe_get_user_id(message)
    lang = safe_get_lang(user_id)
    
    if current_state is None:
        await message.answer(
            t("cancel_nothing", lang),
            reply_markup=get_main_menu(lang),
        )
        return
    
    await state.clear()
    await message.answer(
        t("cancel_done", lang),
        reply_markup=get_main_menu(lang),
    )


# ============== LANGUAGE SELECTION ==============

@router.message(F.text.func(is_language_button))
async def start_language_selection(message: Message, state: FSMContext):
    """Show language selection keyboard."""
    await state.clear()
    user_id = safe_get_user_id(message)
    lang = safe_get_lang(user_id)
    
    await state.set_state(LanguageSelection.choosing)
    await message.answer(
        t("choose_language", lang),
        reply_markup=get_language_keyboard(),
    )


@router.message(LanguageSelection.choosing)
async def process_language_choice(message: Message, state: FSMContext):
    """Process language selection."""
    text = message.text or ""
    user_id = safe_get_user_id(message)
    
    if not user_id:
        return
    
    # Map button text to language code
    lang_map = {
        "🇺🇿 O'zbekcha": "uz",
        "🇷🇺 Русский": "ru",
        "🇬🇧 English": "en",
    }
    
    new_lang = lang_map.get(text.strip()) if text else None
    
    if not new_lang:
        # Check if it's cancel
        if is_cancel_button(text):
            await state.clear()
            lang = safe_get_lang(user_id)
            await message.answer(
                t("cancel_done", lang),
                reply_markup=get_main_menu(lang),
            )
            return
        
        # Invalid selection
        lang = safe_get_lang(user_id)
        await message.answer(
            t("choose_language", lang),
            reply_markup=get_language_keyboard(),
        )
        return
    
    # Save new language (safe)
    try:
        db.set_user_lang(user_id, new_lang)
    except Exception as e:
        print(f"⚠️ DB error in set_user_lang: {e}")
    
    await state.clear()
    
    await message.answer(
        t("language_changed", new_lang),
        reply_markup=get_main_menu(new_lang),
    )


# ============== OPERATOR & HELP HANDLERS ==============

@router.message(F.text.func(is_operator_button))
async def operator_contact(message: Message, state: FSMContext):
    """Show operator contact info."""
    await state.clear()
    user_id = safe_get_user_id(message)
    lang = safe_get_lang(user_id)
    
    await message.answer(
        t("operator_info", lang),
        reply_markup=get_main_menu(lang),
        parse_mode="HTML",
    )


@router.message(F.text.func(is_help_button))
async def help_command(message: Message, state: FSMContext):
    """Show help instructions."""
    await state.clear()
    user_id = safe_get_user_id(message)
    lang = safe_get_lang(user_id)
    
    await message.answer(
        t("help_text", lang),
        reply_markup=get_main_menu(lang),
        parse_mode="HTML",
    )


# ============== USER HISTORY (My Orders) ==============

@router.message(F.text.func(is_my_orders_button))
async def show_my_orders(message: Message, state: FSMContext):
    """Show user's order history."""
    await state.clear()
    user_id = safe_get_user_id(message)
    
    if not user_id:
        return
    
    lang = safe_get_lang(user_id)
    
    # Get user's orders (safe)
    try:
        orders = db.get_orders_by_user(user_id, limit=10)
    except Exception as e:
        print(f"⚠️ DB error in get_orders_by_user: {e}")
        await message.answer(
            t("error_generic", lang) if "error_generic" in dir(t) else "⚠️ Xatolik yuz berdi.",
            reply_markup=get_main_menu(lang),
        )
        return
    
    if not orders:
        await message.answer(
            t("my_orders_empty", lang),
            reply_markup=get_main_menu(lang),
        )
        return
    
    # Build response with inline buttons for each order
    for order in orders:
        try:
            status_display = STATUS_DISPLAY.get(order.get("status", ""), order.get("status", ""))
            order_text = t("my_orders_item", lang,
                order_id=order.get("id", "?"),
                status=status_display,
                service=order.get("service", ""),
                date_text=order.get("date_text", ""),
                created_at=order.get("created_at", "")
            )
            
            await message.answer(
                order_text,
                reply_markup=get_user_order_inline_keyboard(order.get("id", 0), lang),
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"⚠️ Error formatting order: {e}")
            continue
    
    await message.answer(
        "⬆️",
        reply_markup=get_main_menu(lang),
    )


@router.callback_query(F.data.startswith("my:order:"))
async def show_my_order_details(callback: CallbackQuery):
    """Show detailed view of user's specific order."""
    user_id = callback.from_user.id if callback.from_user else None
    
    if not user_id:
        await callback.answer("❌ Error", show_alert=True)
        return
    
    lang = safe_get_lang(user_id)
    
    # Parse order_id from callback_data (safely)
    try:
        parts = (callback.data or "").split(":")
        if len(parts) < 3:
            raise ValueError("Invalid callback data format")
        order_id = int(parts[2])
    except (ValueError, IndexError, TypeError):
        await callback.answer(t("my_order_not_found", lang), show_alert=True)
        return
    
    # Get order from database (safe)
    try:
        order = db.get_order_by_id(order_id)
    except Exception as e:
        print(f"⚠️ DB error in get_order_by_id: {e}")
        await callback.answer("❌ Database error", show_alert=True)
        return
    
    if not order:
        await callback.answer(t("my_order_not_found", lang), show_alert=True)
        return
    
    # Security check: ensure user owns this order
    if order.get("user_id") != user_id:
        await callback.answer(t("my_order_no_access", lang), show_alert=True)
        return
    
    # Format full order details
    status_display = STATUS_DISPLAY.get(order.get("status", ""), order.get("status", ""))
    
    try:
        details_text = t("my_order_details", lang,
            order_id=order.get("id", "?"),
            service=order.get("service", ""),
            name=order.get("name", ""),
            phone=order.get("phone", ""),
            date_text=order.get("date_text", ""),
            details=order.get("details", ""),
            status=status_display,
            created_at=order.get("created_at", ""),
            updated_at=order.get("updated_at", "")
        )
        
        if callback.message:
            await callback.message.edit_text(
                text=details_text,
                parse_mode="HTML",
            )
    except Exception as e:
        print(f"⚠️ Error showing order details: {e}")
    
    await callback.answer()

# 111111111111111111111111111111
@router.callback_query(F.data.startswith("hotel:pick:"))
async def pick_hotel_and_start(call: CallbackQuery, state: FSMContext):
    hotel_id = (call.data or "").split(":")[-1]
    h = find_hotel(hotel_id)

    if not h:
        await call.answer("❌ Mehmonxona topilmadi", show_alert=True)
        return

    user_id = call.from_user.id if call.from_user else None
    lang = safe_get_lang(user_id)

    await state.clear()
    await state.update_data(
        lang=lang,
        service=f"🏨 Mehmonxona: {h['name']} ({h['price']})",
        hotel_id=h["id"],
        hotel_name=h["name"],
        hotel_price=h["price"],
    )
    await state.set_state(BookingForm.name)

    await call.message.answer(
        f"✅ Tanlandi: <b>{h['name']}</b>\n"
        f"💰 Narx: <b>{h['price']}</b>\n\n"
        f"Endi ismingizni kiriting:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(lang),
    )
    await call.answer("Tanlandi ✅")

@router.callback_query(F.data.startswith("room:"))
async def room_type_chosen(call: CallbackQuery, state: FSMContext):
    _, rooms, level = call.data.split(":")

    room_text = f"{rooms} xonali ({'Standart' if level == 'std' else 'Lyuks'})"

    await state.update_data(room_type=room_text)
    await call.answer()

    # endi mehmonxonalar chiqadi (avval yozgan media_group koding ishlaydi)
    await call.message.edit_text(
        f"🏨 Tanlangan xona: <b>{room_text}</b>\n\nMehmonxonani tanlang:",
        parse_mode="HTML",
    )

    # shu yerdan sen yozgan
    # show_hotels_catalog ichidagi kodni
    # function qilib chaqiramiz yoki shu yerga ko‘chirib qo‘yamiz


# ============== CALENDAR CALLBACKS ==============


HOTEL_BUTTON_TEXTS = ("🏨 Mehmonxona bron", "🏨 Mehmonhona bron", "🏨 Hotel")

@router.message(F.text.in_(HOTEL_BUTTON_TEXTS))
async def show_hotels_catalog(message: Message, state: FSMContext):
    await state.clear()

    await message.answer("🏨 Mehmonxonani tanlang:")

    
    for h in HOTELS:
        photos = h.get("photos", [])

        # xavfsizlik: photos bo‘sh bo‘lsa o‘tkazib yuboramiz
        if not photos:
            continue

        media = []
        for idx, p in enumerate(photos[:10]):  # Telegram: max 10 ta
            if idx == 0:
                media.append(
                    InputMediaPhoto(
                        media=p,
                        caption=f"<b>{h['name']}</b>\n💰 Narx: <b>{h['price']}</b>",
                        parse_mode="HTML",
                    )
                )
            else:
                media.append(InputMediaPhoto(media=p))

        # Albom qilib yuboradi (bir nechta rasm birga)
        await message.bot.send_media_group(chat_id=message.chat.id, media=media)

        # Pastidan tanlash tugmasi
        await message.answer(
            "⬆️ Tanlash uchun tugmani bosing:",
            reply_markup=hotel_inline_kb(h["id"], h["name"]),
        )

# ============== SERVICE SELECTION (Start FSM) ==============

@router.message(F.text.in_(SERVICE_BUTTONS))
async def start_booking(message: Message, state: FSMContext):
    """Start booking flow when user selects a service."""
    service = message.text or ""
    user_id = safe_get_user_id(message)
    lang = safe_get_lang(user_id)
    
    # Save selected service and move to name step
    await state.update_data(service=service, lang=lang)
    await state.set_state(BookingForm.name)
    
    service_display = SERVICE_NAMES.get(service, service)
    
    await message.answer(
        t("ask_name", lang, service=service_display),
        reply_markup=get_cancel_keyboard(lang),
        parse_mode="HTML",
    )


# ============== FSM: NAME STEP ==============

@router.message(BookingForm.name)
async def process_name(message: Message, state: FSMContext):
    """Process user's name input."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    
    text = message.text or ""
    
    # Check for cancel
    if is_cancel_button(text):
        await state.clear()
        await message.answer(
            t("cancel_done", lang),
            reply_markup=get_main_menu(lang),
        )
        return
    
    name = text.strip() if text else ""
    
    if len(name) < 2:
        await message.answer(
            t("name_too_short", lang),
            reply_markup=get_cancel_keyboard(lang),
        )
        return
    
    if len(name) > 100:
        await message.answer(
            t("name_too_long", lang),
            reply_markup=get_cancel_keyboard(lang),
        )
        return
    
    await state.update_data(name=name)
    await state.set_state(BookingForm.phone)
    
    await message.answer(
        t("ask_phone", lang),
        reply_markup=get_phone_keyboard(lang),
        parse_mode="HTML",
    )


# ============== FSM: PHONE STEP (Contact handler MUST be first) ==============

@router.message(BookingForm.phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    """Process shared contact - handles contact button press."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    
    # Extract phone from contact object (safely)
    phone_raw = message.contact.phone_number if message.contact else None
    phone_normalized = normalize_phone(phone_raw)
    
    # Validate with lenient rules for contacts (allows non-UZ numbers)
    if not validate_phone_contact(phone_normalized):
        await message.answer(
            t("phone_invalid", lang),
            reply_markup=get_phone_keyboard(lang),
            parse_mode="HTML",
        )
        return
    
    # Save phone and proceed to next step
    await state.update_data(phone=phone_normalized)
    await state.set_state(BookingForm.datetime)
    
    now = datetime.now()
    await message.answer(
        t("ask_datetime", lang),
        reply_markup=build_calendar(now.year, now.month),
        parse_mode="HTML",
    )


@router.message(BookingForm.phone)
async def process_phone_text(message: Message, state: FSMContext):
    """Process and validate phone number from text input."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    
    text = message.text or ""
    
    # Check for cancel
    if is_cancel_button(text):
        await state.clear()
        await message.answer(
            t("cancel_done", lang),
            reply_markup=get_main_menu(lang),
        )
        return
    
    phone = text.strip() if text else ""
    phone_normalized = normalize_phone(phone)
    
    # Strict validation for manual text input (+998 format required)
    if not validate_phone_strict(phone_normalized):
        await message.answer(
            t("phone_invalid", lang),
            reply_markup=get_phone_keyboard(lang),
            parse_mode="HTML",
        )
        return
    
    await state.update_data(phone=phone_normalized)
    await state.set_state(BookingForm.datetime)
    
    now = datetime.now()
    await message.answer(
        t("ask_datetime", lang),
        reply_markup=build_calendar(now.year, now.month),
        parse_mode="HTML",
    )


# ============== FSM: DATETIME STEP ==============

@router.message(BookingForm.datetime)
async def process_datetime(message: Message, state: FSMContext):
    """Process date and time input (text fallback for calendar)."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    
    text = message.text or ""
    
    # Check for cancel
    if is_cancel_button(text):
        await state.clear()
        await message.answer(
            t("cancel_done", lang),
            reply_markup=get_main_menu(lang),
        )
        return
    
    datetime_str = text.strip() if text else ""
    
    if len(datetime_str) < 3:
        await message.answer(
            t("datetime_too_short", lang),
            reply_markup=get_cancel_keyboard(lang),
        )
        return
    
    await state.update_data(datetime=datetime_str)
    await state.set_state(BookingForm.details)
    
    await message.answer(
        t("ask_details", lang),
        reply_markup=get_cancel_keyboard(lang),
        parse_mode="HTML",
    )


# ============== FSM: DETAILS STEP ==============

@router.message(BookingForm.details)
async def process_details(message: Message, state: FSMContext):
    """Process additional details and show confirmation."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    
    text = message.text or ""
    
    # Check for cancel
    if is_cancel_button(text):
        await state.clear()
        await message.answer(
            t("cancel_done", lang),
            reply_markup=get_main_menu(lang),
        )
        return
    
    details = text.strip() if text else ""
    
    await state.update_data(details=details)
    await state.set_state(BookingForm.confirm)
    
    # Get all collected data for summary
    data = await state.get_data()
    
    await message.answer(
        t("confirm_prompt", lang,
          service=data.get("service", ""),
          name=data.get("name", ""),
          phone=data.get("phone", ""),
          datetime=data.get("datetime", ""),
          details=data.get("details", "")),
        reply_markup=get_confirm_keyboard(lang),
        parse_mode="HTML",
    )


# ============== FSM: CONFIRMATION STEP ==============

@router.message(BookingForm.confirm)
async def process_confirmation(message: Message, state: FSMContext, bot: Bot):
    """Process final confirmation."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    
    text = message.text or ""
    
    # Check for cancel
    if is_cancel_button(text):
        await state.clear()
        await message.answer(
            t("cancel_done", lang),
            reply_markup=get_main_menu(lang),
        )
        return
    
    confirmation = normalize_confirmation(text, lang)
    
    if confirmation is None:
        await message.answer(
            t("confirm_invalid", lang),
            reply_markup=get_confirm_keyboard(lang),
            parse_mode="HTML",
        )
        return
    
    if confirmation == "YOQ":
        await state.clear()
        await message.answer(
            t("order_cancelled", lang),
            reply_markup=get_main_menu(lang),
        )
        return
    
    # confirmation == "HA"
    user = message.from_user
    user_id = safe_get_user_id(message)
    
    if not user_id:
        await message.answer("❌ Error")
        return
    
    # Check rate limit
    if not rate_limit.can_create_order(user_id):
        await message.answer(
            t("rate_limit", lang),
            reply_markup=get_confirm_keyboard(lang),
        )
        return
    
    # Create order in database (safe)
    try:
        order_id = db.create_order(
            user_id=user_id,
            username=user.username if user else None,
            service=data.get("service", ""),
            name=data.get("name", ""),
            phone=data.get("phone", ""),
            date_text=data.get("datetime", ""),
            details=data.get("details", ""),
        )
    except Exception as e:
        print(f"❌ DB error creating order: {e}")
        await message.answer(
            "❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.",
            reply_markup=get_main_menu(lang),
        )
        await state.clear()
        return
    
    # Record order creation for rate limiting
    try:
        rate_limit.record_order_created(user_id)
    except Exception as e:
        print(f"⚠️ Rate limit record error: {e}")
    
    # Format order notification for admins
    admin_notification = (
        f"🆕 <b>YANGI BUYURTMA #{order_id}</b>\n\n"
        f"🏷 <b>Xizmat:</b> {data.get('service', '')}\n"
        f"👤 <b>Mijoz:</b> {data.get('name', '')}\n"
        f"📱 <b>Telefon:</b> {data.get('phone', '')}\n"
        f"📅 <b>Sana/vaqt:</b> {data.get('datetime', '')}\n"
        f"📝 <b>Qo'shimcha:</b> {data.get('details', '')}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 User ID: {user_id}\n"
        f"👤 Username: @{user.username if user and user.username else 'N/A'}\n"
        f"📛 TG Name: {user.full_name if user else 'N/A'}\n\n"
        f"📊 Status: {STATUS_DISPLAY['new']}"
    )
    
    # Send notification to all admins with status buttons (safe)
    for admin_id in ADMINS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_notification,
                parse_mode="HTML",
                reply_markup=get_order_status_keyboard(order_id),
            )
        except Exception as e:
            print(f"⚠️ Failed to notify admin {admin_id}: {e}")
    
    # Clear state and thank user
    await state.clear()
    await message.answer(
        t("order_success", lang, order_id=order_id),
        reply_markup=get_main_menu(lang),
        parse_mode="HTML",
    )


# ============== ADMIN CALLBACK HANDLERS ==============
# @router.message(F.photo)
# async def get_photo_file_id(message: Message):
#     file_id = message.photo[-1].file_id
#     await message.answer(
#         f"📸 PHOTO FILE_ID:\n\n<code>{file_id}</code>",
#         parse_mode="HTML"
#     )
# ====================================
@router.callback_query(F.data.startswith("st:"))
async def handle_status_callback(callback: CallbackQuery, bot: Bot):
    """Handle admin status update callbacks."""
    # Safely parse callback data
    parsed = parse_status_callback(callback.data or "")
    
    if not parsed:
        await callback.answer("❌ Xatolik: noto'g'ri ma'lumot", show_alert=True)
        return
    
    order_id, new_status = parsed
    
    # Get order from database (safe)
    try:
        order = db.get_order(order_id)
    except Exception as e:
        print(f"⚠️ DB error in get_order: {e}")
        await callback.answer("❌ Database error", show_alert=True)
        return
    
    if not order:
        await callback.answer(f"❌ Buyurtma #{order_id} topilmadi", show_alert=True)
        return
    
    # Update order status (safe)
    try:
        success = db.update_order_status(order_id, new_status)
    except Exception as e:
        print(f"⚠️ DB error in update_order_status: {e}")
        await callback.answer("❌ Status yangilanmadi", show_alert=True)
        return
    
    if not success:
        await callback.answer("❌ Status yangilanmadi", show_alert=True)
        return
    
    # Update admin message
    status_text = STATUS_DISPLAY.get(new_status, new_status)
    
    try:
        # Edit the message to show new status
        old_text = callback.message.text if callback.message else ""
        if old_text:
            # Replace the status line
            lines = old_text.split("\n")
            new_lines = []
            for line in lines:
                if line.startswith("📊 Status:"):
                    new_lines.append(f"📊 Status: {status_text}")
                else:
                    new_lines.append(line)
            
            new_text = "\n".join(new_lines)
            
            await callback.message.edit_text(
                text=new_text,
                parse_mode="HTML",
                reply_markup=get_order_status_keyboard(order_id),
            )
    except Exception as e:
        print(f"⚠️ Failed to edit admin message: {e}")
    
    await callback.answer(f"✅ Status: {status_text}")
    
    # Notify user about status change (safe)
    user_id = order.get("user_id")
    if user_id:
        user_lang = safe_get_lang(user_id)
        status_key = f"status_{new_status}"
        
        try:
            await bot.send_message(
                chat_id=user_id,
                text=t(status_key, user_lang, order_id=order_id),
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"⚠️ Failed to notify user {user_id}: {e}")


# ============== FALLBACK HANDLER ==============

@router.message()
async def fallback_handler(message: Message, state: FSMContext):
    """Handle any unrecognized messages."""
    current_state = await state.get_state()
    user_id = safe_get_user_id(message)
    lang = safe_get_lang(user_id)
    
    # If user is in FSM, this shouldn't trigger (state handlers have priority)
    if current_state is None:
        await message.answer(
            t("fallback", lang),
            reply_markup=get_main_menu(lang),
        )
@router.callback_query(F.data.startswith("CAL:nav:"))
async def cal_nav(call: CallbackQuery):
    _, _, y, m = call.data.split(":")
    await call.message.edit_reply_markup(reply_markup=build_calendar(int(y), int(m)))
    await call.answer()

@router.callback_query(F.data.startswith("CAL:pick:"))
async def cal_pick(call: CallbackQuery, state: FSMContext):
    date_str = call.data.split(":", 2)[2]  # yyyy-mm-dd

    # FSM bosqichi datetime bo‘lsa – saqlaymiz
    current_state = await state.get_state()
    if current_state == BookingForm.datetime.state:
        await state.update_data(datetime=date_str)
        await state.set_state(BookingForm.details)

        user_id = call.from_user.id if call.from_user else None
        data = await state.get_data()
        lang = data.get("lang", safe_get_lang(user_id))

        await call.message.answer(
            t("ask_details", lang),
            reply_markup=get_cancel_keyboard(lang),
            parse_mode="HTML",
        )
        await call.message.delete()
    else:
        await call.message.edit_text(f"✅ Tanlandi: {date_str}")

    await call.answer("Sana tanlandi ✅")

@router.callback_query(F.data == "CAL:cancel")
async def cal_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = call.from_user.id if call.from_user else None
    lang = safe_get_lang(user_id)
    await call.message.edit_text(t("cancel_done", lang))
    await call.answer()

@router.callback_query(F.data == "CAL:noop")
async def cal_noop(call: CallbackQuery):
    await call.answer()
