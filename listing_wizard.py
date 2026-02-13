"""
listing_wizard.py - Add Listing Wizard + Management (Final Phase)

Commands:
- /add: Start listing wizard (Super Admin + Partner Admin)
- /my_listings: View/manage own listings
- /cancel: Cancel wizard

Wizard flow:
Category → Title → Description → Region → Subtype → Price → Phone → Location → Photos → Confirm → Save
"""

import html
import logging
from typing import Optional

from aiogram import Router, Bot, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, StateFilter, BaseFilter
from aiogram.exceptions import TelegramBadRequest

from config import ADMINS
import db_postgres as db

logger = logging.getLogger(__name__)

listing_wizard_router = Router(name="listing_wizard")


# =============================================================================
# Router-Level Admin Guard
# =============================================================================

class AdminFilter(BaseFilter):
    """Block non-admin users from this entire router."""
    async def __call__(self, event) -> bool:
        user = getattr(event, "from_user", None)
        if user and user.id in ADMINS:
            return True
        # For commands, send denial; for callbacks/FSM, silently reject
        if hasattr(event, "answer"):
            try:
                await event.answer("⛔ Bu buyruq faqat adminlar uchun.")
            except Exception:
                pass
        return False


listing_wizard_router.message.filter(AdminFilter())
listing_wizard_router.callback_query.filter(AdminFilter())


# =============================================================================
# HTML Safety Helpers
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


# =============================================================================
# FSM States
# =============================================================================

class AddListing(StatesGroup):
    """Wizard states."""
    category = State()
    hotel_type = State()  # New step for hotels
    title = State()
    description = State()
    region = State()
    subtype = State()     # Deprecated for hotel, used for others if needed? No, purely internal now.
    price = State()
    phone = State()
    location = State()
    photos = State()
    confirm = State()


# =============================================================================
# Constants
# =============================================================================

CATEGORIES = [
    ("hotel", "🏨 Mehmonxona"),
    ("guide", "🧑‍💼 Gid"),
    ("taxi", "🚕 Taxi"),
    ("place", "📍 Diqqatga sazovor joy"),
]

HOTEL_SUBTYPES = [
    ("shale", "Shale"),
    ("uy_mehmonxona", "Uy mehmonxona"),
    ("mehmonxona", "Mehmonxona"),
    ("kapsula", "Kapsula mehmonxona"),
    ("dacha", "Dacha"),
]

LOCATION_REQUIRED = {"hotel", "place"}
PHOTOS_REQUIRED = {"hotel", "place"}
PRICE_CATEGORIES = {"hotel", "taxi"}
MAX_PHOTOS = 5


# =============================================================================
# Permission Check
# =============================================================================

def is_admin(user_id: int) -> bool:
    """Check if user is in ADMINS list."""
    return user_id in ADMINS


# =============================================================================
# Keyboards
# =============================================================================

def kb_categories() -> InlineKeyboardMarkup:
    """Category selection keyboard."""
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"wiz:cat:{code}")] for code, name in CATEGORIES]
    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="wiz:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_regions() -> InlineKeyboardMarkup:
    """Region selection keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Zomin ✅", callback_data="wiz:region:zomin")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="wiz:cancel")],
    ])


def kb_subtypes() -> InlineKeyboardMarkup:
    """Hotel subtype selection keyboard."""
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"wiz:sub:{code}")] for code, name in HOTEL_SUBTYPES]
    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="wiz:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_confirm() -> InlineKeyboardMarkup:
    """Confirmation keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Saqlash", callback_data="wiz:save"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="wiz:cancel"),
        ]
    ])


def kb_my_listings(listings: list[dict]) -> Optional[InlineKeyboardMarkup]:
    """Keyboard for /my_listings."""
    if not listings:
        return None
    buttons = []
    for lst in listings[:10]:
        status = "🟢" if lst["is_active"] else "🔴"
        title = lst["title"][:18]
        buttons.append([InlineKeyboardButton(
            text=f"{status} {title}",
            callback_data=f"myl:view:{lst['id'][:8]}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_listing_actions(listing_id: str, is_active: bool) -> InlineKeyboardMarkup:
    """Actions for a single listing."""
    lid = listing_id[:8]
    toggle = "🔴 O'chirish" if is_active else "🟢 Yoqish"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=toggle, callback_data=f"myl:toggle:{lid}"),
            InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"myl:del:{lid}"),
        ],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="myl:back")],
    ])


# =============================================================================
# /add - Start Wizard
# =============================================================================

@listing_wizard_router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    """Start the Add Listing wizard. Admin-only (enforced by router filter)."""
    user_id = message.from_user.id
    
    await state.clear()
    await state.update_data(admin_id=user_id, photos=[])
    await state.set_state(AddListing.category)
    
    await safe_send(
        message,
        "📝 <b>Yangi listing qo'shish</b>\n\nKategoriyani tanlang:",
        reply_markup=kb_categories(),
    )


# =============================================================================
# Step: Category
# =============================================================================

@listing_wizard_router.callback_query(F.data.startswith("wiz:cat:"))
async def step_category(callback: CallbackQuery, state: FSMContext):
    """Handle category selection."""
    await callback.answer()
    
    category = callback.data.split(":")[2]
    await state.update_data(category=category)
    
    if category == "hotel":
        await state.set_state(AddListing.hotel_type)
        await safe_edit(
            callback.message,
            "🏨 <b>Mehmonxona turini tanlang</b>",
            reply_markup=kb_subtypes(),
        )
    else:
        await state.set_state(AddListing.title)
        cat_name = dict(CATEGORIES).get(category, category)
        await safe_edit(
            callback.message,
            f"✅ Kategoriya: <b>{h(cat_name)}</b>\n\n📌 Nomini kiriting (min 3 belgi):",
        )


# =============================================================================
# Step: Title
# =============================================================================

@listing_wizard_router.message(AddListing.title)
async def step_title(message: Message, state: FSMContext):
    """Handle title input."""
    text = (message.text or "").strip()
    
    if text.lower() == "/cancel":
        await cancel_wizard(message, state)
        return
    
    if len(text) < 3:
        await safe_send(message, "❌ Nom kamida 3 belgidan iborat bo'lishi kerak:")
        return
    
    await state.update_data(title=text)
    await state.set_state(AddListing.description)
    
    # Get category for example
    data = await state.get_data()
    category = data.get("category", "hotel")
    
    examples = {
        "hotel": (
            "🏔 Zomin Suffa Mehmonxonasi\n"
            "📍 Manzil: Zomin, markazga yaqin\n"
            "🛏 Xona turlari: 2 va 4 kishilik\n"
            "💰 Narx: 250 000 so‘mdan\n"
            "🌐 Wi-Fi, 🚿 issiq suv, 🅿️ avtoturargoh mavjud\n"
            "🍽 Nonushta kiradi"
        ),
        "guide": (
            "🧑‍🏫 Zomin bo‘yicha professional gid\n"
            "📍 Yo‘nalish: Zomin tog‘lari va tarixiy joylar\n"
            "🗣 Tillar: O‘zbek, Rus, Ingliz\n"
            "🕒 3–5 soatlik ekskursiya\n"
            "💰 Narx: 400 000 so‘m (guruh uchun)"
        ),
        "taxi": (
            "🚕 Zomin – Toshkent yo‘nalishi\n"
            "🚘 Mashina: Cobalt / Gentra\n"
            "👥 4 yo‘lovchi\n"
            "💰 Narx: 120 000 so‘m (1 kishi)\n"
            "🕒 Oldindan buyurtma mumkin"
        ),
        "place": (
            "📍 Zomin Milliy bog‘i\n"
            "🏞 Go‘zal tog‘ manzarasi\n"
            "📸 Fotosessiya uchun qulay joy\n"
            "🕒 Tashrif vaqti: 08:00 – 20:00\n"
            "🎟 Kirish: Bepul"
        ),
    }
    
    ex_text = examples.get(category, "...")
    
    await safe_send(
        message, 
        f"✅ Nom: <b>{h(text)}</b>\n\n"
        f"📝 <b>Ta'rifni kiriting</b> (/skip o'tkazish):\n\n"
        f"<i>Namuna:</i>\n{h(ex_text)}"
    )


# =============================================================================
# Step: Description
# =============================================================================

@listing_wizard_router.message(AddListing.description)
async def step_description(message: Message, state: FSMContext):
    """Handle description input."""
    text = (message.text or "").strip()
    
    if text.lower() == "/cancel":
        await cancel_wizard(message, state)
        return
    
    desc = None if text.lower() == "/skip" else text
    await state.update_data(description=desc)
    await state.set_state(AddListing.region)
    
    await safe_send(
        message,
        f"✅ Ta'rif: {h(desc[:40] + '...' if desc and len(desc) > 40 else desc or '—')}\n\n🗺 Hududni tanlang:",
        reply_markup=kb_regions(),
    )


# =============================================================================
# Step: Region
# =============================================================================

@listing_wizard_router.callback_query(F.data.startswith("wiz:region:"))
async def step_region(callback: CallbackQuery, state: FSMContext):
    """Handle region selection."""
    await callback.answer()
    
    region = callback.data.split(":")[2]
    await state.update_data(region=region)
    
    data = await state.get_data()
    category = data.get("category", "")
    
    # Subtype already selected in Step 2 for hotels
    if category in PRICE_CATEGORIES:
        await state.set_state(AddListing.price)
        await safe_edit(
            callback.message,
            "✅ Hudud: <b>Zomin</b>\n\n💰 Narxni kiriting (UZS) yoki /skip:",
        )
    else:
        await state.set_state(AddListing.phone)
        await safe_edit(
            callback.message,
            "✅ Hudud: <b>Zomin</b>\n\n📱 Telefon raqamini kiriting yoki /skip:",
        )


# =============================================================================
# Step: Subtype (Hotel Type) - Moved to Step 2
# =============================================================================

@listing_wizard_router.callback_query(F.data.startswith("wiz:sub:"))
async def step_hotel_type(callback: CallbackQuery, state: FSMContext):
    """Handle hotel type selection."""
    await callback.answer()
    
    subtype = callback.data.split(":")[2]
    await state.update_data(subtype=subtype)
    await state.set_state(AddListing.title)
    
    subtype_name = dict(HOTEL_SUBTYPES).get(subtype, subtype)
    await safe_edit(
        callback.message,
        f"✅ Turi: <b>{h(subtype_name)}</b>\n\n📌 Nomini kiriting (min 3 belgi):",
    )


# =============================================================================
# Step: Price
# =============================================================================

@listing_wizard_router.message(AddListing.price)
async def step_price(message: Message, state: FSMContext):
    """Handle price input."""
    text = (message.text or "").strip()
    
    if text.lower() == "/cancel":
        await cancel_wizard(message, state)
        return
    
    price = None
    if text.lower() != "/skip":
        try:
            price = int(text.replace(" ", "").replace(",", ""))
            if price < 0:
                await safe_send(message, "❌ Narx manfiy bo'lishi mumkin emas:")
                return
        except ValueError:
            await safe_send(message, "❌ Faqat raqam kiriting yoki /skip:")
            return
    
    await state.update_data(price_from=price)
    await state.set_state(AddListing.phone)
    
    price_display = f"{price:,} UZS" if price else "—"
    await safe_send(message, f"✅ Narx: <b>{price_display}</b>\n\n📱 Telefon raqamini kiriting yoki /skip:")


# =============================================================================
# Step: Phone
# =============================================================================

@listing_wizard_router.message(AddListing.phone)
async def step_phone(message: Message, state: FSMContext):
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
    loc_required = category in LOCATION_REQUIRED
    
    skip_note = "" if loc_required else " yoki /skip"
    req_note = "⚠️ Joylashuv majburiy!" if loc_required else "(ixtiyoriy)"
    
    await safe_send(
        message,
        f"✅ Telefon: <b>{h(phone or '—')}</b>\n\n"
        f"📍 Joylashuvni yuboring (Telegram location){skip_note}\n{req_note}",
    )


# =============================================================================
# Step: Location
# =============================================================================

@listing_wizard_router.message(AddListing.location, F.location)
async def step_location_received(message: Message, state: FSMContext):
    """Handle location input."""
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
    )
    await move_to_photos(message, state)


@listing_wizard_router.message(AddListing.location)
async def step_location_text(message: Message, state: FSMContext):
    """Handle text during location step."""
    text = (message.text or "").strip().lower()
    
    if text == "/cancel":
        await cancel_wizard(message, state)
        return
    
    data = await state.get_data()
    category = data.get("category", "")
    loc_required = category in LOCATION_REQUIRED
    
    if text == "/skip":
        if loc_required:
            await safe_send(message, "❌ Bu kategoriya uchun joylashuv majburiy! Telegram location yuboring:")
            return
        await state.update_data(latitude=None, longitude=None)
        await move_to_photos(message, state)
    else:
        skip_hint = " yoki /skip" if not loc_required else ""
        await safe_send(message, f"❌ Telegram location yuboring (📎 tugmasidan){skip_hint}")


async def move_to_photos(message: Message, state: FSMContext):
    """Transition to photos step."""
    await state.set_state(AddListing.photos)
    
    data = await state.get_data()
    category = data.get("category", "")
    photos_required = category in PHOTOS_REQUIRED
    
    lat = data.get("latitude")
    loc_status = f"📍 {lat:.4f}, ..." if lat else "—"
    
    skip_note = "" if photos_required else " /skip - o'tkazish"
    req_note = "⚠️ Rasmlar majburiy (1-5)!" if photos_required else "(ixtiyoriy)"
    
    await safe_send(
        message,
        f"✅ Joylashuv: <b>{loc_status}</b>\n\n"
        f"📷 Rasmlarni yuboring (1-5 ta). Tugallash: /done\n{req_note}{skip_note}",
    )


# =============================================================================
# Step: Photos
# =============================================================================

@listing_wizard_router.message(AddListing.photos, F.photo)
async def step_photos_received(message: Message, state: FSMContext):
    """Collect photo file_ids."""
    data = await state.get_data()
    photos = data.get("photos", [])
    
    if len(photos) >= MAX_PHOTOS:
        await safe_send(message, f"⚠️ Maksimum {MAX_PHOTOS} ta rasm. /done bilan tugating.")
        return
    
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    
    await safe_send(message, f"✅ Rasm {len(photos)}/{MAX_PHOTOS} qabul qilindi. Yana yuboring yoki /done")


@listing_wizard_router.message(AddListing.photos)
async def step_photos_text(message: Message, state: FSMContext):
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
            await safe_send(message, "❌ Kamida 1 ta rasm yuklang!")
            return
        await move_to_confirm(message, state)
        return
    
    if text == "/skip":
        if photos_required:
            await safe_send(message, "❌ Bu kategoriya uchun rasmlar majburiy! Kamida 1 ta yuboring.")
            return
        await move_to_confirm(message, state)
        return
    
    await safe_send(message, "📷 Rasm yuboring yoki /done, /skip buyruqlaridan foydalaning.")


async def move_to_confirm(message: Message, state: FSMContext):
    """Transition to confirmation step."""
    await state.set_state(AddListing.confirm)
    
    data = await state.get_data()
    
    cat_name = dict(CATEGORIES).get(data.get("category", ""), data.get("category", ""))
    subtype = data.get("subtype")
    subtype_name = dict(HOTEL_SUBTYPES).get(subtype, subtype) if subtype else None
    
    lines = ["📋 <b>Tasdiqlash</b>", "", f"📂 Kategoriya: <b>{h(cat_name)}</b>"]
    
    if subtype_name:
        lines.append(f"🏷 Turi: <b>{h(subtype_name)}</b>")
    
    lines.append(f"📌 Nom: <b>{h(data.get('title', ''))}</b>")
    
    desc = data.get("description")
    if desc:
        lines.append(f"📝 Ta'rif: {h(desc[:50] + '...' if len(desc) > 50 else desc)}")
    
    lines.append("🗺 Hudud: <b>Zomin</b>")
    
    price = data.get("price_from")
    if price:
        lines.append(f"💰 Narx: <b>{price:,} UZS</b>")
    
    phone = data.get("phone")
    if phone:
        lines.append(f"📱 Telefon: <b>{h(phone)}</b>")
    
    lat = data.get("latitude")
    if lat:
        lines.append(f"📍 Joylashuv: <b>{lat:.4f}, {data.get('longitude', 0):.4f}</b>")
    
    photos = data.get("photos", [])
    lines.append(f"📷 Rasmlar: <b>{len(photos)} ta</b>")
    
    lines.extend(["", "👇 Saqlaysizmi?"])
    
    await safe_send(message, "\n".join(lines), reply_markup=kb_confirm())


# =============================================================================
# Step: Save
# =============================================================================

@listing_wizard_router.callback_query(F.data == "wiz:save")
async def step_save(callback: CallbackQuery, state: FSMContext):
    """Save the listing."""
    await callback.answer()
    
    data = await state.get_data()
    
    listing_id = await db.create_listing({
        "region": data.get("region", "zomin"),
        "category": data.get("category"),
        "subtype": data.get("subtype"),
        "title": data.get("title"),
        "description": data.get("description"),
        "price_from": data.get("price_from"),
        "currency": "UZS",
        "phone": data.get("phone"),
        "telegram_admin_id": data.get("admin_id"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "photos": data.get("photos", []),
    })
    
    await state.clear()
    
    if listing_id:
        await safe_edit(
            callback.message,
            f"✅ <b>Saqlandi!</b>\n\n"
            f"📌 {h(data.get('title', ''))}\n"
            f"🆔 ID: <code>{listing_id[:8]}...</code>\n\n"
            f"📋 Listinglaringiz: /my_listings",
        )
    else:
        await safe_edit(callback.message, "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")


# =============================================================================
# Cancel
# =============================================================================

@listing_wizard_router.callback_query(F.data == "wiz:cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    """Cancel via inline button."""
    await callback.answer()
    await state.clear()
    await safe_edit(callback.message, "❌ Bekor qilindi.")


async def cancel_wizard(message: Message, state: FSMContext):
    """Cancel the wizard."""
    await state.clear()
    await safe_send(message, "❌ Wizard bekor qilindi.")


@listing_wizard_router.message(Command("cancel"), StateFilter(AddListing))
async def cmd_cancel(message: Message, state: FSMContext):
    """Handle /cancel command during wizard."""
    await cancel_wizard(message, state)


# =============================================================================
# /my_listings
# =============================================================================

@listing_wizard_router.message(Command("my_listings"))
async def cmd_my_listings(message: Message):
    """List current user's listings. Admin-only (enforced by router filter)."""
    user_id = message.from_user.id
    listings = await db.fetch_listings_by_admin(user_id)
    
    if not listings:
        await safe_send(message, "📭 Sizda hali listinglar yo'q.\n\nYangi qo'shish: /add")
        return
    
    lines = [f"📋 <b>Sizning listinglaringiz</b> ({len(listings)} ta)", ""]
    
    cat_emoji = {"hotel": "🏨", "guide": "🧑‍💼", "taxi": "🚕", "place": "📍"}
    
    for lst in listings[:10]:
        status = "🟢" if lst["is_active"] else "🔴"
        emoji = cat_emoji.get(lst["category"], "📦")
        lines.append(f"{status} {emoji} <b>{h(lst['title'])}</b>")
        lines.append(f"   ID: <code>{lst['id'][:8]}</code>")
    
    if len(listings) > 10:
        lines.append(f"\n... va yana {len(listings) - 10} ta")
    
    await safe_send(message, "\n".join(lines), reply_markup=kb_my_listings(listings))


# =============================================================================
# My Listings Actions
# =============================================================================

@listing_wizard_router.callback_query(F.data.startswith("myl:view:"))
async def myl_view(callback: CallbackQuery):
    """View a single listing."""
    await callback.answer()
    
    lid_short = callback.data.split(":")[2]
    user_id = callback.from_user.id
    
    listings = await db.fetch_listings_by_admin(user_id)
    listing = next((l for l in listings if l["id"].startswith(lid_short)), None)
    
    if not listing:
        await safe_edit(callback.message, "❌ Listing topilmadi.")
        return
    
    status = "🟢 Aktiv" if listing["is_active"] else "🔴 O'chirilgan"
    cat_names = {"hotel": "Mehmonxona", "guide": "Gid", "taxi": "Taxi", "place": "Joy"}
    
    lines = [
        f"📌 <b>{h(listing['title'])}</b>",
        "",
        f"📂 {cat_names.get(listing['category'], listing['category'])}",
        f"📊 {status}",
    ]
    
    if listing.get("price_from"):
        lines.append(f"💰 {listing['price_from']:,} {listing.get('currency', 'UZS')}")
    
    if listing.get("phone"):
        lines.append(f"📱 {h(listing['phone'])}")
    
    if listing.get("latitude"):
        lines.append(f"📍 {listing['latitude']:.4f}, {listing['longitude']:.4f}")
    
    photos = listing.get("photos", [])
    lines.append(f"📷 Rasmlar: {len(photos)} ta")
    lines.append(f"\n🆔 <code>{listing['id']}</code>")
    
    await safe_edit(
        callback.message,
        "\n".join(lines),
        reply_markup=kb_listing_actions(listing["id"], listing["is_active"]),
    )


@listing_wizard_router.callback_query(F.data.startswith("myl:toggle:"))
async def myl_toggle(callback: CallbackQuery):
    """Toggle listing active status."""
    await callback.answer()
    
    lid_short = callback.data.split(":")[2]
    user_id = callback.from_user.id
    
    listings = await db.fetch_listings_by_admin(user_id)
    listing = next((l for l in listings if l["id"].startswith(lid_short)), None)
    
    if not listing:
        await safe_edit(callback.message, "❌ Listing topilmadi.")
        return
    
    new_status = not listing["is_active"]
    success = await db.toggle_listing_active(listing["id"], new_status)
    
    if success:
        status_text = "yoqildi ✅" if new_status else "o'chirildi 🔴"
        await safe_edit(
            callback.message,
            f"Listing {status_text}\n\n📌 {h(listing['title'])}",
            reply_markup=kb_listing_actions(listing["id"], new_status),
        )
    else:
        await safe_edit(callback.message, "❌ Xatolik yuz berdi.")


@listing_wizard_router.callback_query(F.data.startswith("myl:del:"))
async def myl_delete_confirm(callback: CallbackQuery):
    """Confirm deletion."""
    await callback.answer()
    
    lid_short = callback.data.split(":")[2]
    
    await safe_edit(
        callback.message,
        "⚠️ <b>O'chirishni tasdiqlang</b>\n\nBu amalni bekor qilib bo'lmaydi!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha", callback_data=f"myl:delok:{lid_short}"),
                InlineKeyboardButton(text="❌ Yo'q", callback_data="myl:back"),
            ]
        ]),
    )


@listing_wizard_router.callback_query(F.data.startswith("myl:delok:"))
async def myl_delete_execute(callback: CallbackQuery):
    """Execute deletion."""
    await callback.answer()
    
    lid_short = callback.data.split(":")[2]
    user_id = callback.from_user.id
    
    listings = await db.fetch_listings_by_admin(user_id)
    listing = next((l for l in listings if l["id"].startswith(lid_short)), None)
    
    if not listing:
        await safe_edit(callback.message, "❌ Listing topilmadi.")
        return
    
    success = await db.delete_listing(listing["id"])
    
    if success:
        await safe_edit(callback.message, f"🗑 <b>O'chirildi!</b>\n\n📌 {h(listing['title'])}")
    else:
        await safe_edit(callback.message, "❌ Xatolik yuz berdi.")


@listing_wizard_router.callback_query(F.data == "myl:back")
async def myl_back(callback: CallbackQuery):
    """Go back to listings list."""
    await callback.answer()
    
    user_id = callback.from_user.id
    listings = await db.fetch_listings_by_admin(user_id)
    
    if not listings:
        await safe_edit(callback.message, "📭 Listinglar yo'q.")
        return
    
    lines = [f"📋 <b>Sizning listinglaringiz</b> ({len(listings)} ta)", ""]
    
    cat_emoji = {"hotel": "🏨", "guide": "🧑‍💼", "taxi": "🚕", "place": "📍"}
    
    for lst in listings[:10]:
        status = "🟢" if lst["is_active"] else "🔴"
        emoji = cat_emoji.get(lst["category"], "📦")
        lines.append(f"{status} {emoji} <b>{h(lst['title'])}</b>")
        lines.append(f"   ID: <code>{lst['id'][:8]}</code>")
    
    await safe_edit(callback.message, "\n".join(lines), reply_markup=kb_my_listings(listings))
