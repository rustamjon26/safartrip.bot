"""
Admin commands router for Telegram bot.

Commands:
- /admin_help - Show admin commands list
- /admin_health - Database health check and partner stats
- /seed_partners - Seed sample partners
- /partners - List all partners
- /connect CODE - Partner connection (non-admin)

All messages use parse_mode=None to avoid HTML/Markdown parse errors.
"""
import logging
from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.filters import Command, CommandObject

from config import ADMINS
import db_postgres as db_pg

logger = logging.getLogger(__name__)

# Create router
router = Router(name="admin_commands")

# Telegram message size limit (safe margin)
MAX_MESSAGE_LENGTH = 4000


# =============================================================================
# HELPERS
# =============================================================================

def is_admin(user_id: int) -> bool:
    """Check if user is an admin."""
    return user_id in ADMINS


def chunk_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split long text into chunks that fit Telegram message limits."""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    lines = text.split("\n")
    current_chunk = ""
    
    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks if chunks else [text[:max_length]]


def safe_get(d: dict, key: str, default=""):
    """Safely get value from dict."""
    try:
        val = d.get(key, default)
        return val if val is not None else default
    except Exception:
        return default


# =============================================================================
# /admin_help
# =============================================================================

@router.message(Command("admin_help"))
async def cmd_admin_help(message: Message):
    """Show admin commands list."""
    if not is_admin(message.from_user.id):
        return
    
    text = """ADMIN COMMANDS

/admin_help - Show this help
/admin_health - Database health check and partner stats
/seed_partners - Seed sample partners (4 guides, 5 taxis, 2 hotels)
/partners - List all partners with details

NON-ADMIN COMMANDS
/connect CODE - Partner connects their Telegram account"""
    
    await message.answer(text, parse_mode=None)


# =============================================================================
# /admin_health
# =============================================================================

@router.message(Command("admin_health"))
async def cmd_admin_health(message: Message):
    """Database health check and partner statistics."""
    if not is_admin(message.from_user.id):
        return
    
    lines = ["🏥 ADMIN HEALTH CHECK", ""]
    
    # PostgreSQL connectivity
    try:
        pg_ok, pg_msg = await db_pg.healthcheck()
        status = "✅" if pg_ok else "❌"
        lines.append(f"PostgreSQL: {status} {pg_msg}")
    except Exception as e:
        lines.append(f"PostgreSQL: ❌ Error: {e}")
        await message.answer("\n".join(lines), parse_mode=None)
        return
    
    if not pg_ok:
        lines.append("")
        lines.append("⚠️ Database connection failed!")
        lines.append("Check DATABASE_URL and ensure PostgreSQL is running.")
        await message.answer("\n".join(lines), parse_mode=None)
        return
    
    # Get all partners
    try:
        all_partners = await db_pg.get_all_partners()
    except Exception as e:
        lines.append(f"Error fetching partners: {e}")
        await message.answer("\n".join(lines), parse_mode=None)
        return
    
    # Count by type
    by_type: dict[str, list] = {"guide": [], "taxi": [], "hotel": []}
    for p in all_partners:
        ptype = safe_get(p, "type", "unknown").lower()
        if ptype in by_type:
            by_type[ptype].append(p)
    
    lines.append("")
    lines.append("📊 PARTNERS SUMMARY")
    lines.append(f"  Total: {len(all_partners)}")
    
    type_emoji = {"guide": "🧑‍💼", "taxi": "🚕", "hotel": "🏨"}
    
    for ptype, plist in by_type.items():
        active = len([p for p in plist if safe_get(p, "is_active", False)])
        connected = len([p for p in plist if safe_get(p, "telegram_id")])
        emoji = type_emoji.get(ptype, "📦")
        lines.append(f"  {emoji} {ptype}: {len(plist)} total, {active} active, {connected} connected")
    
    # Top 3 per type
    for ptype, plist in by_type.items():
        if not plist:
            continue
        emoji = type_emoji.get(ptype, "📦")
        lines.append("")
        lines.append(f"{emoji} {ptype.upper()} (top 3):")
        
        for p in plist[:3]:
            tid = safe_get(p, "telegram_id")
            is_active = safe_get(p, "is_active", False)
            
            connected_icon = "✅" if tid else "❌"
            active_icon = "🟢" if is_active else "🔴"
            name = safe_get(p, "display_name", "Unknown")
            pid = safe_get(p, "id", "????????")[:8]
            code = safe_get(p, "connect_code", "N/A")
            
            lines.append(f"  {connected_icon}{active_icon} {name}")
            lines.append(f"      ID: {pid} | Code: {code}")
    
    # Warnings
    if len(all_partners) == 0:
        lines.append("")
        lines.append("⚠️ No partners found!")
        lines.append("Run /seed_partners to create sample partners.")
    
    total_active = len([p for p in all_partners if safe_get(p, "is_active", False)])
    if total_active == 0 and len(all_partners) > 0:
        lines.append("")
        lines.append("⚠️ All partners are inactive!")
        lines.append("Check is_active column in database.")
    
    await message.answer("\n".join(lines), parse_mode=None)


# =============================================================================
# /seed_partners
# =============================================================================

@router.message(Command("seed_partners"))
async def cmd_seed_partners(message: Message):
    """Seed sample partners into database."""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer("🔄 Seeding partners...", parse_mode=None)
    
    try:
        result = await db_pg.seed_partners_default()
        
        if result and isinstance(result, dict):
            inserted = result.get("inserted", "?")
            updated = result.get("updated", "?")
            total = result.get("total", "?")
            text = f"✅ Seeding completed!\n\nInserted: {inserted}\nUpdated: {updated}\nTotal: {total}"
        else:
            # seed_partners returned None or non-dict
            text = "✅ Seeding completed!"
        
        # List partners after seeding
        try:
            all_partners = await db_pg.get_all_partners()
            if all_partners:
                text += f"\n\nPartners in database: {len(all_partners)}"
                
                by_type: dict[str, list] = {"guide": [], "taxi": [], "hotel": []}
                for p in all_partners:
                    ptype = safe_get(p, "type", "unknown").lower()
                    if ptype in by_type:
                        by_type[ptype].append(p)
                
                type_emoji = {"guide": "🧑‍💼", "taxi": "🚕", "hotel": "🏨"}
                for ptype, plist in by_type.items():
                    if plist:
                        emoji = type_emoji.get(ptype, "📦")
                        text += f"\n\n{emoji} {ptype.upper()} ({len(plist)}):"
                        for p in plist:
                            name = safe_get(p, "display_name", "Unknown")
                            code = safe_get(p, "connect_code", "N/A")
                            text += f"\n  • {name}"
                            text += f"\n    Code: {code}"
                
                text += "\n\n💡 Partners can connect via: /connect CODE"
        except Exception as e:
            logger.error(f"Error listing partners after seed: {e}")
        
        await message.answer(text, parse_mode=None)
        
    except Exception as e:
        logger.error(f"Error seeding partners: {e}")
        await message.answer(f"❌ Seeding failed: {e}", parse_mode=None)


# =============================================================================
# /partners
# =============================================================================

@router.message(Command("partners"))
async def cmd_partners(message: Message):
    """List all partners with details."""
    if not is_admin(message.from_user.id):
        return
    
    try:
        all_partners = await db_pg.get_all_partners()
    except Exception as e:
        await message.answer(f"❌ Error fetching partners: {e}", parse_mode=None)
        return
    
    if not all_partners:
        await message.answer("📭 No partners found. Run /seed_partners to create sample partners.", parse_mode=None)
        return
    
    # Group by type
    by_type: dict[str, list] = {"guide": [], "taxi": [], "hotel": []}
    for p in all_partners:
        ptype = safe_get(p, "type", "unknown").lower()
        if ptype in by_type:
            by_type[ptype].append(p)
        else:
            by_type.setdefault("other", []).append(p)
    
    lines = [f"📋 PARTNERS LIST ({len(all_partners)} total)", ""]
    
    type_emoji = {"guide": "🧑‍💼", "taxi": "🚕", "hotel": "🏨", "other": "📦"}
    
    for ptype in ["guide", "taxi", "hotel", "other"]:
        plist = by_type.get(ptype, [])
        if not plist:
            continue
        
        # Sort by display_name
        plist.sort(key=lambda x: safe_get(x, "display_name", "").lower())
        
        emoji = type_emoji.get(ptype, "📦")
        lines.append(f"{emoji} {ptype.upper()} ({len(plist)})")
        lines.append("-" * 30)
        
        for p in plist:
            tid = safe_get(p, "telegram_id")
            is_active = safe_get(p, "is_active", False)
            
            connected_icon = "✅" if tid else "❌"
            active_icon = "🟢" if is_active else "🔴"
            name = safe_get(p, "display_name", "Unknown")
            pid = safe_get(p, "id", "????????")[:8]
            code = safe_get(p, "connect_code", "N/A")
            
            lines.append(f"{active_icon}{connected_icon} [{ptype}] {name}")
            lines.append(f"   ID: {pid}...")
            lines.append(f"   Code: {code}")
            lines.append(f"   Telegram: {tid or 'Not connected'}")
            
            # Location info for hotels
            lat = safe_get(p, "latitude")
            lng = safe_get(p, "longitude")
            addr = safe_get(p, "address")
            
            if lat and lng:
                lines.append(f"   Location: {lat}, {lng}")
            if addr:
                lines.append(f"   Address: {addr}")
            
            lines.append("")
    
    # Chunk and send
    full_text = "\n".join(lines)
    chunks = chunk_message(full_text)
    
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            header = f"[{i+1}/{len(chunks)}]\n\n"
            chunk = header + chunk
        await message.answer(chunk, parse_mode=None)


# =============================================================================
# /connect CODE
# =============================================================================

@router.message(Command("connect"))
async def cmd_connect(message: Message, command: CommandObject):
    """Partner connects their Telegram account using a connect code."""
    code = command.args.strip() if command.args else ""
    
    if not code:
        await message.answer(
            "Usage: /connect YOUR_CODE\n\n"
            "Example: /connect GUIDE-001\n\n"
            "The code was provided to you when you registered as a partner.",
            parse_mode=None
        )
        return
    
    user_id = message.from_user.id
    
    try:
        result = await db_pg.connect_partner(code, user_id)
        
        if result:
            name = safe_get(result, "display_name", "Partner")
            ptype = safe_get(result, "type", "unknown")
            
            await message.answer(
                f"✅ Successfully connected!\n\n"
                f"Name: {name}\n"
                f"Type: {ptype}\n"
                f"Telegram ID: {user_id}\n\n"
                "You will now receive booking requests.",
                parse_mode=None
            )
            logger.info(f"Partner connected: {name} ({ptype}) -> {user_id}")
        else:
            await message.answer(
                "❌ Connection failed.\n\n"
                "Possible reasons:\n"
                "• Invalid code\n"
                "• Partner is inactive\n"
                "• Code already used by another account\n\n"
                "Please check your code and try again, or contact support.",
                parse_mode=None
            )
            
    except Exception as e:
        logger.error(f"Error connecting partner: {e}")
        await message.answer(f"❌ Error: {e}", parse_mode=None)


# =============================================================================
# /test_hotel_location (bonus admin command)
# =============================================================================

@router.message(Command("test_hotel_location"))
async def cmd_test_hotel_location(message: Message, command: CommandObject, bot: Bot):
    """Test hotel location sending by code or ID."""
    if not is_admin(message.from_user.id):
        return
    
    code = command.args.strip() if command.args else ""
    if not code:
        await message.answer("Usage: /test_hotel_location HOTEL-001", parse_mode=None)
        return
    
    # Try by connect_code first, then by UUID
    partner = await db_pg.get_partner_by_code(code)
    if not partner:
        partner = await db_pg.get_partner_by_id(code)
    
    if not partner:
        await message.answer(f"Partner not found: {code}", parse_mode=None)
        return
    
    lat = safe_get(partner, "latitude")
    lng = safe_get(partner, "longitude")
    address = safe_get(partner, "address")
    name = safe_get(partner, "display_name", "Unknown")
    ptype = safe_get(partner, "type", "unknown")
    pcode = safe_get(partner, "connect_code", "N/A")
    
    info = f"Partner: {name}\nType: {ptype}\nCode: {pcode}"
    
    if lat and lng:
        await message.answer(f"📍 Sending location for:\n{info}", parse_mode=None)
        try:
            await bot.send_location(
                chat_id=message.chat.id,
                latitude=float(lat),
                longitude=float(lng)
            )
            addr_text = f"🏠 Address: {address}" if address else "No address set"
            await message.answer(addr_text, parse_mode=None)
        except Exception as e:
            await message.answer(f"❌ Failed to send location: {e}", parse_mode=None)
    else:
        await message.answer(
            f"⚠️ No location data for:\n{info}\n\n"
            f"latitude: {lat}\n"
            f"longitude: {lng}\n"
            f"address: {address or 'None'}",
            parse_mode=None
        )
