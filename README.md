# 🌍 Safar.uz Telegram Bot (MVP+ with Admin Features)

A travel services booking bot built with Python and aiogram 3.x, featuring SQLite persistence, multi-language support, admin order management, search/filter, CSV export, and automated backups.

## 📁 Project Structure

```
safar_bot/
├── main.py              # Entry point - starts the bot
├── config.py            # Configuration loader (.env parser)
├── db.py                # SQLite database operations
├── i18n.py              # Internationalization (UZ/RU/EN)
├── keyboards.py         # Reply keyboard layouts
├── admin_keyboards.py   # Admin inline keyboards
├── admin_commands.py    # Admin-only commands router
├── states.py            # FSM state definitions
├── handlers.py          # Message handlers and booking flow
├── rate_limit.py        # Anti-spam rate limiter
├── export_utils.py      # CSV export utilities
├── backup.py            # Automated daily backup
├── requirements.txt     # Python dependencies
├── .env.example         # Example environment file
├── README.md            # This file
├── bot.db               # SQLite database (auto-created)
└── backups/             # Daily backup folder (auto-created)
    └── bot_YYYYMMDD.db  # Daily backup files
```

## 🚀 Quick Start

### 1. Create Virtual Environment

**Windows (PowerShell):**
```powershell
cd safar_bot
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Git Bash / CMD):**
```bash
cd safar_bot
python -m venv venv
source venv/Scripts/activate  # Git Bash
# or
venv\Scripts\activate.bat     # CMD
```

**Linux / macOS:**
```bash
cd safar_bot
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Copy the example file and edit it:

**Windows:**
```powershell
copy .env.example .env
```

**Linux / macOS:**
```bash
cp .env.example .env
```

Edit `.env` with your settings:
```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
ADMINS=123456789,987654321
```

**How to get these values:**
- `BOT_TOKEN`: Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
- `ADMINS`: Get your user ID from [@userinfobot](https://t.me/userinfobot)

### 4. Run the Bot

```bash
python main.py
```

You should see:
```
✅ Config loaded: 1 admin(s) configured
🚀 Starting Safar.uz Bot (MVP+ with Admin Features)...
📢 Configured admins: [123456789]
✅ Database initialized
🔄 Backup scheduler started
✅ Database backed up: bot_20250123.db
✅ Bot is running! Press Ctrl+C to stop.
```

**Note:** 
- `bot.db` SQLite database is automatically created on first run
- `backups/` folder is automatically created for daily backups

## 🎯 Features

### Main Menu (User)
- 🏨 **Mehmonxona bron** - Hotel booking
- 🚕 **Transport** - Transportation service
- 🧑‍💼 **Gid** - Guide service
- 🎡 **Diqqatga sazovor joylar** - Tourist attractions
- ☎️ **Operator** - Contact information
- ℹ️ **Yordam** - Help & instructions
- 🌐 **Til** - Language selection (UZ/RU/EN)

### Admin Commands

| Command | Description |
|---------|-------------|
| `/orders` | Show last 10 orders (all statuses) |
| `/orders new` | Show last 10 orders with status "new" |
| `/orders accepted` | Show last 10 orders with status "accepted" |
| `/orders contacted` | Show last 10 orders with status "contacted" |
| `/orders done` | Show last 10 orders with status "done" |
| `/orders <status> <page>` | Pagination (e.g., `/orders new 2`) |
| `/order <id>` | Show full order details + status buttons |
| `/find <query>` | Search orders by name/phone/service/details |
| `/filter service <value>` | Filter by service type |
| `/filter date <value>` | Filter by date |
| `/export` | Export all orders as CSV |
| `/export <status>` | Export orders with specific status |

**Note:** Non-admins get a localized "No access" message.

### Booking Flow (FSM)
1. Select service from menu
2. Enter your name
3. Enter phone number (+998 format) or share contact
4. Enter preferred date/time
5. Add additional details
6. Confirm with YES/NO

### Admin Order Management
When admins receive an order or use `/order <id>`, they get inline buttons:
- **✅ Qabul qilindi** - Mark as accepted
- **📞 Bog'landik** - Mark as contacted
- **✅ Yakunlandi** - Mark as completed

When admin clicks a button:
- Order status is updated in database
- Admin message is updated with new status
- User receives notification about status change (in their language)

### Automated Daily Backup
- `backups/` folder is created automatically
- Every 24 hours, `bot.db` is backed up using SQLite backup API
- Filename format: `bot_YYYYMMDD.db`
- Skips if today's backup already exists
- Admins receive notification on backup success

### User History (My Orders)
- Users can view their last 10 orders via main menu
- Shows status, service, date, and creation time
- "🔎 Details" button for full order info
- Secure: users can only see their own orders

### Error Logging
- Exceptions are caught globally
- Admins receive error reports with traceback
- Throttling: same error sent max once per 30s
- Prevents bot crashes on unhandled errors

### Multi-Language Support
Users can switch between:
- 🇺🇿 **O'zbekcha** (Uzbek) - default
- 🇷🇺 **Русский** (Russian)
- 🇬🇧 **English**

All messages (prompts, errors, notifications) are localized.

### Anti-Spam Protection
- Users can only create 1 order per 10 seconds
- Prevents accidental double-submissions

## 📱 Phone Validation

The bot accepts Uzbekistan phone numbers in these formats:
- ✅ `+998901234567`
- ✅ `+998 90 123 45 67`
- ❌ `8901234567` (missing +998)
- ❌ `+7901234567` (wrong country code)

## 🗃️ Database Schema

### users
| Column | Type | Description |
|--------|------|-------------|
| user_id | INTEGER | Telegram user ID (primary key) |
| username | TEXT | Telegram username |
| lang | TEXT | Language preference (uz/ru/en) |

### orders
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Order ID (auto-increment) |
| user_id | INTEGER | Telegram user ID |
| username | TEXT | Telegram username |
| service | TEXT | Selected service |
| name | TEXT | Customer name |
| phone | TEXT | Phone number |
| date_text | TEXT | Requested date/time |
| details | TEXT | Additional details |
| status | TEXT | Order status (new/accepted/contacted/done) |
| created_at | TEXT | Creation timestamp |
| updated_at | TEXT | Last update timestamp |

## 📊 CSV Export Format

Exported CSV files contain columns:
```
id,user_id,username,service,name,phone,date_text,details,status,created_at,updated_at
```

- Filename: `orders_YYYYMMDD_HHMMSS.csv` or `orders_<status>_YYYYMMDD_HHMMSS.csv`
- Encoding: UTF-8 with BOM (Excel-compatible)

## ⚠️ Troubleshooting

**"BOT_TOKEN is not set"**
- Make sure you created `.env` file (not just `.env.example`)
- Check that `.env` is in the same folder as `main.py`

**"ADMINS must be comma-separated integers"**
- Use only numbers, no quotes: `ADMINS=123456789`
- Multiple admins: `ADMINS=123456789,987654321`

**Bot not responding**
- Check if another instance is running
- Verify your BOT_TOKEN is correct
- Check your internet connection

**Admin commands not working**
- Make sure your user ID is in the ADMINS list in `.env`
- Check bot console for error messages

**Backup not working**
- Check write permissions in project folder
- Verify `backups/` folder was created

## 📝 License

MIT License - feel free to use and modify!
