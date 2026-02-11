"""
listings_user_flow.py - User Browsing + Booking Flow (Final Phase)

Features:
- Region → Category → Subtype → Listing cards with photos
- Detail view with media group
- Location sending
- Booking FSM (name → phone → date → note → confirm)
"""

import html
import logging
from typing import Optional

from aiogram import Router, Bot, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InputMediaPhoto,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, StateFilter, BaseFilter
from aiogram.exceptions import TelegramBadRequest

import db_postgres as db



logger = logging.getLogger(__name__)

user_flow_router = Router(name="user_flow")


# =============================================================================
# Registration Flow
# =============================================================================

class Registration(StatesGroup):
    """User registration flow."""
    contact = State()
    first_name = State()
    last_name = State()


async def start_registration(message: Message, state: FSMContext):
    """Start mandatory registration flow."""
    await state.clear()
    await state.set_state(Registration.contact)
    
    await message.answer(
        "👋 Assalomu alaykum!\n\n"
        "Botdan foydalanish uchun ro'yxatdan o'tishingiz kerak.\n"
        "Iltimos, telefon raqamingizni yuboring (tugmani bosing):",
        reply_markup=kb_contact(),
    )


@user_flow_router.message(StateFilter(Registration.contact), F.contact)
async def process_contact(message: Message, state: FSMContext):
    """Handle valid contact sharing."""
    contact = message.contact
    user_id = message.from_user.id
    
    # Check if contact belongs to sender
    if contact.user_id != user_id:
        await message.answer(
            "❌ Iltimos, o'z raqamingizni yuboring (kontakt yuborish).",
            reply_markup=kb_contact(),
        )
        return

    await state.update_data(phone=contact.phone_number)
    await state.set_state(Registration.first_name)
    
    await message.answer(
        "✅ Raqam qabul qilindi.\n\n"
        "👤 Ismingizni kiriting:",
        reply_markup=ReplyKeyboardRemove(),
    )


@user_flow_router.message(StateFilter(Registration.contact))
async def process_contact_fallback(message: Message):
    """Fallback for invalid contact input (e.g. text)."""
    await message.answer(
        "📞 Iltimos, telefon raqamingizni pastdagi tugma orqali yuboring (Kontakt yuborish).",
        reply_markup=kb_contact(),
    )


@user_flow_router.message(StateFilter(Registration.first_name))
async def process_first_name(message: Message, state: FSMContext):
    """Handle first name input."""
    name = (message.text or "").strip()
    
    if not message.text or not name or len(name) < 2:
        await message.answer("❌ Ism matn bo'lishi va kamida 2 harfdan iborat bo'lishi kerak:")
        return
        
    await state.update_data(first_name=name)
    await state.set_state(Registration.last_name)
    
    await message.answer(f"👤 Familyangizni kiriting ({h(name)}):")


@user_flow_router.message(StateFilter(Registration.last_name))
async def process_last_name(message: Message, state: FSMContext):
    """Handle last name input and save to DB."""
    last_name = (message.text or "").strip()
    
    if not message.text or not last_name or len(last_name) < 2:
        await message.answer("❌ Familya matn bo'lishi va kamida 2 harfdan iborat bo'lishi kerak:")
        return
        
    data = await state.get_data()
    user_id = message.from_user.id
    phone = data.get("phone")
    first_name = data.get("first_name")
    
    # Save to DB
    success = await db.upsert_user(user_id, phone, first_name, last_name)
    
    if not success:
        await message.answer("❌ Tizimda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring (/start).")
        await state.clear()
        return
        
    await state.clear()
    
    # Send success message + normal /start menu
    await message.answer(
        f"✅ <b>Ro'yxatdan o'tdingiz!</b>\n\n"
        f"Xush kelibsiz, {h(first_name)} {h(last_name)}!",
        parse_mode="HTML"
    )
    
    # Continue normal flow (show menu)
    # We call the logic that normally serves /start here manually
    await show_main_menu(message)


async def show_main_menu(message: Message):
    """Show the main menu (used after registration or login)."""
    # Logic copied from main.py's cmd_start to avoid circular import issues
    # But since main.py defines it, and we are in listings_user_flow.py,
    # we can't easily call main.py's function.
    # So we define the menu logic here or use a shared helper.
    # Given 'Do not create new file', we duplicate the message structure here.
    
    from config import ADMINS
    user_id = message.from_user.id
    
    lines = [
        "Assalomu alaykum! <b>SafarTrip.uz</b> botiga xush kelibsiz.",
        "",
        "📍 <b>Hudud:</b> Zomin",
        "",
        "Bu yerda siz mehmonxonalar, dam olish maskanlari va gid xizmatlarini oson topishingiz va band qilishingiz mumkin.",
        "",
        "Zomin bo'yicha eng yaxshi takliflar shu yerda!",
        "<i>(Boshqa hududlar tez orada qo'shiladi)</i>",
    ]
    
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=build_main_menu(user_id))


# =============================================================================
# HTML Safety
# =============================================================================

def h(text) -> str:
    """HTML-escape any value."""
    if text is None:
        return ""
    return html.escape(str(text), quote=False)


async def safe_send(message: Message, text: str, reply_markup=None, **kwargs) -> Message:
    """Send with HTML fallback."""
    try:
        return await message.answer(text, parse_mode="HTML", reply_markup=reply_markup, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            return await message.answer(text, parse_mode=None, reply_markup=reply_markup, **kwargs)
        raise


async def safe_edit(message: Message, text: str, reply_markup=None) -> Optional[Message]:
    """Edit with HTML fallback."""
    try:
        return await message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            return await message.edit_text(text, parse_mode=None, reply_markup=reply_markup)
        if "message is not modified" in str(e).lower():
            return message
        raise


async def safe_send_photo(message: Message, photo: str, caption: str, reply_markup=None) -> Message:
    """Send photo with caption, HTML fallback."""
    try:
        return await message.answer_photo(photo=photo, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            return await message.answer_photo(photo=photo, caption=caption, parse_mode=None, reply_markup=reply_markup)
        raise


# =============================================================================
# FSM States
# =============================================================================

class BrowseState(StatesGroup):
    """Browsing states."""
    region = State()
    category = State()
    subtype = State()
    listing = State()


class BookingForm(StatesGroup):
    """Booking form states."""
    name = State()
    phone = State()
    date = State()
    note = State()
    confirm = State()


# =============================================================================
# Constants
# =============================================================================

CATEGORIES = [
    ("hotel", "🏨 Mehmonxona"),
    ("guide", "🧑‍💼 Gid"),
    ("taxi", "🚕 Taxi"),
    ("place", "📍 Joy"),
]

HOTEL_SUBTYPES = [
    ("shale", "Shale"),
    ("uy_mehmonxona", "Uy mehmonxona"),
    ("mehmonxona", "Mehmonxona"),
    ("kapsula", "Kapsula mehmonxona"),
    ("dacha", "Dacha"),
]


# =============================================================================
# Keyboards
# =============================================================================

def kb_regions() -> InlineKeyboardMarkup:
    """Region selection."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏔 Zomin", callback_data="uf:region:zomin")],
    ])


def kb_contact() -> ReplyKeyboardMarkup:
    """Request contact keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def build_main_menu(user_id: int) -> ReplyKeyboardMarkup:
    """Main menu keyboard (dynamic for admins)."""
    # Base user buttons
    rows = [
        [KeyboardButton(text="🧭 Sayohatni boshlash"), KeyboardButton(text="📍 Hudud")],
        [KeyboardButton(text="❓ Yordam")]
    ]
    
    # Admin buttons
    from config import ADMINS
    if user_id in ADMINS:
        rows.append([KeyboardButton(text="➕ Listing qo'shish")])
        rows.append([KeyboardButton(text="🗂 Mening listinglarim")])
        
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,  # Persistent menu
    )


def kb_categories() -> InlineKeyboardMarkup:
    """Category selection."""
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"uf:cat:{code}")] for code, name in CATEGORIES]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="uf:back:region")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_subtypes() -> InlineKeyboardMarkup:
    """Hotel subtype selection."""
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"uf:sub:{code}")] for code, name in HOTEL_SUBTYPES]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="uf:back:category")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_listing_card(listing: dict, index: int, total: int) -> InlineKeyboardMarkup:
    """Card buttons for a single listing."""
    lid = listing["id"][:8]
    buttons = [
        [
            InlineKeyboardButton(text="✅ Tanlash", callback_data=f"uf:pick:{lid}"),
        ]
    ]
    
    # Location button only if coordinates exist
    if listing.get("latitude"):
        buttons[0].append(InlineKeyboardButton(text="📍 Lokatsiya", callback_data=f"uf:loc:{lid}"))
    
    # Pagination
    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"uf:page:{index - 1}"))
    if index < total - 1:
        nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"uf:page:{index + 1}"))
    if nav:
        buttons.append(nav)
    
    buttons.append([InlineKeyboardButton(text="🔙 Kategoriyaga", callback_data="uf:back:category")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_detail(listing: dict) -> InlineKeyboardMarkup:
    """Detail view buttons."""
    lid = listing["id"][:8]
    buttons = [
        [InlineKeyboardButton(text="📝 Bron qilish", callback_data=f"uf:book:{lid}")],
    ]
    
    if listing.get("latitude"):
        buttons.append([InlineKeyboardButton(text="📍 Lokatsiya", callback_data=f"uf:loc:{lid}")])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="uf:back:list")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_booking_confirm(listing_id: str) -> InlineKeyboardMarkup:
    """Booking confirmation buttons."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"uf:bconfirm:{listing_id[:8]}"),
            InlineKeyboardButton(text="❌ Bekor", callback_data="uf:bcancel"),
        ]
    ])


# =============================================================================
# /browse - Start Browsing
# =============================================================================

@user_flow_router.message(Command("browse"))
@user_flow_router.message(F.text == "🧭 Sayohatni boshlash")
@user_flow_router.message(F.text == "🔍 Qidirish") # Legacy support
async def cmd_browse(message: Message, state: FSMContext):
    """Start browsing flow."""
    await state.clear()
    await state.set_state(BrowseState.region)
    
    # Remove older reply keyboard if we want inline only
    # But usually bots keep main menu or hide it
    # We will hide main menu temporarily or keep it?
    # Requirement: keep UX simple.
    
    await safe_send(
        message,
        "<b>Qaysi hududga bormoqchisiz?</b>",
        reply_markup=kb_regions(),
    )


@user_flow_router.message(F.text == "📍 Hudud")
async def cmd_hudud_btn(message: Message):
    """Handle 📍 Hudud button."""
    await safe_send(
        message,
        "🏔 <b>Zomin</b> ✅\n\n"
        "(Boshqa hududlar tez orada qo‘shiladi)"
    )


@user_flow_router.message(F.text == "❓ Yordam")
async def cmd_help_btn(message: Message):
    """Handle Help button (triggers main help)."""
    # Since cmd_help is in main.py, we just show a simple help text here 
    # to avoid circular imports or complex routing.
    # Or ideally, main.py should handle this if we want exactly the same output.
    # But user asked to keep it simple.
    await safe_send(
        message,
        "📚 <b>Yordam</b>\n\n"
        "<b>Compass</b> - Sayohatni boshlash\n"
        "<b>Hudud</b> - Hozirgi lokatsiya\n"
        "<i>Adminlar uchun qo'shimcha menyular mavjud.</i>",
        reply_markup=build_main_menu(message.from_user.id)
    )
    
    
@user_flow_router.message(F.text == "➕ Listing qo'shish")
async def cmd_add_btn(message: Message, state: FSMContext):
    """Trigger listing wizard (Admin only)."""
    # Check admin
    from config import ADMINS
    if message.from_user.id not in ADMINS:
        return
        
    # We need to call the wizard start. 
    # Since wizard router is separate, but we are all in same dispatcher...
    # We can't easily call the function across routers without importing.
    # We will import it inside here to avoid top-level circular dep.
    from listing_wizard import start_add_listing
    await start_add_listing(message, state)


@user_flow_router.message(F.text == "🗂 Mening listinglarim")
async def cmd_my_listings_btn(message: Message):
    """Trigger my listings (Admin only)."""
    from config import ADMINS
    if message.from_user.id not in ADMINS:
        return
        
    from listing_wizard import cmd_my_listings
    await cmd_my_listings(message)


@user_flow_router.message(F.text)
async def handle_unknown_text(message: Message):
    """Fallback for unknown text messages (in no specific state)."""
    # Simply ignore or give hint if it looks like a command attempt?
    # User requirement: Avoid “Update is not handled”.
    # Provide a hint.
    await safe_send(
        message,
        "Buyruqlardan foydalaning: /browse yoki /help",
        reply_markup=build_main_menu(message.from_user.id)
    )


# =============================================================================
# Region Selection
# =============================================================================

@user_flow_router.callback_query(F.data.startswith("uf:region:"))
async def select_region(callback: CallbackQuery, state: FSMContext):
    """Handle region selection."""
    await callback.answer()
    
    region = callback.data.split(":")[2]
    await state.update_data(region=region)
    await state.set_state(BrowseState.category)
    
    await safe_edit(
        callback.message,
        f"🗺 Hudud: <b>Zomin</b>\n\nBoshqa viloyatlar va shaharlar bosqichma-bosqich qo'shib boriladi.\n\n📂 Kategoriyani tanlang:",
        reply_markup=kb_categories(),
    )


# =============================================================================
# Category Selection
# =============================================================================

@user_flow_router.callback_query(F.data.startswith("uf:cat:"))
async def select_category(callback: CallbackQuery, state: FSMContext):
    """Handle category selection."""
    await callback.answer()
    
    category = callback.data.split(":")[2]
    await state.update_data(category=category)
    
    if category == "hotel":
        await state.set_state(BrowseState.subtype)
        await safe_edit(
            callback.message,
            "🏨 <b>Mehmonxona turini tanlang</b>",
            reply_markup=kb_subtypes(),
        )
    else:
        await state.set_state(BrowseState.listing)
        await show_listings(callback.message, state, callback.from_user.id)


# =============================================================================
# Subtype Selection (Hotel)
# =============================================================================

@user_flow_router.callback_query(F.data.startswith("uf:sub:"))
async def select_subtype(callback: CallbackQuery, state: FSMContext):
    """Handle subtype selection for hotels."""
    await callback.answer()
    
    subtype = callback.data.split(":")[2]
    await state.update_data(subtype=subtype)
    await state.set_state(BrowseState.listing)
    
    await show_listings(callback.message, state, callback.from_user.id)


# =============================================================================
# Show Listings (Card by Card)
# =============================================================================

async def show_listings(message: Message, state: FSMContext, user_id: int, index: int = 0):
    """Display listings one by one with photo cards."""
    data = await state.get_data()
    
    region = data.get("region", "zomin")
    category = data.get("category")
    subtype = data.get("subtype")
    
    listings = await db.fetch_listings(region=region, category=category, subtype=subtype)
    
    if not listings:
        await safe_edit(
            message,
            "📭 Afsuski, bu kategoriyada hozircha listinglar yo'q.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="uf:back:category")]
            ]),
        )
        return
    
    await state.update_data(listings=[l["id"] for l in listings], current_index=index)
    
    if index >= len(listings):
        index = 0
    
    listing = listings[index]
    await send_listing_card(message, listing, index, len(listings))


async def send_listing_card(message: Message, listing: dict, index: int, total: int):
    """Send a single listing as a photo card."""
    photos = listing.get("photos", [])
    
    # Build caption
    lines = [f"<b>{h(listing['title'])}</b>"]
    
    if listing.get("price_from"):
        lines.append(f"💰 {listing['price_from']:,} {listing.get('currency', 'UZS')}")
    
    desc = listing.get("description", "")
    if desc:
        lines.append(f"📝 {h(desc[:80] + '...' if len(desc) > 80 else desc)}")
    
    lines.append(f"\n📊 {index + 1}/{total}")
    
    caption = "\n".join(lines)
    keyboard = kb_listing_card(listing, index, total)
    
    if photos:
        # Send first photo as card
        try:
            # Delete previous message first
            try:
                await message.delete()
            except:
                pass
            
            # Get the bot from message
            bot = message.bot
            chat_id = message.chat.id
            
            await bot.send_photo(
                chat_id=chat_id,
                photo=photos[0],
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except TelegramBadRequest as e:
            if "can't parse entities" in str(e).lower():
                await message.bot.send_photo(
                    chat_id=message.chat.id,
                    photo=photos[0],
                    caption=caption,
                    parse_mode=None,
                    reply_markup=keyboard,
                )
            else:
                # Photo might be invalid, send text only
                await message.bot.send_message(
                    chat_id=message.chat.id,
                    text=caption + "\n\n⚠️ Rasm yuklanmadi.",
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
    else:
        # No photo, send text message
        try:
            await message.edit_text(caption + "\n\n📷 Rasm yo'q", parse_mode="HTML", reply_markup=keyboard)
        except:
            await message.bot.send_message(
                chat_id=message.chat.id,
                text=caption + "\n\n📷 Rasm yo'q",
                parse_mode="HTML",
                reply_markup=keyboard,
            )


# =============================================================================
# Pagination
# =============================================================================

@user_flow_router.callback_query(F.data.startswith("uf:page:"))
async def paginate_listings(callback: CallbackQuery, state: FSMContext):
    """Handle pagination."""
    await callback.answer()
    
    index = int(callback.data.split(":")[2])
    data = await state.get_data()
    listing_ids = data.get("listings", [])
    
    if not listing_ids or index >= len(listing_ids):
        return
    
    listing = await db.get_listing(listing_ids[index])
    if listing:
        await state.update_data(current_index=index)
        await send_listing_card(callback.message, listing, index, len(listing_ids))


# =============================================================================
# Pick Listing (Detail View)
# =============================================================================

@user_flow_router.callback_query(F.data.startswith("uf:pick:"))
async def pick_listing(callback: CallbackQuery, state: FSMContext):
    """Show listing detail view."""
    await callback.answer()
    
    lid_short = callback.data.split(":")[2]
    data = await state.get_data()
    listing_ids = data.get("listings", [])
    
    # Find full ID
    full_id = next((lid for lid in listing_ids if lid.startswith(lid_short)), None)
    if not full_id:
        await callback.answer("Listing topilmadi", show_alert=True)
        return
    
    listing = await db.get_listing(full_id)
    if not listing:
        await callback.answer("Listing topilmadi", show_alert=True)
        return
    
    await state.update_data(selected_listing=full_id)
    
    photos = listing.get("photos", [])
    
    # Build detail text
    lines = [
        f"<b>{h(listing['title'])}</b>",
        "",
    ]
    
    if listing.get("description"):
        lines.append(f"📝 {h(listing['description'])}")
        lines.append("")
    
    if listing.get("price_from"):
        lines.append(f"💰 Narx: {listing['price_from']:,} {listing.get('currency', 'UZS')}")
    
    if listing.get("phone"):
        lines.append(f"📱 Telefon: {h(listing['phone'])}")
    
    if listing.get("address"):
        lines.append(f"📍 Manzil: {h(listing['address'])}")
    
    detail_text = "\n".join(lines)
    keyboard = kb_detail(listing)
    
    try:
        await callback.message.delete()
    except:
        pass
    
    bot = callback.message.bot
    chat_id = callback.message.chat.id
    
    # Send media group if multiple photos
    if len(photos) > 1:
        media = [InputMediaPhoto(media=p) for p in photos[:10]]
        try:
            await bot.send_media_group(chat_id=chat_id, media=media)
        except:
            # If media group fails, send first photo only
            if photos:
                await bot.send_photo(chat_id=chat_id, photo=photos[0])
        
        # Send detail text separately
        await bot.send_message(chat_id=chat_id, text=detail_text, parse_mode="HTML", reply_markup=keyboard)
    elif len(photos) == 1:
        await bot.send_photo(chat_id=chat_id, photo=photos[0], caption=detail_text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await bot.send_message(chat_id=chat_id, text=detail_text, parse_mode="HTML", reply_markup=keyboard)


# =============================================================================
# Location
# =============================================================================

@user_flow_router.callback_query(F.data.startswith("uf:loc:"))
async def send_location(callback: CallbackQuery, state: FSMContext):
    """Send listing location."""
    await callback.answer()
    
    lid_short = callback.data.split(":")[2]
    data = await state.get_data()
    listing_ids = data.get("listings", [])
    
    full_id = next((lid for lid in listing_ids if lid.startswith(lid_short)), None)
    if not full_id:
        full_id = data.get("selected_listing")
    
    if not full_id:
        await callback.answer("Listing topilmadi", show_alert=True)
        return
    
    listing = await db.get_listing(full_id)
    if not listing:
        await callback.answer("Listing topilmadi", show_alert=True)
        return
    
    lat = listing.get("latitude")
    lon = listing.get("longitude")
    
    if lat and lon:
        bot = callback.message.bot
        chat_id = callback.message.chat.id
        
        await bot.send_location(chat_id=chat_id, latitude=lat, longitude=lon)
        
        if listing.get("address"):
            await bot.send_message(chat_id=chat_id, text=f"📍 {h(listing['address'])}", parse_mode="HTML")
    else:
        await callback.answer("📍 Lokatsiya ma'lumoti mavjud emas.", show_alert=True)


# =============================================================================
# Back Navigation
# =============================================================================

@user_flow_router.callback_query(F.data == "uf:back:region")
async def back_to_region(callback: CallbackQuery, state: FSMContext):
    """Go back to region selection."""
    await callback.answer()
    await state.set_state(BrowseState.region)
    
    await safe_edit(
        callback.message,
        "<b>Qaysi hududga bormoqchisiz?</b>",
        reply_markup=kb_regions(),
    )


@user_flow_router.callback_query(F.data == "uf:back:category")
async def back_to_category(callback: CallbackQuery, state: FSMContext):
    """Go back to category selection."""
    await callback.answer()
    await state.update_data(subtype=None, listings=None, current_index=0)
    await state.set_state(BrowseState.category)
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.bot.send_message(
        chat_id=callback.message.chat.id,
        text="📂 Kategoriyani tanlang:",
        parse_mode="HTML",
        reply_markup=kb_categories(),
    )


@user_flow_router.callback_query(F.data == "uf:back:list")
async def back_to_list(callback: CallbackQuery, state: FSMContext):
    """Go back to listings."""
    await callback.answer()
    
    data = await state.get_data()
    index = data.get("current_index", 0)
    listing_ids = data.get("listings", [])
    
    if listing_ids and index < len(listing_ids):
        listing = await db.get_listing(listing_ids[index])
        if listing:
            try:
                await callback.message.delete()
            except:
                pass
            
            # Need to send as new message
            await callback.message.bot.send_photo(
                chat_id=callback.message.chat.id,
                photo=listing["photos"][0] if listing.get("photos") else None,
                caption=f"<b>{h(listing['title'])}</b>\n📊 {index + 1}/{len(listing_ids)}",
                parse_mode="HTML",
                reply_markup=kb_listing_card(listing, index, len(listing_ids)),
            ) if listing.get("photos") else await callback.message.bot.send_message(
                chat_id=callback.message.chat.id,
                text=f"<b>{h(listing['title'])}</b>\n📊 {index + 1}/{len(listing_ids)}",
                parse_mode="HTML",
                reply_markup=kb_listing_card(listing, index, len(listing_ids)),
            )


# =============================================================================
# Booking Flow
# =============================================================================

@user_flow_router.callback_query(F.data.startswith("uf:book:"))
async def start_booking(callback: CallbackQuery, state: FSMContext):
    """Start booking form."""
    await callback.answer()
    
    lid_short = callback.data.split(":")[2]
    data = await state.get_data()
    listing_ids = data.get("listings", [])
    
    full_id = next((lid for lid in listing_ids if lid.startswith(lid_short)), None)
    if not full_id:
        full_id = data.get("selected_listing")
    
    if not full_id:
        await callback.answer("Listing topilmadi", show_alert=True)
        return
    
    listing = await db.get_listing(full_id)
    if not listing:
        await callback.answer("Listing topilmadi", show_alert=True)
        return
    
    await state.update_data(booking_listing_id=full_id, booking_listing=listing)
    await state.set_state(BookingForm.name)
    
    await safe_edit(
        callback.message,
        f"📝 <b>Bron qilish</b>\n\n"
        f"📌 {h(listing['title'])}\n\n"
        f"👤 Ism-familyangizni kiriting:",
    )


@user_flow_router.message(BookingForm.name)
async def booking_name(message: Message, state: FSMContext):
    """Collect name."""
    name = (message.text or "").strip()
    
    if not name or len(name) < 2:
        await safe_send(message, "❌ Ism kamida 2 belgidan iborat bo'lishi kerak:")
        return
    
    await state.update_data(booking_name=name)
    await state.set_state(BookingForm.phone)
    
    await safe_send(message, f"✅ Ism: <b>{h(name)}</b>\n\n📱 Telefon raqamingizni kiriting:")


@user_flow_router.message(BookingForm.phone)
async def booking_phone(message: Message, state: FSMContext):
    """Collect phone."""
    phone = (message.text or "").strip()
    
    # Basic validation
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 7:
        await safe_send(message, "❌ Telefon raqami kamida 7 raqamdan iborat bo'lishi kerak:")
        return
    
    await state.update_data(booking_phone=phone)
    await state.set_state(BookingForm.date)
    
    await safe_send(
        message,
        f"✅ Telefon: <b>{h(phone)}</b>\n\n"
        f"📅 Sanani kiriting (masalan: '15-fevral' yoki '15-20 fevral'):",
    )


@user_flow_router.message(BookingForm.date)
async def booking_date(message: Message, state: FSMContext):
    """Collect date."""
    date = (message.text or "").strip()
    
    if not date:
        await safe_send(message, "❌ Sanani kiriting:")
        return
    
    await state.update_data(booking_date=date)
    await state.set_state(BookingForm.note)
    
    await safe_send(
        message,
        f"✅ Sana: <b>{h(date)}</b>\n\n"
        f"📝 Qo'shimcha izoh (yoki /skip):",
    )


@user_flow_router.message(BookingForm.note)
async def booking_note(message: Message, state: FSMContext):
    """Collect optional note."""
    text = (message.text or "").strip()
    
    note = None if text.lower() == "/skip" else text
    await state.update_data(booking_note=note)
    await state.set_state(BookingForm.confirm)
    
    data = await state.get_data()
    listing = data.get("booking_listing", {})
    
    lines = [
        "📋 <b>Bronni tasdiqlang</b>",
        "",
        f"📌 {h(listing.get('title', ''))}",
    ]
    
    if listing.get("price_from"):
        lines.append(f"💰 {listing['price_from']:,} {listing.get('currency', 'UZS')}")
    
    lines.extend([
        "",
        f"👤 Ism: {h(data.get('booking_name', ''))}",
        f"📱 Telefon: {h(data.get('booking_phone', ''))}",
        f"📅 Sana: {h(data.get('booking_date', ''))}",
    ])
    
    if note:
        lines.append(f"📝 Izoh: {h(note)}")
    
    await safe_send(
        message,
        "\n".join(lines),
        reply_markup=kb_booking_confirm(data.get("booking_listing_id", "")),
    )


@user_flow_router.callback_query(F.data.startswith("uf:bconfirm:"))
async def confirm_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Confirm and submit booking."""
    await callback.answer()
    
    data = await state.get_data()
    listing_id = data.get("booking_listing_id")
    listing = data.get("booking_listing", {})
    
    if not listing_id:
        await safe_edit(callback.message, "❌ Xatolik yuz berdi.")
        await state.clear()
        return
    
    # Create booking
    payload = {
        "name": data.get("booking_name", ""),
        "phone": data.get("booking_phone", ""),
        "date": data.get("booking_date", ""),
        "note": data.get("booking_note"),
    }
    
    booking_id = await db.create_booking(
        listing_id=listing_id,
        user_telegram_id=callback.from_user.id,
        payload=payload,
        expires_minutes=5,
    )
    
    if not booking_id:
        await safe_edit(callback.message, "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")
        await state.clear()
        return
    
    # Dispatch to partner admin
    from booking_dispatch import dispatch_booking_to_admin
    success = await dispatch_booking_to_admin(bot, booking_id)
    
    if success:
        await safe_edit(
            callback.message,
            "✅ <b>Bron yuborildi!</b>\n\n"
            f"📌 {h(listing.get('title', ''))}\n\n"
            "⏳ 5 daqiqa ichida javob keladi.\n"
            "Agar javob kelmasa, keyinroq urinib ko'ring.",
        )
    else:
        await safe_edit(
            callback.message,
            "⚠️ <b>Bron saqlandi</b>, lekin adminni topmadik.\n\n"
            "Tez orada siz bilan bog'lanamiz.",
        )
    
    await state.clear()


@user_flow_router.callback_query(F.data == "uf:bcancel")
async def cancel_booking(callback: CallbackQuery, state: FSMContext):
    """Cancel booking form."""
    await callback.answer()
    await state.clear()
    await safe_edit(callback.message, "❌ Bron bekor qilindi.\n\nQayta ko'rish: /browse")
