# Safar.uz Telegram Bot

A Telegram bot for booking travel services in Uzbekistan — guides, taxis, and hotels. Built with aiogram 3.x and PostgreSQL, deployed on Railway.

## Features

### User Flows

- **Guide Booking** — Select a guide, enter tour details, confirm booking
- **Taxi Booking** — Select a taxi service, enter pickup/dropoff, confirm booking
- **Hotel Booking** — Select a hotel (receives location pin), enter check-in/out dates, confirm booking

### Partner System

- Partners (guides, taxis, hotels) connect their Telegram via `/connect CODE`
- Connected partners receive booking requests instantly
- Partners can accept or reject bookings

### Admin Tools

- `/admin_health` — Database health check and partner statistics
- `/seed_partners` — Seed sample partners (4 guides, 5 taxis, 2 hotels)
- `/partners` — List all partners with connection status
- `/test_hotel_location` — Test hotel location sending

### Hotel Location

When a user selects a hotel, the bot automatically sends:

- A Telegram location pin (if coordinates exist)
- The hotel address

---

## Project Structure

```
├── main.py              # Bot entry point, router registration
├── config.py            # Environment variables (BOT_TOKEN, ADMINS, DATABASE_URL)
├── db_postgres.py       # PostgreSQL layer (asyncpg pool, auto-schema, CRUD)
├── db.py                # SQLite layer (legacy orders)
├── handlers.py          # Main user handlers (start, language, menu)
├── booking_handlers.py  # Guide/Taxi/Hotel booking flows
├── booking_dispatch.py  # Universal dispatch to partners
├── admin_commands.py    # Admin commands router
├── partner_handlers.py  # Partner /connect and booking callbacks
├── states.py            # FSM states for booking flows
├── keyboards.py         # Inline and reply keyboards
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container build (optional)
└── .env.example         # Environment template
```

---

## Local Development

### Prerequisites

- Python 3.12 (recommended)
- PostgreSQL (optional locally)

### Setup

**Windows:**

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**Linux/macOS:**

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Environment Variables

Edit `.env` with your values:

```env
BOT_TOKEN=your_bot_token_from_botfather
ADMINS=123456789,987654321
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
```

| Variable       | Required   | Description                        |
| -------------- | ---------- | ---------------------------------- |
| `BOT_TOKEN`    | Yes        | Telegram bot token from @BotFather |
| `ADMINS`       | Yes        | Comma-separated Telegram user IDs  |
| `DATABASE_URL` | Production | PostgreSQL connection string       |

### Run

```bash
python main.py
```

---

## Railway Deployment

### 1. Create Project

1. Go to [railway.app](https://railway.app) and create a new project
2. Connect your GitHub repository

### 2. Add PostgreSQL

1. Click "New" → "Database" → "PostgreSQL"
2. Railway automatically sets `DATABASE_URL` in your service

### 3. Set Environment Variables

In your service's Variables tab, add:

- `BOT_TOKEN` — Your bot token
- `ADMINS` — Your Telegram user ID(s)

### 4. Deploy

Railway auto-detects Python and builds using Nixpacks.

If using Dockerfile:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

### 5. Verify

After deploy, send `/admin_health` to your bot to verify database connection.

---

## Database & Migrations

### Auto Schema Creation

On startup, the bot automatically creates tables if they don't exist:

- `partners` — Partner records (guides, taxis, hotels)
- `bookings` — Booking records with status tracking

No manual migrations required.

### Seeding Partners

As an admin, send `/seed_partners` to create sample partners:

- 4 guides (GUIDE-001 to GUIDE-004)
- 5 taxis (TAXI-001 to TAXI-005)
- 2 hotels with locations (HOTEL-001, HOTEL-002)

### Verification

Send `/admin_health` to see:

- PostgreSQL connection status
- Partner counts by type (total, active, connected)
- Top 3 partners per type

---

## Partner Onboarding

1. Create partner record in database (via `/seed_partners` or admin panel)
2. Give partner their unique `connect_code` (e.g., `GUIDE-001`)
3. Partner opens bot and sends `/connect GUIDE-001`
4. Partner is now connected and will receive booking requests

---

## Troubleshooting

### BOT_TOKEN missing

```
Error: BOT_TOKEN not set
```

Set `BOT_TOKEN` in `.env` or Railway Variables.

### No partners found

If users see "Hozircha faol gidlar yo'q":

1. Send `/admin_health` to check database
2. Send `/seed_partners` to create sample partners
3. Verify partners exist with `/partners`

### DATABASE_URL format

Railway uses `postgresql://` prefix. The bot auto-converts `postgres://` to `postgresql://`.

If connection fails, verify:

- URL format is correct
- PostgreSQL service is running
- Network allows connection

### Telegram parse errors

```
Bad Request: can't parse entities
```

All admin commands use `parse_mode=None` to prevent this. If you add new messages, avoid HTML tags or use proper escaping.

### Python 3.13 build errors on Railway

```
error: failed to build pydantic-core
```

Pin Python to 3.12. Create `nixpacks.toml`:

```toml
[variables]
NIXPACKS_PYTHON_VERSION = "3.12"
```

Or in `runtime.txt`:

```
python-3.12
```

---

## Security Notes

- **Never commit `.env`** — Contains secrets
- **Rotate BOT_TOKEN** — If leaked, regenerate via @BotFather
- **Admin IDs** — Only trusted users should be in `ADMINS`
- **DATABASE_URL** — Keep credentials private

---

## Commands Reference

### User Commands

| Command  | Description                |
| -------- | -------------------------- |
| `/start` | Start bot, show main menu  |
| `/help`  | Show help message          |
| `/lang`  | Change language (UZ/RU/EN) |

### Admin Commands

| Command                          | Description                       |
| -------------------------------- | --------------------------------- |
| `/admin_help`                    | List admin commands               |
| `/admin_health`                  | Database health and partner stats |
| `/seed_partners`                 | Create sample partners            |
| `/partners`                      | List all partners with details    |
| `/test_hotel_location HOTEL-001` | Test hotel location sending       |

### Partner Commands

| Command         | Description             |
| --------------- | ----------------------- |
| `/connect CODE` | Connect partner account |

**Example:**

```
/connect GUIDE-001
```

Response:

```
✅ Successfully connected!

Name: Akmal - Samarqand gidi
Type: guide
Telegram ID: 123456789

You will now receive booking requests.
```

---

## License

MIT
