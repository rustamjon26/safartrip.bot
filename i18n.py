"""
Internationalization (i18n) module for Safar.uz bot.
Supports: Uzbek (uz), Russian (ru), English (en)
"""

# All translatable strings organized by key
TRANSLATIONS = {
    # /start greeting
    "start_greeting": {
        "uz": (
            "🌍 <b>Safar.uz botiga xush kelibsiz!</b>\n\n"
            "Sayohat xizmatlarini osongina bron qiling.\n"
            "Quyidagi menyudan kerakli xizmatni tanlang:"
        ),
        "ru": (
            "🌍 <b>Добро пожаловать в бот Safar.uz!</b>\n\n"
            "Легко бронируйте туристические услуги.\n"
            "Выберите нужную услугу из меню ниже:"
        ),
        "en": (
            "🌍 <b>Welcome to Safar.uz bot!</b>\n\n"
            "Easily book travel services.\n"
            "Select a service from the menu below:"
        ),
    },
    
    # Booking flow: ask for name
    "ask_name": {
        "uz": (
            "📝 <b>{service}</b>\n\n"
            "Buyurtma berish uchun ma'lumotlarni kiriting.\n\n"
            "👤 <b>Ism-familiyangizni kiriting:</b>"
        ),
        "ru": (
            "📝 <b>{service}</b>\n\n"
            "Введите данные для заказа.\n\n"
            "👤 <b>Введите ваше имя и фамилию:</b>"
        ),
        "en": (
            "📝 <b>{service}</b>\n\n"
            "Enter your details to place an order.\n\n"
            "👤 <b>Enter your full name:</b>"
        ),
    },
    
    # Name validation errors
    "name_too_short": {
        "uz": "⚠️ Ism juda qisqa. Iltimos, to'liq ismingizni kiriting:",
        "ru": "⚠️ Имя слишком короткое. Пожалуйста, введите полное имя:",
        "en": "⚠️ Name is too short. Please enter your full name:",
    },
    "name_too_long": {
        "uz": "⚠️ Ism juda uzun. Iltimos, qisqaroq kiriting:",
        "ru": "⚠️ Имя слишком длинное. Пожалуйста, сократите:",
        "en": "⚠️ Name is too long. Please shorten it:",
    },
    
    # Ask for phone
    "ask_phone": {
        "uz": (
            "✅ Rahmat!\n\n"
            "📱 <b>Telefon raqamingizni kiriting:</b>\n"
            "Format: +998 XX XXX XX XX\n\n"
            "Yoki \"📲 Kontaktni yuborish\" tugmasini bosing."
        ),
        "ru": (
            "✅ Спасибо!\n\n"
            "📱 <b>Введите ваш номер телефона:</b>\n"
            "Формат: +998 XX XXX XX XX\n\n"
            "Или нажмите кнопку \"📲 Отправить контакт\"."
        ),
        "en": (
            "✅ Thank you!\n\n"
            "📱 <b>Enter your phone number:</b>\n"
            "Format: +998 XX XXX XX XX\n\n"
            "Or press \"📲 Share Contact\" button."
        ),
    },
    
    # Phone validation error
    "phone_invalid": {
        "uz": (
            "⚠️ <b>Noto'g'ri telefon raqami!</b>\n\n"
            "Iltimos, O'zbekiston raqamini to'g'ri formatda kiriting:\n"
            "✅ +998901234567\n"
            "✅ +998 90 123 45 67\n\n"
            "📱 Qaytadan kiriting:"
        ),
        "ru": (
            "⚠️ <b>Неверный номер телефона!</b>\n\n"
            "Пожалуйста, введите номер Узбекистана в правильном формате:\n"
            "✅ +998901234567\n"
            "✅ +998 90 123 45 67\n\n"
            "📱 Попробуйте снова:"
        ),
        "en": (
            "⚠️ <b>Invalid phone number!</b>\n\n"
            "Please enter an Uzbekistan number in correct format:\n"
            "✅ +998901234567\n"
            "✅ +998 90 123 45 67\n\n"
            "📱 Try again:"
        ),
    },
    
    # Phone accepted, ask for date
    "ask_datetime": {
        "uz": (
            "✅ Telefon qabul qilindi!\n\n"
            "📅 <b>Sana va vaqtni kiriting:</b>\n"
            "Misol: 25.01.2025, soat 14:00"
        ),
        "ru": (
            "✅ Телефон принят!\n\n"
            "📅 <b>Введите дату и время:</b>\n"
            "Пример: 25.01.2025, 14:00"
        ),
        "en": (
            "✅ Phone accepted!\n\n"
            "📅 <b>Enter date and time:</b>\n"
            "Example: 25.01.2025, 14:00"
        ),
    },
    
    # Datetime validation
    "datetime_too_short": {
        "uz": "⚠️ Iltimos, sana va vaqtni aniqroq kiriting:\nMisol: 25.01.2025, soat 14:00",
        "ru": "⚠️ Пожалуйста, укажите дату и время точнее:\nПример: 25.01.2025, 14:00",
        "en": "⚠️ Please specify date and time more clearly:\nExample: 25.01.2025, 14:00",
    },
    
    # Ask for details
    "ask_details": {
        "uz": (
            "✅ Sana qabul qilindi!\n\n"
            "📝 <b>Qo'shimcha ma'lumot kiriting:</b>\n"
            "(Maxsus talablar, izohlar, va h.k.)\n\n"
            "Agar yo'q bo'lsa, \"Yo'q\" deb yozing."
        ),
        "ru": (
            "✅ Дата принята!\n\n"
            "📝 <b>Введите дополнительную информацию:</b>\n"
            "(Особые требования, комментарии и т.д.)\n\n"
            "Если нет — напишите «Нет»."
        ),
        "en": (
            "✅ Date accepted!\n\n"
            "📝 <b>Enter additional details:</b>\n"
            "(Special requirements, comments, etc.)\n\n"
            "If none, write \"None\"."
        ),
    },
    
    # Confirmation prompt
    "confirm_prompt": {
        "uz": (
            "📋 <b>Buyurtma ma'lumotlari:</b>\n\n"
            "🏷 <b>Xizmat:</b> {service}\n"
            "👤 <b>Ism:</b> {name}\n"
            "📱 <b>Telefon:</b> {phone}\n"
            "📅 <b>Sana/vaqt:</b> {datetime}\n"
            "📝 <b>Qo'shimcha:</b> {details}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ Tasdiqlaysizmi? <b>HA</b> yoki <b>YO'Q</b> deb yozing:"
        ),
        "ru": (
            "📋 <b>Данные заказа:</b>\n\n"
            "🏷 <b>Услуга:</b> {service}\n"
            "👤 <b>Имя:</b> {name}\n"
            "📱 <b>Телефон:</b> {phone}\n"
            "📅 <b>Дата/время:</b> {datetime}\n"
            "📝 <b>Дополнительно:</b> {details}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ Подтверждаете? Напишите <b>ДА</b> или <b>НЕТ</b>:"
        ),
        "en": (
            "📋 <b>Order details:</b>\n\n"
            "🏷 <b>Service:</b> {service}\n"
            "👤 <b>Name:</b> {name}\n"
            "📱 <b>Phone:</b> {phone}\n"
            "📅 <b>Date/time:</b> {datetime}\n"
            "📝 <b>Details:</b> {details}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ Confirm? Type <b>YES</b> or <b>NO</b>:"
        ),
    },
    
    # Confirmation invalid
    "confirm_invalid": {
        "uz": "⚠️ Iltimos, <b>HA</b> yoki <b>YO'Q</b> deb javob bering:",
        "ru": "⚠️ Пожалуйста, ответьте <b>ДА</b> или <b>НЕТ</b>:",
        "en": "⚠️ Please answer <b>YES</b> or <b>NO</b>:",
    },
    
    # Order cancelled (user said NO)
    "order_cancelled": {
        "uz": "❌ Buyurtma bekor qilindi.\n\nBosh menyuga qaytdingiz:",
        "ru": "❌ Заказ отменён.\n\nВы вернулись в главное меню:",
        "en": "❌ Order cancelled.\n\nYou're back to the main menu:",
    },
    
    # Order success
    "order_success": {
        "uz": (
            "✅ <b>Rahmat! Buyurtmangiz #{order_id} qabul qilindi!</b>\n\n"
            "Tez orada operatorimiz siz bilan bog'lanadi.\n\n"
            "📞 Shoshilinch bo'lsa: +998 90 123 45 67"
        ),
        "ru": (
            "✅ <b>Спасибо! Ваш заказ #{order_id} принят!</b>\n\n"
            "Скоро наш оператор свяжется с вами.\n\n"
            "📞 Срочно: +998 90 123 45 67"
        ),
        "en": (
            "✅ <b>Thank you! Your order #{order_id} has been received!</b>\n\n"
            "Our operator will contact you soon.\n\n"
            "📞 Urgent: +998 90 123 45 67"
        ),
    },
    
    # Rate limit exceeded
    "rate_limit": {
        "uz": "⏳ Iltimos, keyingi buyurtma berish uchun biroz kuting (10 soniya).",
        "ru": "⏳ Пожалуйста, подождите немного перед следующим заказом (10 секунд).",
        "en": "⏳ Please wait a moment before placing another order (10 seconds).",
    },
    
    # Cancel handler
    "cancel_nothing": {
        "uz": "Bekor qilinadigan jarayon yo'q 🙂",
        "ru": "Нечего отменять 🙂",
        "en": "Nothing to cancel 🙂",
    },
    "cancel_done": {
        "uz": "❌ Buyurtma bekor qilindi.\n\nBosh menyuga qaytdingiz:",
        "ru": "❌ Заказ отменён.\n\nВы вернулись в главное меню:",
        "en": "❌ Order cancelled.\n\nYou're back to the main menu:",
    },
    
    # Operator
    "operator_info": {
        "uz": (
            "📞 <b>Operator bilan bog'lanish:</b>\n\n"
            "☎️ Telefon: +998 90 123 45 67\n"
            "📱 Telegram: @safar_operator\n"
            "⏰ Ish vaqti: 09:00 - 21:00\n\n"
            "Savolingiz bo'lsa, bemalol murojaat qiling!"
        ),
        "ru": (
            "📞 <b>Связаться с оператором:</b>\n\n"
            "☎️ Телефон: +998 90 123 45 67\n"
            "📱 Telegram: @safar_operator\n"
            "⏰ Время работы: 09:00 - 21:00\n\n"
            "Если есть вопросы — обращайтесь!"
        ),
        "en": (
            "📞 <b>Contact operator:</b>\n\n"
            "☎️ Phone: +998 90 123 45 67\n"
            "📱 Telegram: @safar_operator\n"
            "⏰ Working hours: 09:00 - 21:00\n\n"
            "Feel free to contact us with any questions!"
        ),
    },
    
    # Help
    "help_text": {
        "uz": (
            "ℹ️ <b>Yordam</b>\n\n"
            "Bu bot orqali siz quyidagi xizmatlarni bron qilishingiz mumkin:\n\n"
            "🏨 <b>Mehmonxona</b> - Mehmonxona xonalarini bron qilish\n"
            "🚕 <b>Transport</b> - Taksi yoki transport xizmati\n"
            "🧑‍💼 <b>Gid</b> - Professional gid xizmati\n"
            "🎡 <b>Diqqatga sazovor</b> - Turistik joylar sayohati\n\n"
            "📋 <b>Buyurtma berish tartibi:</b>\n"
            "1. Xizmat turini tanlang\n"
            "2. Ism-familiyangizni kiriting\n"
            "3. Telefon raqamingizni kiriting (+998...)\n"
            "4. Sana va vaqtni belgilang\n"
            "5. Qo'shimcha ma'lumot kiriting\n"
            "6. Buyurtmani tasdiqlang\n\n"
            "❓ Savol bo'lsa: ☎️ Operator tugmasini bosing"
        ),
        "ru": (
            "ℹ️ <b>Помощь</b>\n\n"
            "С помощью этого бота вы можете заказать следующие услуги:\n\n"
            "🏨 <b>Отель</b> - Бронирование номера\n"
            "🚕 <b>Транспорт</b> - Такси или трансфер\n"
            "🧑‍💼 <b>Гид</b> - Услуги профессионального гида\n"
            "🎡 <b>Достопримечательности</b> - Экскурсии\n\n"
            "📋 <b>Порядок оформления заказа:</b>\n"
            "1. Выберите тип услуги\n"
            "2. Введите имя и фамилию\n"
            "3. Введите номер телефона (+998...)\n"
            "4. Укажите дату и время\n"
            "5. Добавьте дополнительную информацию\n"
            "6. Подтвердите заказ\n\n"
            "❓ Вопросы? Нажмите кнопку ☎️ Оператор"
        ),
        "en": (
            "ℹ️ <b>Help</b>\n\n"
            "With this bot you can book the following services:\n\n"
            "🏨 <b>Hotel</b> - Room reservation\n"
            "🚕 <b>Transport</b> - Taxi or transfer service\n"
            "🧑‍💼 <b>Guide</b> - Professional guide service\n"
            "🎡 <b>Attractions</b> - Tourist excursions\n\n"
            "📋 <b>How to place an order:</b>\n"
            "1. Select service type\n"
            "2. Enter your full name\n"
            "3. Enter phone number (+998...)\n"
            "4. Specify date and time\n"
            "5. Add additional details\n"
            "6. Confirm your order\n\n"
            "❓ Questions? Press ☎️ Operator button"
        ),
    },
    
    # Language selection
    "choose_language": {
        "uz": "🌐 Tilni tanlang:",
        "ru": "🌐 Выберите язык:",
        "en": "🌐 Choose language:",
    },
    "language_changed": {
        "uz": "✅ Til o'zgartirildi: O'zbekcha 🇺🇿",
        "ru": "✅ Язык изменён: Русский 🇷🇺",
        "en": "✅ Language changed: English 🇬🇧",
    },
    
    # Fallback
    "fallback": {
        "uz": "🙂 Menyudan tanlang:",
        "ru": "🙂 Выберите из меню:",
        "en": "🙂 Please select from the menu:",
    },
    
    # No access (for admin commands)
    "no_access": {
        "uz": "🚫 Ruxsat yo'q. Bu buyruq faqat adminlar uchun.",
        "ru": "🚫 Нет доступа. Эта команда только для администраторов.",
        "en": "🚫 No access. This command is for admins only.",
    },
    
    # Status notifications to user
    "status_accepted": {
        "uz": "📦 Sizning #{order_id} raqamli buyurtmangiz <b>qabul qilindi</b>! Tez orada bog'lanamiz.",
        "ru": "📦 Ваш заказ #{order_id} <b>принят</b>! Скоро свяжемся с вами.",
        "en": "📦 Your order #{order_id} has been <b>accepted</b>! We'll contact you soon.",
    },
    "status_contacted": {
        "uz": "📞 Sizning #{order_id} raqamli buyurtmangiz bo'yicha <b>bog'landik</b>.",
        "ru": "📞 По вашему заказу #{order_id} <b>связались</b> с вами.",
        "en": "📞 We have <b>contacted</b> you regarding order #{order_id}.",
    },
    "status_done": {
        "uz": "✅ Sizning #{order_id} raqamli buyurtmangiz <b>yakunlandi</b>! Rahmat!",
        "ru": "✅ Ваш заказ #{order_id} <b>выполнен</b>! Спасибо!",
        "en": "✅ Your order #{order_id} is <b>completed</b>! Thank you!",
    },
    
    # Menu placeholder
    "menu_placeholder": {
        "uz": "Xizmatni tanlang...",
        "ru": "Выберите услугу...",
        "en": "Select a service...",
    },
    "input_placeholder": {
        "uz": "Ma'lumot kiriting yoki bekor qiling...",
        "ru": "Введите данные или отмените...",
        "en": "Enter data or cancel...",
    },
    "confirm_placeholder": {
        "uz": "HA yoki YO'Q?",
        "ru": "ДА или НЕТ?",
        "en": "YES or NO?",
    },
    
    # User history (My Orders)
    "my_orders_title": {
        "uz": "📜 <b>Mening buyurtmalarim</b>\n\n",
        "ru": "📜 <b>Мои заказы</b>\n\n",
        "en": "📜 <b>My Orders</b>\n\n",
    },
    "my_orders_empty": {
        "uz": "📭 Sizda hali buyurtma yo'q.",
        "ru": "📭 У вас пока нет заказов.",
        "en": "📭 You don't have any orders yet.",
    },
    "my_orders_item": {
        "uz": "📦 <b>#{order_id}</b> | {status}\n   {service}\n   📅 {date_text}\n   🕐 {created_at}",
        "ru": "📦 <b>#{order_id}</b> | {status}\n   {service}\n   📅 {date_text}\n   🕐 {created_at}",
        "en": "📦 <b>#{order_id}</b> | {status}\n   {service}\n   📅 {date_text}\n   🕐 {created_at}",
    },
    "my_order_details": {
        "uz": (
            "📦 <b>Buyurtma #{order_id}</b>\n\n"
            "🏷 <b>Xizmat:</b> {service}\n"
            "👤 <b>Ism:</b> {name}\n"
            "📱 <b>Telefon:</b> {phone}\n"
            "📅 <b>Sana/vaqt:</b> {date_text}\n"
            "📝 <b>Qo'shimcha:</b> {details}\n\n"
            "📊 <b>Status:</b> {status}\n"
            "🕐 <b>Yaratilgan:</b> {created_at}\n"
            "🔄 <b>Yangilangan:</b> {updated_at}"
        ),
        "ru": (
            "📦 <b>Заказ #{order_id}</b>\n\n"
            "🏷 <b>Услуга:</b> {service}\n"
            "👤 <b>Имя:</b> {name}\n"
            "📱 <b>Телефон:</b> {phone}\n"
            "📅 <b>Дата/время:</b> {date_text}\n"
            "📝 <b>Дополнительно:</b> {details}\n\n"
            "📊 <b>Статус:</b> {status}\n"
            "🕐 <b>Создан:</b> {created_at}\n"
            "🔄 <b>Обновлён:</b> {updated_at}"
        ),
        "en": (
            "📦 <b>Order #{order_id}</b>\n\n"
            "🏷 <b>Service:</b> {service}\n"
            "👤 <b>Name:</b> {name}\n"
            "📱 <b>Phone:</b> {phone}\n"
            "📅 <b>Date/time:</b> {date_text}\n"
            "📝 <b>Details:</b> {details}\n\n"
            "📊 <b>Status:</b> {status}\n"
            "🕐 <b>Created:</b> {created_at}\n"
            "🔄 <b>Updated:</b> {updated_at}"
        ),
    },
    "my_order_not_found": {
        "uz": "❌ Buyurtma topilmadi.",
        "ru": "❌ Заказ не найден.",
        "en": "❌ Order not found.",
    },
    "my_order_no_access": {
        "uz": "🚫 Ruxsat yo'q. Bu sizning buyurtmangiz emas.",
        "ru": "🚫 Нет доступа. Это не ваш заказ.",
        "en": "🚫 No access. This is not your order.",
    },
    "btn_details": {
        "uz": "🔎 Batafsil",
        "ru": "🔎 Подробнее",
        "en": "🔎 Details",
    },
}


def t(key: str, lang: str = "uz", **kwargs) -> str:
    """
    Get translated string by key.
    Supports format placeholders via kwargs.
    Falls back to Uzbek if translation not found.
    """
    translations = TRANSLATIONS.get(key, {})
    text = translations.get(lang) or translations.get("uz", f"[{key}]")
    
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass  # If formatting fails, return as-is
    
    return text


# Button texts (for keyboards)
BUTTONS = {
    "cancel": {
        "uz": "❌ Bekor qilish",
        "ru": "❌ Отмена",
        "en": "❌ Cancel",
    },
    "share_contact": {
        "uz": "📲 Kontaktni yuborish",
        "ru": "📲 Отправить контакт",
        "en": "📲 Share Contact",
    },
    "yes": {
        "uz": "✅ HA",
        "ru": "✅ ДА",
        "en": "✅ YES",
    },
    "no": {
        "uz": "❌ YO'Q",
        "ru": "❌ НЕТ",
        "en": "❌ NO",
    },
    "operator": {
        "uz": "☎️ Operator",
        "ru": "☎️ Оператор",
        "en": "☎️ Operator",
    },
    "help": {
        "uz": "ℹ️ Yordam",
        "ru": "ℹ️ Помощь",
        "en": "ℹ️ Help",
    },
    "language": {
        "uz": "🌐 Til",
        "ru": "🌐 Язык",
        "en": "🌐 Language",
    },
    "my_orders": {
        "uz": "📜 Mening buyurtmalarim",
        "ru": "📜 Мои заказы",
        "en": "📜 My orders",
    },
}


def btn(key: str, lang: str = "uz") -> str:
    """Get button text by key."""
    button_texts = BUTTONS.get(key, {})
    return button_texts.get(lang) or button_texts.get("uz", key)
