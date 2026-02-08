# Safar.uz Telegram Bot

A Telegram bot for booking travel services in Uzbekistan — hotels, guides, taxis, and places. Built with aiogram 3.x and PostgreSQL, deployed on Railway.

## Architecture

**Unified CMS in Telegram:**

- One `listings` table for all categories (hotel, guide, taxi, place)
- One `bookings` table referencing listings with 5-minute timeout
- Partners add/manage listings via `/add` and `/my_listings`
- Users browse via `/browse` → Region → Category → Listings → Book

---

## Quick Start

### Environment Variables

```env
BOT_TOKEN=your_bot_token_from_botfather
DATABASE_URL=postgresql://user:pass@host:5432/dbname
ADMINS=123456789,987654321
```

| Variable       | Required | Description                        |
| -------------- | -------- | ---------------------------------- |
| `BOT_TOKEN`    | Yes      | Telegram bot token from @BotFather |
| `DATABASE_URL` | Yes      | PostgreSQL connection string       |
| `ADMINS`       | Yes      | Comma-separated admin Telegram IDs |
| `REDIS_URL`    | No       | Redis URL for FSM persistence      |

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your values

# Run
python main.py
```

### Railway Deployment

1. Create project on [railway.app](https://railway.app)
2. Add PostgreSQL database (auto-provides `DATABASE_URL`)
3. Set `BOT_TOKEN` and `ADMINS` variables
4. Deploy from GitHub

---

## Commands

### User Commands

| Command   | Description          |
| --------- | -------------------- |
| `/start`  | Start bot, show menu |
| `/browse` | Browse listings      |
| `/help`   | Show help            |

### Partner Commands

| Command        | Description              |
| -------------- | ------------------------ |
| `/add`         | Add new listing (wizard) |
| `/my_listings` | Manage your listings     |

### Admin Commands

| Command   | Description   |
| --------- | ------------- |
| `/health` | System health |

---

## Add Listing Wizard (`/add`)

Step-by-step flow:

1. **Category** — hotel / guide / taxi / place
2. **Title** — Min 3 characters
3. **Description** — Or `/skip`
4. **Region** — Currently only Zomin
5. **Subtype** — Hotels only: Shale, Mehmonxona, etc.
6. **Price** — Hotel/taxi only, or `/skip`
7. **Phone** — Or `/skip`
8. **Location** — Required for hotel/place
9. **Photos** — 1-5 required for hotel/place
10. **Confirm** — Save or cancel

### Photo Notes

- Photos stored as Telegram `file_id` strings
- Maximum 5 photos per listing
- Use largest photo size (automatically selected)

### Location Requirements

| Category | Location |
| -------- | -------- |
| hotel    | Required |
| place    | Required |
| guide    | Optional |
| taxi     | Optional |

---

## User Booking Flow

1. `/browse` → Select Region (Zomin)
2. Select Category (Hotel, Guide, Taxi, Place)
3. For hotels: Select subtype
4. Browse listings (photo cards with pagination)
5. Select listing → View details with all photos
6. Click "Bron qilish" → Fill form (name, phone, date)
7. Confirm → Booking sent to partner admin
8. Partner has 5 minutes to accept/reject
9. User notified of result

### 5-Minute Timeout

- Bookings expire after 5 minutes if no response
- Background task checks every 30 seconds
- Uses atomic `UPDATE RETURNING` (safe for multiple workers)

---

## Database Schema

### listings

```sql
id                UUID PRIMARY KEY
region            TEXT NOT NULL DEFAULT 'zomin'
category          TEXT NOT NULL (hotel/guide/taxi/place)
subtype           TEXT NULL
title             TEXT NOT NULL
description       TEXT NULL
price_from        INTEGER NULL
currency          TEXT NOT NULL DEFAULT 'UZS'
phone             TEXT NULL
telegram_admin_id BIGINT NOT NULL
latitude          DOUBLE PRECISION NULL
longitude         DOUBLE PRECISION NULL
address           TEXT NULL
photos            JSONB DEFAULT '[]'
is_active         BOOLEAN DEFAULT true
created_at        TIMESTAMPTZ DEFAULT now()
```

### bookings

```sql
id               UUID PRIMARY KEY
listing_id       UUID REFERENCES listings(id)
user_telegram_id BIGINT NOT NULL
payload          JSONB DEFAULT '{}'
status           TEXT (new/sent/accepted/rejected/timeout)
expires_at       TIMESTAMPTZ NULL
created_at       TIMESTAMPTZ DEFAULT now()
```

---

## Project Structure

```
├── main.py               # Entry point, routers, /start, /help
├── db_postgres.py        # asyncpg pool, schema, CRUD
├── listing_wizard.py     # /add wizard, /my_listings
├── listings_user_flow.py # /browse, booking FSM
├── booking_dispatch.py   # Partner callbacks, timeout checker
├── config.py             # Environment config
└── requirements.txt      # Dependencies
```

---

## Troubleshooting

### DATABASE_URL format

Railway uses `postgres://`, bot auto-converts to `postgresql://`.

### HTML parse errors

All user text is escaped with `html.escape()`. Safe send/edit functions retry without parse_mode if parsing fails.

### Photos not loading

Telegram `file_id` is server-specific. If bot token changes, old file_ids may become invalid.

---

## License

MIT
