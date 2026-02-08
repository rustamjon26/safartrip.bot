"""
Keyboard layouts for the bot (localized).
"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from i18n import btn, t


# --- Inline calendar builder (moved from keyboards/calendar.py) ---
from aiogram.types import InlineKeyboardMarkup as _InlineKeyboardMarkup, InlineKeyboardButton as _InlineKeyboardButton
import calendar as _py_calendar

def build_calendar(year: int, month: int) -> InlineKeyboardMarkup:
    """Build an inline calendar keyboard for the given year/month."""
    keyboard: list[list[_InlineKeyboardButton]] = []

    keyboard.append([
        _InlineKeyboardButton(text=f"{_py_calendar.month_name[month]} {year}", callback_data="ignore")
    ])

    keyboard.append([
        _InlineKeyboardButton(text=day, callback_data="ignore")
        for day in ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]
    ])

    for week in _py_calendar.monthcalendar(year, month):
        row: list[_InlineKeyboardButton] = []
        for day in week:
            if day == 0:
                row.append(_InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                row.append(_InlineKeyboardButton(text=str(day), callback_data=f"date:{year}:{month}:{day}"))
        keyboard.append(row)

    keyboard.append([_InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")])

    return _InlineKeyboardMarkup(inline_keyboard=keyboard)



def get_main_menu(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Create main menu keyboard with service options."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🏨 Mehmonxona bron"),
                KeyboardButton(text="🚕 Transport"),
            ],
            [
                KeyboardButton(text="🧑‍💼 Gid"),
                KeyboardButton(text="🎡 Diqqatga sazovor joylar"),
            ],
            [
                KeyboardButton(text=btn("my_orders", lang)),
            ],
            [
                KeyboardButton(text=btn("operator", lang)),
                KeyboardButton(text=btn("help", lang)),
            ],
            [
                KeyboardButton(text=btn("language", lang)),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder=btn("menu_placeholder", lang) if lang == "uz" else None,
    )


def get_cancel_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Cancel button keyboard for FSM flows."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=btn("cancel", lang))],
        ],
        resize_keyboard=True,
    )


def get_phone_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Phone input keyboard with contact share button."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=btn("share_contact", lang),
                    request_contact=True
                ),
            ],
            [KeyboardButton(text=btn("cancel", lang))],
        ],
        resize_keyboard=True,
    )


def get_confirm_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Confirmation keyboard with YES/NO options."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=btn("yes", lang)),
                KeyboardButton(text=btn("no", lang)),
            ],
            [KeyboardButton(text=btn("cancel", lang))],
        ],
        resize_keyboard=True,
    )


def get_language_keyboard() -> ReplyKeyboardMarkup:
    """Language selection keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🇺🇿 O'zbekcha"),
                KeyboardButton(text="🇷🇺 Русский"),
                KeyboardButton(text="🇬🇧 English"),
            ],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True,
    )


def get_user_order_inline_keyboard(order_id: int, lang: str = "uz") -> InlineKeyboardMarkup:
    """Inline keyboard for user order details button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_details", lang),
                    callback_data=f"my:order:{order_id}"
                ),
            ],
        ]
    )


# Service buttons (these stay the same across languages)
SERVICE_BUTTONS = [
    "🏨 Mehmonxona bron",
    "🚕 Transport",
    "🧑‍💼 Gid",
    "🎡 Diqqatga sazovor joylar",
]

# Service name mapping for display
SERVICE_NAMES = {
    "🏨 Mehmonxona bron": "🏨 Mehmonxona bron qilish",
    "🚕 Transport": "🚕 Transport xizmati",
    "🧑‍💼 Gid": "🧑‍💼 Gid xizmati",
    "🎡 Diqqatga sazovor joylar": "🎡 Diqqatga sazovor joylar",
}


import calendar
import datetime as dt
from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


# Callback format:
# CAL:nav:<year>:<month>
# CAL:pick:<yyyy-mm-dd>
# CAL:today
# CAL:cancel

WEEKDAYS_UZ = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]


def _month_name_uz(month: int) -> str:
    months = [
        "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
        "Iyul", "Avgust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr"
    ]
    return months[month - 1]


def build_calendar(year: int | None = None, month: int | None = None) -> InlineKeyboardMarkup:
    today = dt.date.today()
    year = year or today.year
    month = month or today.month

    cal = calendar.Calendar(firstweekday=0)  # 0 = Monday

    kb = InlineKeyboardBuilder()

    # Header: "Noyabr 2016"
    kb.row(
        InlineKeyboardButton(
            text=f"{_month_name_uz(month)} {year}",
            callback_data="CAL:noop"
        )
    )

    # Weekdays row
    kb.row(*[
        InlineKeyboardButton(text=wd, callback_data="CAL:noop")
        for wd in WEEKDAYS_UZ
    ])

    # Days grid
    month_days = cal.monthdayscalendar(year, month)  # list of weeks, 0 for empty cells
    for week in month_days:
        row_btns = []
        for day in week:
            if day == 0:
                row_btns.append(InlineKeyboardButton(text=" ", callback_data="CAL:noop"))
            else:
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                row_btns.append(InlineKeyboardButton(text=str(day), callback_data=f"CAL:pick:{date_str}"))
        kb.row(*row_btns)

    # Navigation row
    prev_y, prev_m = _add_month(year, month, -1)
    next_y, next_m = _add_month(year, month, +1)

    kb.row(
        InlineKeyboardButton(text="⬅️", callback_data=f"CAL:nav:{prev_y}:{prev_m}"),
        InlineKeyboardButton(text="Bugun", callback_data="CAL:today"),
        InlineKeyboardButton(text="➡️", callback_data=f"CAL:nav:{next_y}:{next_m}"),
    )

    # Cancel row
    kb.row(
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="CAL:cancel")
    )

    return kb.as_markup()


def _add_month(year: int, month: int, delta: int) -> tuple[int, int]:
    # delta = -1 or +1 (or any int)
    y = year
    m = month + delta
    while m < 1:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return y, m


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def hotel_inline_kb(hotel_id: str, hotel_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏨 {hotel_name}", callback_data=f"hotel:pick:{hotel_id}")],
    ])
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def room_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛏 2 xonali (Standart)", callback_data="room:2:std")],
        [InlineKeyboardButton(text="🛏 4 xonali (Standart)", callback_data="room:4:std")],
        [InlineKeyboardButton(text="✨ 2 xonali (Lyuks)", callback_data="room:2:lux")],
        [InlineKeyboardButton(text="✨ 4 xonali (Lyuks)", callback_data="room:4:lux")],
    ])
def taxi_pick_kb(taxi_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Tanlash", callback_data=f"taxi:pick:{taxi_id}")]
    ])


def taxi_pick_kb(taxi_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Tanlash", callback_data=f"taxi:pick:{taxi_id}")]
    ])

