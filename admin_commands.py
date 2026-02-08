"""
Admin-only commands router.
Provides /orders, /order, /find, /filter, /export, /health commands.
"""
import io
import os
import time
from aiogram import Router, Bot
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command, CommandObject

from config import ADMINS, get_startup_info
from admin_keyboards import get_order_status_keyboard, STATUS_DISPLAY
import db
from i18n import t
from export_utils import generate_orders_csv

# Create router for admin commands
admin_router = Router()


def is_admin(user_id: int) -> bool:
    """Check if user is an admin."""
    return user_id in ADMINS


def format_order_short(order: dict) -> str:
    """Format order as short summary for list view."""
    return (
        f"📦 <b>#{order['id']}</b> | {STATUS_DISPLAY.get(order['status'], order['status'])}\n"
        f"   {order['service']}\n"
        f"   👤 {order['name']} | 📱 {order['phone']}\n"
        f"   📅 {order['date_text']}\n"
        f"   🕐 {order['created_at']}"
    )


def format_order_full(order: dict) -> str:
    """Format order with full details."""
    return (
        f"📦 <b>Buyurtma #{order['id']}</b>\n\n"
        f"🏷 <b>Xizmat:</b> {order['service']}\n"
        f"👤 <b>Mijoz:</b> {order['name']}\n"
        f"📱 <b>Telefon:</b> {order['phone']}\n"
        f"📅 <b>Sana/vaqt:</b> {order['date_text']}\n"
        f"📝 <b>Qo'shimcha:</b> {order['details']}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 User ID: {order['user_id']}\n"
        f"👤 Username: @{order['username'] or 'N/A'}\n"
        f"📊 Status: {STATUS_DISPLAY.get(order['status'], order['status'])}\n"
        f"🕐 Yaratilgan: {order['created_at']}\n"
        f"🔄 Yangilangan: {order['updated_at']}"
    )


# ============== /orders COMMAND ==============

@admin_router.message(Command("orders"))
async def cmd_orders(message: Message, command: CommandObject):
    """
    Show orders list.
    Usage: /orders [status] [page]
    """
    if not is_admin(message.from_user.id):
        lang = db.get_user_lang(message.from_user.id)
        await message.answer(t("no_access", lang))
        return
    
    args = command.args.split() if command.args else []
    
    # Parse arguments
    status = None
    page = 1
    
    valid_statuses = ("new", "accepted", "contacted", "done")
    
    for arg in args:
        if arg.lower() in valid_statuses:
            status = arg.lower()
        elif arg.isdigit():
            page = max(1, int(arg))
    
    # Calculate offset
    limit = 10
    offset = (page - 1) * limit
    
    # Get orders
    orders = db.get_orders(status=status, limit=limit, offset=offset)
    total = db.get_orders_count(status=status)
    
    if not orders:
        status_text = f" ({status})" if status else ""
        await message.answer(f"📭 Buyurtmalar topilmadi{status_text}.")
        return
    
    # Format response
    total_pages = (total + limit - 1) // limit
    status_text = f" [{status.upper()}]" if status else ""
    
    header = f"📋 <b>Buyurtmalar{status_text}</b> (sahifa {page}/{total_pages}, jami: {total})\n\n"
    
    order_texts = [format_order_short(order) for order in orders]
    
    footer = f"\n\n💡 <i>/order &lt;id&gt; - to'liq ma'lumot</i>"
    if total_pages > 1:
        status_arg = status if status else ""
        footer += f"\n<i>/orders {status_arg} {page+1} - keyingi sahifa</i>"
    
    await message.answer(
        header + "\n\n".join(order_texts) + footer,
        parse_mode="HTML",
    )


# ============== /order <id> COMMAND ==============

@admin_router.message(Command("order"))
async def cmd_order_detail(message: Message, command: CommandObject):
    """
    Show single order details with status buttons.
    Usage: /order <id>
    """
    if not is_admin(message.from_user.id):
        lang = db.get_user_lang(message.from_user.id)
        await message.answer(t("no_access", lang))
        return
    
    if not command.args or not command.args.strip().isdigit():
        await message.answer(
            "❓ <b>Foydalanish:</b> /order &lt;id&gt;\n"
            "Misol: /order 123",
            parse_mode="HTML",
        )
        return
    
    order_id = int(command.args.strip())
    order = db.get_order_by_id(order_id)
    
    if not order:
        await message.answer(f"❌ Buyurtma #{order_id} topilmadi.")
        return
    
    await message.answer(
        format_order_full(order),
        parse_mode="HTML",
        reply_markup=get_order_status_keyboard(order_id),
    )


# ============== /find COMMAND ==============

@admin_router.message(Command("find"))
async def cmd_find(message: Message, command: CommandObject):
    """
    Search orders by query.
    Usage: /find <query>
    """
    if not is_admin(message.from_user.id):
        lang = db.get_user_lang(message.from_user.id)
        await message.answer(t("no_access", lang))
        return
    
    if not command.args or len(command.args.strip()) < 2:
        await message.answer(
            "🔍 <b>Qidiruv:</b> /find &lt;so'rov&gt;\n"
            "Misol: /find Ali\n\n"
            "Qidiruv: ism, telefon, xizmat, izoh, username bo'yicha.",
            parse_mode="HTML",
        )
        return
    
    query = command.args.strip()
    orders = db.search_orders(query, limit=10)
    
    if not orders:
        await message.answer(f"🔍 \"{query}\" bo'yicha hech narsa topilmadi.")
        return
    
    header = f"🔍 <b>Qidiruv natijalari:</b> \"{query}\" ({len(orders)} ta)\n\n"
    order_texts = [format_order_short(order) for order in orders]
    
    await message.answer(
        header + "\n\n".join(order_texts),
        parse_mode="HTML",
    )


# ============== /filter COMMAND ==============

@admin_router.message(Command("filter"))
async def cmd_filter(message: Message, command: CommandObject):
    """
    Filter orders by service or date.
    Usage: /filter service <value>
           /filter date <value>
    """
    if not is_admin(message.from_user.id):
        lang = db.get_user_lang(message.from_user.id)
        await message.answer(t("no_access", lang))
        return
    
    if not command.args:
        await message.answer(
            "🏷 <b>Filtrlash:</b>\n\n"
            "/filter service &lt;qiymat&gt;\n"
            "Misol: /filter service mehmonxona\n\n"
            "/filter date &lt;qiymat&gt;\n"
            "Misol: /filter date 2025-01",
            parse_mode="HTML",
        )
        return
    
    parts = command.args.split(maxsplit=1)
    
    if len(parts) < 2:
        await message.answer("❓ Qiymat kiriting. Misol: /filter service mehmonxona")
        return
    
    filter_type = parts[0].lower()
    value = parts[1].strip()
    
    if len(value) < 2:
        await message.answer("❓ Qiymat juda qisqa. Kamida 2 ta belgi kiriting.")
        return
    
    if filter_type == "service":
        orders = db.filter_orders_by_service(value, limit=10)
        filter_label = f"xizmat: \"{value}\""
    elif filter_type == "date":
        orders = db.filter_orders_by_date(value, limit=10)
        filter_label = f"sana: \"{value}\""
    else:
        await message.answer("❓ Noto'g'ri filtr turi. Foydalaning: service yoki date")
        return
    
    if not orders:
        await message.answer(f"🏷 {filter_label} bo'yicha hech narsa topilmadi.")
        return
    
    header = f"🏷 <b>Filtr:</b> {filter_label} ({len(orders)} ta)\n\n"
    order_texts = [format_order_short(order) for order in orders]
    
    await message.answer(
        header + "\n\n".join(order_texts),
        parse_mode="HTML",
    )


# ============== /export COMMAND ==============

@admin_router.message(Command("export"))
async def cmd_export(message: Message, command: CommandObject):
    """
    Export orders to CSV file.
    Usage: /export [status]
    """
    if not is_admin(message.from_user.id):
        lang = db.get_user_lang(message.from_user.id)
        await message.answer(t("no_access", lang))
        return
    
    # Parse optional status argument
    status = None
    valid_statuses = ("new", "accepted", "contacted", "done")
    
    if command.args:
        arg = command.args.strip().lower()
        if arg in valid_statuses:
            status = arg
        else:
            await message.answer(
                "📊 <b>Eksport:</b> /export [status]\n\n"
                "Statuslar: new, accepted, contacted, done\n"
                "Misol: /export new\n"
                "Hammasi: /export",
                parse_mode="HTML",
            )
            return
    
    # Generate CSV
    try:
        filename, csv_bytes = generate_orders_csv(status)
        
        # Check if there's data
        if len(csv_bytes) < 100:  # Just header, no data
            status_text = f" ({status})" if status else ""
            await message.answer(f"📭 Eksport qilish uchun buyurtmalar yo'q{status_text}.")
            return
        
        # Send as document
        document = BufferedInputFile(csv_bytes, filename=filename)
        
        status_text = f" [{status.upper()}]" if status else " [BARCHASI]"
        await message.answer_document(
            document=document,
            caption=f"📊 Buyurtmalar eksporti{status_text}",
        )
        
    except Exception as e:
        await message.answer(f"❌ Eksport xatosi: {e}")


# ============== /health COMMAND ==============

@admin_router.message(Command("health"))
async def cmd_health(message: Message):
    """
    Health check command for monitoring.
    Shows bot uptime, version, database status, and FSM storage type.
    """
    if not is_admin(message.from_user.id):
        return  # Silently ignore for non-admins
    
    # Calculate uptime (BOT_START_TIME is set in main.py)
    try:
        from main import BOT_START_TIME
        uptime_secs = int(time.time() - BOT_START_TIME)
        hours, remainder = divmod(uptime_secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"
    except ImportError:
        uptime_str = "unknown"
    
    # Database health check
    try:
        order_count = db.get_orders_count()
        user_count_result = db.get_connection().execute("SELECT COUNT(*) FROM users").fetchone()
        user_count = user_count_result[0] if user_count_result else 0
        db_status = f"✅ OK ({order_count} orders, {user_count} users)"
    except Exception as e:
        db_status = f"❌ Error: {e}"
    
    # Version info
    version_info = get_startup_info()
    
    # FSM storage type
    fsm_storage = "Redis" if os.getenv("REDIS_URL") else "Memory (⚠️ state lost on restart)"
    
    report = (
        f"🏥 <b>Health Check</b>\n\n"
        f"<b>Status:</b> ✅ Running\n"
        f"<b>Uptime:</b> {uptime_str}\n"
        f"<b>Version:</b> {version_info}\n"
        f"<b>Database:</b> {db_status}\n"
        f"<b>FSM Storage:</b> {fsm_storage}\n"
        f"<b>Admins:</b> {len(ADMINS)}"
    )
    
    await message.answer(report, parse_mode="HTML")


# ============== /partners COMMAND ==============

@admin_router.message(Command("partners"))
async def cmd_partners(message: Message):
    """
    List all partners for admin (grouped by type).
    Shows connection status and connect_code.
    """
    if not is_admin(message.from_user.id):
        return
    
    try:
        import db_postgres as db_pg
        partners = await db_pg.get_all_partners()
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
        return
    
    if not partners:
        await message.answer("📭 Partnerlar topilmadi.")
        return
    
    # Group by type
    by_type: dict[str, list] = {}
    for p in partners:
        ptype = p["type"]
        if ptype not in by_type:
            by_type[ptype] = []
        by_type[ptype].append(p)
    
    type_emoji = {"guide": "🧑‍💼", "taxi": "🚕", "hotel": "🏨"}
    
    lines = ["<b>📋 Partnerlar ro'yxati</b>\n"]
    
    for ptype, plist in by_type.items():
        emoji = type_emoji.get(ptype, "📦")
        lines.append(f"\n{emoji} <b>{ptype.upper()}</b> ({len(plist)} ta)")
        
        for p in plist:
            status = "✅" if p["telegram_id"] else "⏳"
            active = "🟢" if p["is_active"] else "🔴"
            lines.append(
                f"  {status}{active} {p['display_name']}\n"
                f"      Kod: <code>{p['connect_code']}</code>\n"
                f"      ID: <code>{p['id'][:8]}...</code>"
            )
    
    await message.answer("\n".join(lines), parse_mode="HTML")


# ============== /admin_health COMMAND ==============

@admin_router.message(Command("admin_health"))
async def cmd_admin_health(message: Message):
    """
    Comprehensive health check for admins.
    Shows DB connectivity, partner counts by type, and top partners.
    """
    if not is_admin(message.from_user.id):
        return
    
    import db_postgres as db_pg
    
    lines = ["<b>🏥 Admin Health Check</b>\n"]
    
    # PostgreSQL connectivity
    pg_ok, pg_msg = await db_pg.healthcheck()
    lines.append(f"<b>PostgreSQL:</b> {'✅' if pg_ok else '❌'} {pg_msg}")
    
    if not pg_ok:
        lines.append("\n⚠️ <b>Database connection failed!</b>")
        lines.append("Check DATABASE_URL and ensure PostgreSQL is running.")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return
    
    # Get all partners
    all_partners = await db_pg.get_all_partners()
    
    # Count by type
    by_type: dict[str, list] = {"guide": [], "taxi": [], "hotel": []}
    for p in all_partners:
        ptype = p.get("type", "unknown")
        if ptype in by_type:
            by_type[ptype].append(p)
    
    lines.append(f"\n<b>📊 Partners Summary:</b>")
    lines.append(f"  Total: {len(all_partners)}")
    
    for ptype, plist in by_type.items():
        active = len([p for p in plist if p.get("is_active")])
        connected = len([p for p in plist if p.get("telegram_id")])
        emoji = {"guide": "🧑‍💼", "taxi": "🚕", "hotel": "🏨"}.get(ptype, "📦")
        lines.append(f"  {emoji} {ptype}: {len(plist)} total, {active} active, {connected} connected")
    
    # Top 3 per type
    for ptype, plist in by_type.items():
        if not plist:
            continue
        emoji = {"guide": "🧑‍💼", "taxi": "🚕", "hotel": "🏨"}.get(ptype, "📦")
        lines.append(f"\n{emoji} <b>{ptype.upper()} (top 3):</b>")
        for p in plist[:3]:
            status = "✅" if p.get("telegram_id") else "❌"
            active = "🟢" if p.get("is_active") else "🔴"
            lines.append(
                f"  {status}{active} {p['display_name']}\n"
                f"      ID: <code>{p['id'][:8]}</code> | Code: <code>{p['connect_code']}</code>"
            )
    
    # Warnings
    if len(all_partners) == 0:
        lines.append("\n⚠️ <b>No partners found!</b>")
        lines.append("Run /seed_partners to create sample partners.")
    
    total_active = len([p for p in all_partners if p.get("is_active")])
    if total_active == 0 and len(all_partners) > 0:
        lines.append("\n⚠️ <b>All partners are inactive!</b>")
        lines.append("Check is_active column in database.")
    
    await message.answer("\n".join(lines), parse_mode="HTML")


# ============== /seed_partners COMMAND ==============

@admin_router.message(Command("seed_partners"))
async def cmd_seed_partners(message: Message):
    """
    Seed sample partners (4 guides, 5 taxis, 2 hotels).
    Uses upsert by connect_code, safe to run multiple times.
    """
    if not is_admin(message.from_user.id):
        return
    
    import db_postgres as db_pg
    
    await message.answer("🔄 Seeding partners...")
    
    # Sample guides
    sample_guides = [
        {"display_name": "Akmal - Samarqand gidi", "connect_code": "GUIDE-001"},
        {"display_name": "Dilshod - Buxoro gidi", "connect_code": "GUIDE-002"},
        {"display_name": "Malika - Xiva gidi", "connect_code": "GUIDE-003"},
        {"display_name": "Jasur - Toshkent gidi", "connect_code": "GUIDE-004"},
    ]
    
    # Sample taxis
    sample_taxis = [
        {"display_name": "Tez Taksi - Toshkent", "connect_code": "TAXI-001"},
        {"display_name": "Samarqand Express", "connect_code": "TAXI-002"},
        {"display_name": "Buxoro Taksi", "connect_code": "TAXI-003"},
        {"display_name": "Xiva Transport", "connect_code": "TAXI-004"},
        {"display_name": "Farg'ona Taksi", "connect_code": "TAXI-005"},
    ]
    
    # Sample hotels with location
    sample_hotels = [
        {
            "display_name": "Hotel Ichan Qala - Xiva",
            "connect_code": "HOTEL-001",
            "latitude": 41.378889,
            "longitude": 60.363889,
            "address": "Xiva, Ichan Qala, Pahlavon Mahmud ko'chasi",
        },
        {
            "display_name": "Samarqand Registan Plaza",
            "connect_code": "HOTEL-002",
            "latitude": 39.654167,
            "longitude": 66.959722,
            "address": "Samarqand, Registon maydoni yaqinida",
        },
    ]
    
    try:
        count = await db_pg.seed_partners(sample_guides, sample_taxis, sample_hotels)
        
        # Fetch and show results
        all_partners = await db_pg.get_all_partners()
        
        lines = [f"✅ <b>Seeded {count} partners</b>\n"]
        
        by_type: dict[str, list] = {"guide": [], "taxi": [], "hotel": []}
        for p in all_partners:
            ptype = p.get("type", "unknown")
            if ptype in by_type:
                by_type[ptype].append(p)
        
        for ptype, plist in by_type.items():
            emoji = {"guide": "🧑‍💼", "taxi": "🚕", "hotel": "🏨"}.get(ptype, "📦")
            lines.append(f"\n{emoji} <b>{ptype.upper()}</b> ({len(plist)} ta)")
            for p in plist:
                lines.append(f"  • {p['display_name']}")
                lines.append(f"    Code: <code>{p['connect_code']}</code>")
        
        lines.append("\n\n💡 Partners can connect via: /connect <code>")
        
        await message.answer("\n".join(lines), parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Seeding failed: {e}")



