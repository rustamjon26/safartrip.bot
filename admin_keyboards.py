"""
Admin inline keyboards for order status management.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_order_status_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """
    Create inline keyboard for admin order status updates.
    callback_data format: st:<order_id>:<status>
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Qabul qilindi",
                    callback_data=f"st:{order_id}:accepted"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📞 Bog'landik",
                    callback_data=f"st:{order_id}:contacted"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Yakunlandi",
                    callback_data=f"st:{order_id}:done"
                ),
            ],
        ]
    )


def parse_status_callback(callback_data: str) -> tuple[int, str] | None:
    """
    Parse callback data from order status buttons.
    Returns (order_id, status) tuple or None if invalid.
    Expected format: st:<order_id>:<status>
    """
    try:
        parts = callback_data.split(":")
        if len(parts) != 3 or parts[0] != "st":
            return None
        
        order_id = int(parts[1])
        status = parts[2]
        
        if status not in ("accepted", "contacted", "done"):
            return None
        
        return (order_id, status)
    
    except (ValueError, IndexError):
        return None


# Status display names (for admin messages)
STATUS_DISPLAY = {
    "new": "🆕 Yangi",
    "accepted": "✅ Qabul qilindi",
    "contacted": "📞 Bog'landik",
    "done": "✅ Yakunlandi",
}
