"""
admin_listing_wizard.py - Add Listing Wizard for Partners and Admins (Phase-2)

Commands:
- /add - Start the listing wizard
- /my_listings - List current user's listings with toggle/delete options
- /cancel - Cancel wizard at any step

Wizard Flow:
A) Category selection → B) Title → C) Description → D) Region
→ E) Subtype (hotel) → F) Price → G) Rating → H) Phone
→ I) Location → J) Photos → K) Confirm → L) Save

Roles:
- Super Admin: can add any listing
- Partner Admin: adds listings for themselves (telegram_admin_id = user_id)
"""

import logging
from typing import Optional, Any

from aiogram import Router, Bot, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    Location,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, StateFilter
from aiogram.exceptions import TelegramBadRequest

from config import ADMINS
import db_postgres as db_pg
from html_utils import h

logger = logging.getLogger(__name__)

listing_admin_router = Router(name="listing_admin")


# =============================================================================
# FSM States
# =============================================================================

class AddListing(StatesGroup):
    """States for the Add Listing wizard."""
    category = State()       # A: Category selection
    title = State()          # B: Title input
    description = State()    # C: Description input
    region = State()         # D: Region selection
    subtype = State()        # E: Subtype (hotel only)
    price = State()          # F: Price input
    rating = State()         # G: Rating input
    phone = State()          # H: Phone input
    location = State()       # I: Location input
    photos = State()         # J: Photos collection
    confirm = State()        # K: Confirmation


# =============================================================================
# Constants
# =============================================================================

CATEGORIES = [
    ("hotel", "🏨 hotel"),
    ("guide", "🧑‍💼 guide"),
    ("taxi", "🚕 taxi"),
    ("place", "📍 place"),
]

REGIONS = [
    ("zomin", "Zomin ✅"),
]

HOTEL_SUBTYPES = [
    ("shale", "Shale"),
    ("uy mehmonxona", "Uy mehmonxona"),
    ("mehmonxona", "Mehmonxona"),
    ("dacha", "Dacha"),
]

# Categories requiring location
LOCATION_REQUIRED = {"hotel", "place"}

# Categories requiring photos
PHOTOS_REQUIRED = {"hotel", "place"}

# Categories with price
PRICE_CATEGORIES = {"hotel", "taxi"}

MAX_PHOTOS = 5


# =============================================================================
# Helpers
# =============================================================================

def is_admin_or_partner(user_id: int) -> bool:
    """Check if user is allowed to add listings (admin or partner)."""
    # For now, all admins can add. Partners can add for themselves.
    # In production, you might want a separate partner verification.
    return user_id in ADMINS  # TODO: extend with partner check


def is_super_admin(user_id: int) -> bool:
    """Check if user is a super admin."""
    return user_id in ADMINS


async def safe_send_html(bot: Bot, chat_id: int, text: str, reply_markup=None) -> Optional[Message]:
    """Send HTML message with fallback to plain text."""
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            logger.warning("HTML parse failed, retrying without parse_mode: %s", e)
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=None,
                reply_markup=reply_markup,
            )
        raise


async def safe_edit_html(message: Message, text: str, reply_markup=None) -> Optional[Message]:
    """Edit HTML message with fallback to plain text."""
    try:
        return await message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            logger.warning("HTML parse failed in edit, retrying: %s", e)
            return await message.edit_text(text, parse_mode=None, reply_markup=reply_markup)
        # If message not modified, just return
        if "message is not modified" in str(e).lower():
            return message
        raise


async def send_msg(message: Message, text: str, reply_markup=None) -> Message:
    """Shortcut for safe HTML send."""
    try:
        return await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            return await message.answer(text, parse_mode=None, reply_markup=reply_markup)
        raise


# =============================================================================
# Keyboards
# =============================================================================

def build_category_keyboard() -> InlineKeyboardMarkup:
    """Category selection keyboard."""
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"addl:cat:{code}")]
        for code, name in CATEGORIES
    ]
    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="addl:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_region_keyboard() -> InlineKeyboardMarkup:
    """Region selection keyboard."""
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"addl:region:{code}")]
        for code, name in REGIONS
    ]
    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="addl:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_subtype_keyboard() -> InlineKeyboardMarkup:
    """Hotel subtype selection keyboard."""
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"addl:sub:{code}")]
        for code, name in HOTEL_SUBTYPES
    ]
    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="addl:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmation keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Saqlash", callback_data="addl:save"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="addl:cancel"),
        ]
    ])


def build_my_listings_keyboard(listings: list[dict]) -> InlineKeyboardMarkup:
    """Build keyboard for /my_listings."""
    buttons = []
    for lst in listings[:10]:  # Limit to 10 listings
        lid = lst["id"][:8]
        title = lst["title"][:20]
        status = "🟢" if lst["is_active"] else "🔴"
        buttons.append([
            InlineKeyboardButton(text=f"{status} {title}", callback_data=f"myl:view:{lst['id'][:8]}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


def build_listing_actions_keyboard(listing_id: str, is_active: bool) -> InlineKeyboardMarkup:
    """Actions for a single listing."""
    lid = listing_id[:8]
    toggle_text = "🔴 O'chirish" if is_active else "🟢 Yoqish"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=toggle_text, callback_data=f"myl:toggle:{lid}"),
            InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"myl:delete:{lid}"),
        ],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="myl:back")]
    ])


# =============================================================================
# /add - Start Wizard
# =============================================================================

@listing_admin_router.message(Command("add"))
async def cmd_add_listing(message: Message, state: FSMContext):
    """Start the Add Listing wizard."""
    user_id = message.from_user.id
    
    # All users can add listings for themselves (they become the telegram_admin_id)
    # Super admins can also assign to different admin IDs if needed
    
    await state.clear()
    await state.update_data(admin_id=user_id, photos=[])
    await state.set_state(AddListing.category)
    
    await send_msg(
        message,
        "📝 <b>Yangi listing qo'shish</b>\n\n"
        "Kategoriyani tanlang:",
        reply_markup=build_category_keyboard(),
    )


# =============================================================================
# Step A: Category Selection
# =============================================================================

@listing_admin_router.callback_query(F.data.startswith("addl:cat:"))
async def category_selected(callback: CallbackQuery, state: FSMContext):
    """Handle category selection."""
    await callback.answer()
    
    category = callback.data.split(":")[2]
    await state.update_data(category=category)
    await state.set_state(AddListing.title)
    
    cat_name = dict(CATEGORIES).get(category, category)
    await safe_edit_html(
        callback.message,
        f"✅ Kategoriya: <b>{h(cat_name)}</b>\n\n"
        f"📌 Endi nomini (title) kiriting (min 3 belgi):",
    )


# =============================================================================
# Step B: Title Input
# =============================================================================

@listing_admin_router.message(AddListing.title)
async def title_entered(message: Message, state: FSMContext):
    """Handle title input."""
    title = (message.text or "").strip()
    
    if title.lower() == "/cancel":
        await cancel_wizard(message, state)
        return
    
    if len(title) < 3:
        await send_msg(message, "❌ Nom kamida 3 belgidan iborat bo'lishi kerak. Qaytadan kiriting:")
        return
    
    await state.update_data(title=title)
    await state.set_state(AddListing.description)
    
    await send_msg(
        message,
        f"✅ Nom: <b>{h(title)}</b>\n\n"
        f"📝 Ta'rifni kiriting (yoki /skip):",
    )


# =============================================================================
# Step C: Description Input
# =============================================================================

@listing_admin_router.message(AddListing.description)
async def description_entered(message: Message, state: FSMContext):
    """Handle description input."""
    text = (message.text or "").strip()
    
    if text.lower() == "/cancel":
        await cancel_wizard(message, state)
        return
    
    description = None if text.lower() == "/skip" else text
    await state.update_data(description=description)
    await state.set_state(AddListing.region)
    
    desc_display = h(description[:50] + "...") if description and len(description) > 50 else h(description or "—")
    await send_msg(
        message,
        f"✅ Ta'rif: {desc_display}\n\n"
        f"🗺 Hududni tanlang:",
        reply_markup=build_region_keyboard(),
    )


# =============================================================================
# Step D: Region Selection
# =============================================================================

@listing_admin_router.callback_query(F.data.startswith("addl:region:"))
async def region_selected(callback: CallbackQuery, state: FSMContext):
    """Handle region selection."""
    await callback.answer()
    
    region = callback.data.split(":")[2]
    await state.update_data(region=region)
    
    data = await state.get_data()
    category = data.get("category", "")
    
    # If hotel, go to subtype; otherwise skip to price or rating
    if category == "hotel":
        await state.set_state(AddListing.subtype)
        await safe_edit_html(
            callback.message,
            f"✅ Hudud: <b>Zomin</b>\n\n"
            f"🏨 Mehmonxona turini tanlang:",
            reply_markup=build_subtype_keyboard(),
        )
    elif category in PRICE_CATEGORIES:
        await state.set_state(AddListing.price)
        await safe_edit_html(
            callback.message,
            f"✅ Hudud: <b>Zomin</b>\n\n"
            f"💰 Narxni kiriting (so'm) yoki /skip:",
        )
    else:
        # guide/place - go to rating
        await state.set_state(AddListing.rating)
        await safe_edit_html(
            callback.message,
            f"✅ Hudud: <b>Zomin</b>\n\n"
            f"⭐ Reytingni kiriting (0-5) yoki /skip:",
        )


# =============================================================================
# Step E: Subtype (Hotel only)
# =============================================================================

@listing_admin_router.callback_query(F.data.startswith("addl:sub:"))
async def subtype_selected(callback: CallbackQuery, state: FSMContext):
    """Handle subtype selection for hotels."""
    await callback.answer()
    
    subtype = callback.data.split(":")[2]
    await state.update_data(subtype=subtype)
    await state.set_state(AddListing.price)
    
    subtype_name = dict(HOTEL_SUBTYPES).get(subtype, subtype)
    await safe_edit_html(
        callback.message,
        f"✅ Turi: <b>{h(subtype_name)}</b>\n\n"
        f"💰 Narxni kiriting (so'm) yoki /skip:",
    )


# =============================================================================
# Step F: Price Input
# =============================================================================

@listing_admin_router.message(AddListing.price)
async def price_entered(message: Message, state: FSMContext):
    """Handle price input."""
    text = (message.text or "").strip()
    
    if text.lower() == "/cancel":
        await cancel_wizard(message, state)
        return
    
    price_from = None
    if text.lower() != "/skip":
        # Parse integer
        try:
            price_from = int(text.replace(" ", "").replace(",", ""))
            if price_from < 0:
                await send_msg(message, "❌ Narx manfiy bo'lishi mumkin emas. Qaytadan kiriting yoki /skip:")
                return
        except ValueError:
            await send_msg(message, "❌ Notog'ri format. Faqat raqam kiriting yoki /skip:")
            return
    
    await state.update_data(price_from=price_from)
    await state.set_state(AddListing.rating)
    
    price_display = f"{price_from:,} so'm" if price_from else "—"
    await send_msg(
        message,
        f"✅ Narx: <b>{price_display}</b>\n\n"
        f"⭐ Reytingni kiriting (0-5) yoki /skip:",
    )


# =============================================================================
# Step G: Rating Input
# =============================================================================

@listing_admin_router.message(AddListing.rating)
async def rating_entered(message: Message, state: FSMContext):
    """Handle rating input."""
    text = (message.text or "").strip()
    
    if text.lower() == "/cancel":
        await cancel_wizard(message, state)
        return
    
    rating = None
    if text.lower() != "/skip":
        try:
            rating = float(text.replace(",", "."))
            if rating < 0 or rating > 5:
                await send_msg(message, "❌ Reyting 0 dan 5 gacha bo'lishi kerak. Qaytadan yoki /skip:")
                return
            rating = round(rating, 1)
        except ValueError:
            await send_msg(message, "❌ Notog'ri format. Raqam kiriting (masalan: 4.5) yoki /skip:")
            return
    
    await state.update_data(rating=rating)
    await state.set_state(AddListing.phone)
    
    rating_display = f"⭐ {rating}" if rating else "—"
    await send_msg(
        message,
        f"✅ Reyting: <b>{rating_display}</b>\n\n"
        f"📱 Telefon raqamini kiriting yoki /skip:",
    )


# =============================================================================
# Step H: Phone Input
# =============================================================================

@listing_admin_router.message(AddListing.phone)
async def phone_entered(message: Message, state: FSMContext):
    """Handle phone input."""
    text = (message.text or "").strip()
    
    if text.lower() == "/cancel":
        await cancel_wizard(message, state)
        return
    
    phone = None if text.lower() == "/skip" else text
    await state.update_data(phone=phone)
    await state.set_state(AddListing.location)
    
    data = await state.get_data()
    category = data.get("category", "")
    
    location_required = category in LOCATION_REQUIRED
    skip_note = "" if location_required else " yoki /skip"
    
    await send_msg(
        message,
        f"✅ Telefon: <b>{h(phone or '—')}</b>\n\n"
        f"📍 Joylashuvni yuboring (Telegram location){skip_note}:\n"
        f"{'⚠️ Joylashuv majburiy!' if location_required else '(ixtiyoriy)'}",
    )


# =============================================================================
# Step I: Location Input
# =============================================================================

@listing_admin_router.message(AddListing.location, F.location)
async def location_received(message: Message, state: FSMContext):
    """Handle location input."""
    loc: Location = message.location
    
    await state.update_data(
        latitude=loc.latitude,
        longitude=loc.longitude,
        address=None,  # Could be enriched with reverse geocoding
    )
    await move_to_photos(message, state)


@listing_admin_router.message(AddListing.location)
async def location_text(message: Message, state: FSMContext):
    """Handle text input during location step."""
    text = (message.text or "").strip().lower()
    
    if text == "/cancel":
        await cancel_wizard(message, state)
        return
    
    data = await state.get_data()
    category = data.get("category", "")
    location_required = category in LOCATION_REQUIRED
    
    if text == "/skip":
        if location_required:
            await send_msg(
                message,
                "❌ Bu kategoriya uchun joylashuv majburiy!\n"
                "📍 Iltimos, Telegram location yuboring:",
            )
            return
        
        await state.update_data(latitude=None, longitude=None, address=None)
        await move_to_photos(message, state)
    else:
        await send_msg(
            message,
            "❌ Iltimos, Telegram location yuboring (📎 tugmasidan tanlang)\n"
            f"{'yoki /skip' if not location_required else ''}",
        )


async def move_to_photos(message: Message, state: FSMContext):
    """Transition to photos collection step."""
    await state.set_state(AddListing.photos)
    
    data = await state.get_data()
    category = data.get("category", "")
    photos_required = category in PHOTOS_REQUIRED
    
    lat = data.get("latitude")
    loc_status = f"📍 {lat:.4f}, ..." if lat else "—"
    
    skip_note = "" if photos_required else " /skip - o'tkazib yuborish"
    req_note = "⚠️ Rasmlar majburiy (1-5 ta)!" if photos_required else "(ixtiyoriy)"
    
    await send_msg(
        message,
        f"✅ Joylashuv: <b>{loc_status}</b>\n\n"
        f"📷 Rasmlarni yuboring (1-5 ta). Tugallash: /done\n"
        f"{req_note}{skip_note}",
    )


# =============================================================================
# Step J: Photos Collection
# =============================================================================

@listing_admin_router.message(AddListing.photos, F.photo)
async def photo_received(message: Message, state: FSMContext):
    """Collect photo file_ids."""
    data = await state.get_data()
    photos = data.get("photos", [])
    
    if len(photos) >= MAX_PHOTOS:
        await send_msg(message, f"⚠️ Maksimum {MAX_PHOTOS} ta rasm. /done bilan tugating.")
        return
    
    # Get the largest photo size
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    
    await send_msg(
        message,
        f"✅ Rasm {len(photos)}/{MAX_PHOTOS} qabul qilindi.\n"
        f"Yana yuboring yoki /done bilan tugating.",
    )


@listing_admin_router.message(AddListing.photos)
async def photos_text(message: Message, state: FSMContext):
    """Handle text during photos step."""
    text = (message.text or "").strip().lower()
    
    if text == "/cancel":
        await cancel_wizard(message, state)
        return
    
    data = await state.get_data()
    category = data.get("category", "")
    photos = data.get("photos", [])
    photos_required = category in PHOTOS_REQUIRED
    
    if text == "/done":
        if photos_required and len(photos) < 1:
            await send_msg(message, "❌ Kamida 1 ta rasm yuklang!")
            return
        await move_to_confirm(message, state)
        return
    
    if text == "/skip":
        if photos_required:
            await send_msg(message, "❌ Bu kategoriya uchun rasmlar majburiy! Kamida 1 ta yuboring.")
            return
        await move_to_confirm(message, state)
        return
    
    await send_msg(message, "📷 Rasm yuboring yoki /done, /skip buyruqlaridan foydalaning.")


async def move_to_confirm(message: Message, state: FSMContext):
    """Transition to confirmation step."""
    await state.set_state(AddListing.confirm)
    
    data = await state.get_data()
    
    # Build summary
    cat_name = dict(CATEGORIES).get(data.get("category", ""), data.get("category", ""))
    subtype = data.get("subtype")
    subtype_name = dict(HOTEL_SUBTYPES).get(subtype, subtype) if subtype else None
    
    lines = [
        "📋 <b>Tasdiqlash</b>",
        "",
        f"📂 Kategoriya: <b>{h(cat_name)}</b>",
    ]
    
    if subtype_name:
        lines.append(f"🏷 Turi: <b>{h(subtype_name)}</b>")
    
    lines.append(f"📌 Nom: <b>{h(data.get('title', ''))}</b>")
    
    desc = data.get("description")
    if desc:
        desc_short = desc[:50] + "..." if len(desc) > 50 else desc
        lines.append(f"📝 Ta'rif: {h(desc_short)}")
    
    lines.append(f"🗺 Hudud: <b>Zomin</b>")
    
    price = data.get("price_from")
    if price:
        lines.append(f"💰 Narx: <b>{price:,} so'm</b>")
    
    rating = data.get("rating")
    if rating:
        lines.append(f"⭐ Reyting: <b>{rating}</b>")
    
    phone = data.get("phone")
    if phone:
        lines.append(f"📱 Telefon: <b>{h(phone)}</b>")
    
    lat = data.get("latitude")
    if lat:
        lines.append(f"📍 Joylashuv: <b>{lat:.4f}, {data.get('longitude', 0):.4f}</b>")
    
    photos = data.get("photos", [])
    lines.append(f"📷 Rasmlar: <b>{len(photos)} ta</b>")
    
    lines.append("")
    lines.append("👇 Saqlaysizmi?")
    
    await send_msg(
        message,
        "\n".join(lines),
        reply_markup=build_confirm_keyboard(),
    )


# =============================================================================
# Step K: Confirm / Save
# =============================================================================

@listing_admin_router.callback_query(F.data == "addl:save")
async def save_listing(callback: CallbackQuery, state: FSMContext):
    """Save the listing to database."""
    await callback.answer()
    
    data = await state.get_data()
    
    # Insert into database
    listing_id = await db_pg.create_listing({
        "region": data.get("region", "zomin"),
        "category": data.get("category"),
        "subtype": data.get("subtype"),
        "title": data.get("title"),
        "description": data.get("description"),
        "price_from": data.get("price_from"),
        "rating": data.get("rating"),
        "telegram_admin_id": data.get("admin_id"),
        "photos": data.get("photos", []),
        "phone": data.get("phone"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "address": data.get("address"),
    })
    
    await state.clear()
    
    if listing_id:
        await safe_edit_html(
            callback.message,
            f"✅ <b>Saqlandi!</b>\n\n"
            f"📌 {h(data.get('title', ''))}\n"
            f"🆔 ID: <code>{listing_id[:8]}...</code>\n\n"
            f"📋 Listinglaringizni ko'rish: /my_listings",
        )
    else:
        await safe_edit_html(
            callback.message,
            "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
        )


# =============================================================================
# Cancel Handler
# =============================================================================

@listing_admin_router.callback_query(F.data == "addl:cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    """Cancel via inline button."""
    await callback.answer()
    await state.clear()
    await safe_edit_html(
        callback.message,
        "❌ Bekor qilindi.",
    )


async def cancel_wizard(message: Message, state: FSMContext):
    """Cancel the wizard."""
    await state.clear()
    await send_msg(message, "❌ Wizard bekor qilindi.")


@listing_admin_router.message(Command("cancel"), StateFilter(AddListing))
async def cmd_cancel(message: Message, state: FSMContext):
    """Handle /cancel command during wizard."""
    await cancel_wizard(message, state)


# =============================================================================
# /my_listings - List User's Listings
# =============================================================================

@listing_admin_router.message(Command("my_listings"))
async def cmd_my_listings(message: Message):
    """List current user's listings."""
    user_id = message.from_user.id
    
    listings = await db_pg.fetch_listings_by_admin(user_id)
    
    if not listings:
        await send_msg(
            message,
            "📭 Sizda hali listinglar yo'q.\n\n"
            "Yangi qo'shish uchun: /add",
        )
        return
    
    lines = [f"📋 <b>Sizning listinglaringiz</b> ({len(listings)} ta)", ""]
    
    for lst in listings[:10]:
        status = "🟢" if lst["is_active"] else "🔴"
        cat_emoji = {"hotel": "🏨", "guide": "🧑‍💼", "taxi": "🚕", "place": "📍"}.get(lst["category"], "📦")
        lines.append(f"{status} {cat_emoji} <b>{h(lst['title'])}</b>")
        lines.append(f"   ID: <code>{lst['id'][:8]}</code>")
    
    if len(listings) > 10:
        lines.append(f"\n... va yana {len(listings) - 10} ta")
    
    await send_msg(
        message,
        "\n".join(lines),
        reply_markup=build_my_listings_keyboard(listings),
    )


# =============================================================================
# My Listings Actions
# =============================================================================

@listing_admin_router.callback_query(F.data.startswith("myl:view:"))
async def view_listing(callback: CallbackQuery):
    """View a single listing."""
    await callback.answer()
    
    lid_short = callback.data.split(":")[2]
    user_id = callback.from_user.id
    
    # Find full listing by short ID prefix
    listings = await db_pg.fetch_listings_by_admin(user_id)
    listing = next((l for l in listings if l["id"].startswith(lid_short)), None)
    
    if not listing:
        await safe_edit_html(callback.message, "❌ Listing topilmadi.")
        return
    
    status = "🟢 Aktiv" if listing["is_active"] else "🔴 O'chirilgan"
    cat_name = {"hotel": "Mehmonxona", "guide": "Gid", "taxi": "Taxi", "place": "Joy"}.get(listing["category"], listing["category"])
    
    lines = [
        f"📌 <b>{h(listing['title'])}</b>",
        "",
        f"📂 Kategoriya: {cat_name}",
        f"🗺 Hudud: {listing['region'].title()}",
        f"📊 Holat: {status}",
    ]
    
    if listing.get("price_from"):
        lines.append(f"💰 Narx: {listing['price_from']:,} so'm")
    
    if listing.get("rating"):
        lines.append(f"⭐ Reyting: {listing['rating']}")
    
    if listing.get("phone"):
        lines.append(f"📱 Telefon: {h(listing['phone'])}")
    
    if listing.get("latitude"):
        lines.append(f"📍 Joylashuv: {listing['latitude']:.4f}, {listing['longitude']:.4f}")
    
    photos = listing.get("photos", [])
    lines.append(f"📷 Rasmlar: {len(photos)} ta")
    
    lines.append(f"\n🆔 ID: <code>{listing['id']}</code>")
    
    await safe_edit_html(
        callback.message,
        "\n".join(lines),
        reply_markup=build_listing_actions_keyboard(listing["id"], listing["is_active"]),
    )


@listing_admin_router.callback_query(F.data.startswith("myl:toggle:"))
async def toggle_listing(callback: CallbackQuery):
    """Toggle listing active status."""
    await callback.answer()
    
    lid_short = callback.data.split(":")[2]
    user_id = callback.from_user.id
    
    # Find full listing
    listings = await db_pg.fetch_listings_by_admin(user_id)
    listing = next((l for l in listings if l["id"].startswith(lid_short)), None)
    
    if not listing:
        await safe_edit_html(callback.message, "❌ Listing topilmadi.")
        return
    
    new_status = not listing["is_active"]
    success = await db_pg.toggle_listing_active(listing["id"], new_status)
    
    if success:
        status_text = "yoqildi" if new_status else "o'chirildi"
        await safe_edit_html(
            callback.message,
            f"✅ Listing {status_text}!\n\n"
            f"📌 {h(listing['title'])}",
            reply_markup=build_listing_actions_keyboard(listing["id"], new_status),
        )
    else:
        await safe_edit_html(callback.message, "❌ Xatolik yuz berdi.")


@listing_admin_router.callback_query(F.data.startswith("myl:delete:"))
async def delete_listing_confirm(callback: CallbackQuery):
    """Confirm listing deletion."""
    await callback.answer()
    
    lid_short = callback.data.split(":")[2]
    
    await safe_edit_html(
        callback.message,
        f"⚠️ <b>O'chirishni tasdiqlang</b>\n\n"
        f"Bu amalni bekor qilib bo'lmaydi!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, o'chirish", callback_data=f"myl:delok:{lid_short}"),
                InlineKeyboardButton(text="❌ Yo'q", callback_data="myl:back"),
            ]
        ]),
    )


@listing_admin_router.callback_query(F.data.startswith("myl:delok:"))
async def delete_listing_execute(callback: CallbackQuery):
    """Execute listing deletion."""
    await callback.answer()
    
    lid_short = callback.data.split(":")[2]
    user_id = callback.from_user.id
    
    # Find full listing
    listings = await db_pg.fetch_listings_by_admin(user_id)
    listing = next((l for l in listings if l["id"].startswith(lid_short)), None)
    
    if not listing:
        await safe_edit_html(callback.message, "❌ Listing topilmadi.")
        return
    
    success = await db_pg.delete_listing(listing["id"])
    
    if success:
        await safe_edit_html(
            callback.message,
            f"🗑 <b>O'chirildi!</b>\n\n"
            f"📌 {h(listing['title'])}",
        )
    else:
        await safe_edit_html(callback.message, "❌ Xatolik yuz berdi.")


@listing_admin_router.callback_query(F.data == "myl:back")
async def back_to_listings(callback: CallbackQuery):
    """Go back to listings list."""
    await callback.answer()
    
    user_id = callback.from_user.id
    listings = await db_pg.fetch_listings_by_admin(user_id)
    
    if not listings:
        await safe_edit_html(callback.message, "📭 Listinglar yo'q.")
        return
    
    lines = [f"📋 <b>Sizning listinglaringiz</b> ({len(listings)} ta)", ""]
    
    for lst in listings[:10]:
        status = "🟢" if lst["is_active"] else "🔴"
        cat_emoji = {"hotel": "🏨", "guide": "🧑‍💼", "taxi": "🚕", "place": "📍"}.get(lst["category"], "📦")
        lines.append(f"{status} {cat_emoji} <b>{h(lst['title'])}</b>")
        lines.append(f"   ID: <code>{lst['id'][:8]}</code>")
    
    await safe_edit_html(
        callback.message,
        "\n".join(lines),
        reply_markup=build_my_listings_keyboard(listings),
    )
