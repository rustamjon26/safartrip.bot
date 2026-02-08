"""
user_cms_router.py - User browsing and booking flow for CMS listings.

Flow:
1. Region selection (only "Zomin" for now)
2. Category selection: Mehmonxona, Gid, Taxi, Diqqatga sazovor joy
3. Subtype selection (for hotels): Shale, Uy mehmonxona, Mehmonxona, Dacha
4. Listing cards with photos
5. Listing details + "Bron qilish" button
6. Booking form: full_name -> phone -> date(s) -> confirm
7. Booking dispatch with 5-minute timeout
"""

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
from aiogram.filters import Command

import db_postgres as db_pg
from html_utils import h, safe_send, safe_edit, safe_send_photo
from keyboards import get_main_menu, get_cancel_keyboard

logger = logging.getLogger(__name__)

user_cms_router = Router()


# =============================================================================
# FSM States
# =============================================================================

class CMSBrowsing(StatesGroup):
    """States for CMS browsing flow."""
    region = State()
    category = State()
    subtype = State()
    browsing = State()
    listing_detail = State()


class CMSBookingForm(StatesGroup):
    """States for booking form."""
    full_name = State()
    phone = State()
    dates = State()
    confirm = State()


# =============================================================================
# Constants
# =============================================================================

REGIONS = [
    ("zomin", "🏔 Zomin"),
]

CATEGORIES = [
    ("hotel", "🏨 Mehmonxona"),
    ("guide", "🧑‍💼 Gid"),
    ("taxi", "🚕 Taxi"),
    ("place", "🎡 Diqqatga sazovor joy"),
]

HOTEL_SUBTYPES = [
    ("shale", "🏔 Shale"),
    ("uy mehmonxona", "🏠 Uy mehmonxona"),
    ("mehmonxona", "🏨 Mehmonxona"),
    ("dacha", "🏡 Dacha"),
]

CATEGORY_NAMES = {
    "hotel": "Mehmonxona",
    "guide": "Gid",
    "taxi": "Taxi",
    "place": "Diqqatga sazovor joy",
}


# =============================================================================
# Keyboards
# =============================================================================

def build_region_keyboard() -> InlineKeyboardMarkup:
    """Build region selection keyboard."""
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"cms:region:{code}")]
        for code, name in REGIONS
    ]
    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cms:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_category_keyboard() -> InlineKeyboardMarkup:
    """Build category selection keyboard."""
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"cms:cat:{code}")]
        for code, name in CATEGORIES
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="cms:back:region")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_subtype_keyboard(category: str) -> InlineKeyboardMarkup:
    """Build subtype selection keyboard for hotels."""
    if category != "hotel":
        return None
    
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"cms:sub:{code}")]
        for code, name in HOTEL_SUBTYPES
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="cms:back:category")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_listing_keyboard(listing_id: str) -> InlineKeyboardMarkup:
    """Build keyboard for a single listing card."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tanlash", callback_data=f"cms:pick:{listing_id}")],
    ])


def build_listing_detail_keyboard(listing_id: str) -> InlineKeyboardMarkup:
    """Build keyboard for listing details page."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Bron qilish", callback_data=f"cms:book:{listing_id}")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="cms:back:listings")],
    ])


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    """Build booking confirmation keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="cms:confirm:yes"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cms:confirm:no"),
        ],
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
# Entry Points
# =============================================================================

@user_cms_router.message(Command("browse"))
@user_cms_router.message(F.text == "🔍 Ko'rish")
async def cmd_browse(message: Message, state: FSMContext):
    """Start the CMS browsing flow."""
    await state.clear()
    await state.set_state(CMSBrowsing.region)
    
    await safe_send(
        message,
        "🗺 <b>Hududni tanlang:</b>\n\n"
        "Qaysi hududda xizmat qidiryapsiz?",
        reply_markup=build_region_keyboard(),
    )


@user_cms_router.message(F.text == "🏔 Zomin")
async def shortcut_zomin(message: Message, state: FSMContext):
    """Shortcut to start browsing Zomin directly."""
    await state.clear()
    await state.update_data(region="zomin")
    await state.set_state(CMSBrowsing.category)
    
    await safe_send(
        message,
        "📂 <b>Kategoriyani tanlang:</b>\n\n"
        "🏔 <b>Zomin</b> hududida qanday xizmat kerak?",
        reply_markup=build_category_keyboard(),
    )


# =============================================================================
# Region Selection
# =============================================================================

@user_cms_router.callback_query(F.data.startswith("cms:region:"))
async def region_selected(callback: CallbackQuery, state: FSMContext):
    """Handle region selection."""
    await callback.answer()
    
    region = callback.data.split(":")[2]
    await state.update_data(region=region)
    await state.set_state(CMSBrowsing.category)
    
    region_name = dict(REGIONS).get(region, region.title())
    
    await safe_edit(
        callback.message,
        f"📂 <b>Kategoriyani tanlang:</b>\n\n"
        f"🏔 <b>{h(region_name)}</b> hududida qanday xizmat kerak?",
        reply_markup=build_category_keyboard(),
    )


# =============================================================================
# Category Selection
# =============================================================================

@user_cms_router.callback_query(F.data.startswith("cms:cat:"))
async def category_selected(callback: CallbackQuery, state: FSMContext):
    """Handle category selection."""
    await callback.answer()
    
    category = callback.data.split(":")[2]
    await state.update_data(category=category)
    
    # If hotel, show subtype selection
    if category == "hotel":
        await state.set_state(CMSBrowsing.subtype)
        await safe_edit(
            callback.message,
            "🏨 <b>Mehmonxona turini tanlang:</b>",
            reply_markup=build_subtype_keyboard(category),
        )
        return
    
    # Otherwise, show listings directly
    await state.set_state(CMSBrowsing.browsing)
    await show_listings(callback.message, state, callback.from_user.id if callback.from_user else 0)


# =============================================================================
# Subtype Selection (Hotels only)
# =============================================================================

@user_cms_router.callback_query(F.data.startswith("cms:sub:"))
async def subtype_selected(callback: CallbackQuery, state: FSMContext):
    """Handle subtype selection for hotels."""
    await callback.answer()
    
    subtype = callback.data.split(":")[2]
    await state.update_data(subtype=subtype)
    await state.set_state(CMSBrowsing.browsing)
    
    await show_listings(callback.message, state, callback.from_user.id if callback.from_user else 0)


# =============================================================================
# Listing Display
# =============================================================================

async def show_listings(message: Message, state: FSMContext, user_id: int):
    """Display listing cards for the selected region/category/subtype."""
    data = await state.get_data()
    region = data.get("region", "zomin")
    category = data.get("category")
    subtype = data.get("subtype")
    
    listings = await db_pg.fetch_listings(region=region, category=category, subtype=subtype)
    
    if not listings:
        cat_name = CATEGORY_NAMES.get(category, category)
        await safe_edit(
            message,
            f"😔 <b>Hozircha {h(cat_name)} xizmatlari mavjud emas.</b>\n\n"
            f"Iltimos, keyinroq qaytadan tekshirib ko'ring.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="cms:back:category")],
            ]),
        )
        return
    
    # Store listing IDs for pagination (future use)
    await state.update_data(listing_ids=[l["id"] for l in listings])
    
    # Edit the original message to show we're loading listings
    cat_name = CATEGORY_NAMES.get(category, category)
    await safe_edit(
        message,
        f"📋 <b>{h(cat_name)}</b> - topildi: {len(listings)} ta\n\n"
        f"Quyidagi variantlardan birini tanlang:",
        reply_markup=None,
    )
    
    # Send each listing as a photo card
    for listing in listings:
        await send_listing_card(message, listing)


async def send_listing_card(message: Message, listing: dict):
    """Send a single listing as a photo card."""
    listing_id = listing["id"]
    title = listing["title"]
    description = listing.get("description") or ""
    price_from = listing.get("price_from")
    rating = listing.get("rating")
    photos = listing.get("photos", [])
    
    # Build caption
    lines = [f"<b>{h(title)}</b>"]
    
    if rating:
        lines.append(f"⭐ {rating:.1f}")
    
    if price_from:
        lines.append(f"💰 {price_from:,} so'm dan")
    
    if description:
        # Truncate description
        short_desc = description[:100] + "..." if len(description) > 100 else description
        lines.append(f"\n{h(short_desc)}")
    
    caption = "\n".join(lines)
    
    # Send photo or text-only card
    if photos and len(photos) > 0:
        try:
            await safe_send_photo(
                message,
                photo=photos[0],
                caption=caption,
                reply_markup=build_listing_keyboard(listing_id),
            )
            return
        except Exception as e:
            logger.warning(f"Failed to send photo for listing {listing_id}: {e}")
    
    # Fallback: text-only card
    await safe_send(
        message,
        caption,
        reply_markup=build_listing_keyboard(listing_id),
    )


# =============================================================================
# Listing Selection and Details
# =============================================================================

@user_cms_router.callback_query(F.data.startswith("cms:pick:"))
async def listing_selected(callback: CallbackQuery, state: FSMContext):
    """Handle listing selection - show details."""
    await callback.answer()
    
    listing_id = callback.data.split(":")[2]
    listing = await db_pg.get_listing(listing_id)
    
    if not listing:
        await callback.answer("❌ Xizmat topilmadi", show_alert=True)
        return
    
    await state.update_data(
        selected_listing_id=listing_id,
        selected_listing_title=listing["title"],
        selected_listing_admin_id=listing["telegram_admin_id"],
    )
    await state.set_state(CMSBrowsing.listing_detail)
    
    # Build details message
    title = listing["title"]
    description = listing.get("description") or "Ma'lumot yo'q"
    price_from = listing.get("price_from")
    rating = listing.get("rating")
    category = listing.get("category")
    subtype = listing.get("subtype")
    
    lines = [f"📌 <b>{h(title)}</b>"]
    
    if rating:
        lines.append(f"⭐ Reyting: {rating:.1f}")
    
    if price_from:
        lines.append(f"💰 Narx: {price_from:,} so'm dan")
    
    cat_name = CATEGORY_NAMES.get(category, category)
    lines.append(f"📂 Kategoriya: {h(cat_name)}")
    
    if subtype:
        lines.append(f"🏷 Turi: {h(subtype.title())}")
    
    lines.append(f"\n📝 <b>Ta'rif:</b>\n{h(description)}")
    lines.append("\n\n👇 Buyurtma berish uchun tugmani bosing:")
    
    details_text = "\n".join(lines)
    
    await safe_send(
        callback.message,
        details_text,
        reply_markup=build_listing_detail_keyboard(listing_id),
    )


# =============================================================================
# Booking Form
# =============================================================================

@user_cms_router.callback_query(F.data.startswith("cms:book:"))
async def start_booking(callback: CallbackQuery, state: FSMContext):
    """Start booking form for the selected listing."""
    await callback.answer()
    
    listing_id = callback.data.split(":")[2]
    listing = await db_pg.get_listing(listing_id)
    
    if not listing:
        await callback.answer("❌ Xizmat topilmadi", show_alert=True)
        return
    
    await state.update_data(
        selected_listing_id=listing_id,
        selected_listing_title=listing["title"],
        selected_listing_admin_id=listing["telegram_admin_id"],
    )
    await state.set_state(CMSBookingForm.full_name)
    
    await safe_edit(
        callback.message,
        f"📝 <b>Buyurtma berish:</b> {h(listing['title'])}\n\n"
        f"👤 Iltimos, to'liq ismingizni kiriting:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cms:cancel")],
        ]),
    )


@user_cms_router.message(CMSBookingForm.full_name)
async def booking_name_entered(message: Message, state: FSMContext):
    """Handle full name input."""
    name = (message.text or "").strip()
    
    if len(name) < 3:
        await safe_send(message, "❌ Iltimos, to'liq ismingizni kiriting (kamida 3 belgi):")
        return
    
    await state.update_data(booking_name=name)
    await state.set_state(CMSBookingForm.phone)
    
    await safe_send(
        message,
        "📱 <b>Telefon raqamingizni kiriting:</b>\n"
        "Misol: +998901234567",
        reply_markup=get_cancel_keyboard(),
    )


@user_cms_router.message(CMSBookingForm.phone)
async def booking_phone_entered(message: Message, state: FSMContext):
    """Handle phone number input."""
    phone = (message.text or "").strip()
    
    # Basic phone validation
    phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if len(phone_clean) < 9:
        await safe_send(message, "❌ Iltimos, to'g'ri telefon raqam kiriting:")
        return
    
    await state.update_data(booking_phone=phone)
    await state.set_state(CMSBookingForm.dates)
    
    await safe_send(
        message,
        "📅 <b>Sana(lar)ni kiriting:</b>\n"
        "Misol: 15-fevral yoki 15-20 fevral",
    )


@user_cms_router.message(CMSBookingForm.dates)
async def booking_dates_entered(message: Message, state: FSMContext):
    """Handle dates input and show confirmation."""
    dates = (message.text or "").strip()
    
    if len(dates) < 3:
        await safe_send(message, "❌ Iltimos, sanani kiriting:")
        return
    
    await state.update_data(booking_dates=dates)
    await state.set_state(CMSBookingForm.confirm)
    
    data = await state.get_data()
    
    confirm_text = (
        "📋 <b>Buyurtmangizni tasdiqlang:</b>\n\n"
        f"🏷 <b>Xizmat:</b> {h(data.get('selected_listing_title', '—'))}\n"
        f"👤 <b>Ism:</b> {h(data.get('booking_name', '—'))}\n"
        f"📱 <b>Telefon:</b> {h(data.get('booking_phone', '—'))}\n"
        f"📅 <b>Sana:</b> {h(dates)}\n\n"
        f"⏱ Diqqat: Partner 5 daqiqa ichida javob berishi kerak."
    )
    
    await safe_send(
        message,
        confirm_text,
        reply_markup=build_confirm_keyboard(),
    )


# =============================================================================
# Booking Confirmation and Dispatch
# =============================================================================

@user_cms_router.callback_query(F.data == "cms:confirm:yes")
async def booking_confirmed(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Handle booking confirmation - create booking and dispatch to partner."""
    await callback.answer()
    
    data = await state.get_data()
    user = callback.from_user
    user_id = user.id if user else 0
    
    listing_id = data.get("selected_listing_id")
    listing_title = data.get("selected_listing_title", "Xizmat")
    admin_id = data.get("selected_listing_admin_id")
    
    if not listing_id or not admin_id:
        await safe_edit(
            callback.message,
            "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
            reply_markup=None,
        )
        await state.clear()
        return
    
    # Build payload
    payload = {
        "name": data.get("booking_name", ""),
        "phone": data.get("booking_phone", ""),
        "dates": data.get("booking_dates", ""),
        "username": f"@{user.username}" if user and user.username else None,
    }
    
    # Create booking with 5-minute expiration
    booking_id = await db_pg.create_listing_booking(
        listing_id=listing_id,
        user_telegram_id=user_id,
        payload=payload,
        expires_minutes=5,
    )
    
    if not booking_id:
        await safe_edit(
            callback.message,
            "❌ Buyurtma yaratishda xatolik. Iltimos, qaytadan urinib ko'ring.",
            reply_markup=None,
        )
        await state.clear()
        return
    
    # Dispatch to partner
    success = await dispatch_to_partner(
        bot=bot,
        booking_id=booking_id,
        admin_id=admin_id,
        listing_title=listing_title,
        payload=payload,
        user=user,
    )
    
    if success:
        await safe_edit(
            callback.message,
            f"✅ <b>Buyurtma yuborildi!</b>\n\n"
            f"🆔 ID: <code>{h(booking_id[:8])}...</code>\n"
            f"🏷 Xizmat: {h(listing_title)}\n\n"
            f"⏱ Partner 5 daqiqa ichida javob beradi.\n"
            f"Agar javob bo'lmasa, sizga xabar beramiz.",
            reply_markup=None,
        )
    else:
        await safe_edit(
            callback.message,
            f"⚠️ <b>Buyurtma yaratildi</b>\n\n"
            f"🆔 ID: <code>{h(booking_id[:8])}...</code>\n\n"
            f"Partner hozirda mavjud emas. "
            f"Biz sizga tez orada xabar beramiz.",
            reply_markup=None,
        )
    
    await state.clear()
    await safe_send(
        callback.message,
        "🏠 Bosh menyu:",
        reply_markup=get_main_menu(),
    )


async def dispatch_to_partner(
    bot: Bot,
    booking_id: str,
    admin_id: int,
    listing_title: str,
    payload: dict,
    user,
) -> bool:
    """
    Send booking request to partner admin.
    
    Returns:
        True if message sent successfully, False otherwise
    """
    user_name = user.full_name if user else "Mijoz"
    user_username = f"@{user.username}" if user and user.username else "—"
    
    message_text = (
        f"📬 <b>YANGI BUYURTMA</b> #{booking_id[:8]}\n\n"
        f"🏷 <b>Xizmat:</b> {h(listing_title)}\n\n"
        f"👤 <b>Mijoz:</b> {h(user_name)}\n"
        f"🆔 <b>Username:</b> {user_username}\n"
        f"📱 <b>Telefon:</b> {h(payload.get('phone', '—'))}\n"
        f"📅 <b>Sana:</b> {h(payload.get('dates', '—'))}\n\n"
        f"⏱ <i>5 daqiqa ichida javob bering!</i>"
    )
    
    try:
        await bot.send_message(
            chat_id=admin_id,
            text=message_text,
            parse_mode="HTML",
            reply_markup=build_partner_action_keyboard(booking_id),
        )
        
        # Mark as sent
        await db_pg.update_listing_booking_sent(booking_id)
        logger.info(f"Booking {booking_id} dispatched to admin {admin_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to dispatch booking {booking_id} to admin {admin_id}: {e}")
        return False


@user_cms_router.callback_query(F.data == "cms:confirm:no")
async def booking_cancelled(callback: CallbackQuery, state: FSMContext):
    """Handle booking cancellation."""
    await callback.answer()
    await state.clear()
    
    await safe_edit(
        callback.message,
        "❌ Buyurtma bekor qilindi.",
        reply_markup=None,
    )
    
    await safe_send(
        callback.message,
        "🏠 Bosh menyu:",
        reply_markup=get_main_menu(),
    )


# =============================================================================
# Navigation: Back buttons and Cancel
# =============================================================================

@user_cms_router.callback_query(F.data == "cms:back:region")
async def back_to_region(callback: CallbackQuery, state: FSMContext):
    """Go back to region selection."""
    await callback.answer()
    await state.set_state(CMSBrowsing.region)
    
    await safe_edit(
        callback.message,
        "🗺 <b>Hududni tanlang:</b>",
        reply_markup=build_region_keyboard(),
    )


@user_cms_router.callback_query(F.data == "cms:back:category")
async def back_to_category(callback: CallbackQuery, state: FSMContext):
    """Go back to category selection."""
    await callback.answer()
    
    data = await state.get_data()
    region = data.get("region", "zomin")
    region_name = dict(REGIONS).get(region, region.title())
    
    await state.set_state(CMSBrowsing.category)
    
    await safe_edit(
        callback.message,
        f"📂 <b>Kategoriyani tanlang:</b>\n\n"
        f"🏔 <b>{h(region_name)}</b> hududida qanday xizmat kerak?",
        reply_markup=build_category_keyboard(),
    )


@user_cms_router.callback_query(F.data == "cms:back:listings")
async def back_to_listings(callback: CallbackQuery, state: FSMContext):
    """Go back to listings view."""
    await callback.answer()
    await state.set_state(CMSBrowsing.browsing)
    
    # Show listings again
    await show_listings(callback.message, state, callback.from_user.id if callback.from_user else 0)


@user_cms_router.callback_query(F.data == "cms:cancel")
async def cancel_browsing(callback: CallbackQuery, state: FSMContext):
    """Cancel the browsing/booking flow."""
    await callback.answer()
    await state.clear()
    
    await safe_edit(
        callback.message,
        "❌ Bekor qilindi.",
        reply_markup=None,
    )
    
    await safe_send(
        callback.message,
        "🏠 Bosh menyu:",
        reply_markup=get_main_menu(),
    )


# =============================================================================
# Cancel via text message
# =============================================================================

@user_cms_router.message(F.text.in_(["❌ Bekor qilish", "/cancel"]))
async def cancel_via_text(message: Message, state: FSMContext):
    """Handle cancel via text message during booking form."""
    current_state = await state.get_state()
    
    if current_state and (current_state.startswith("CMSBookingForm") or current_state.startswith("CMSBrowsing")):
        await state.clear()
        await safe_send(
            message,
            "❌ Bekor qilindi.\n\n🏠 Bosh menyu:",
            reply_markup=get_main_menu(),
        )
