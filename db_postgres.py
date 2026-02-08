"""
db_postgres.py — Async PostgreSQL database layer (asyncpg) for partner booking system.

Features:
- asyncpg connection pool
- auto schema creation (partners, bookings) with indices
- supports partner connect (/connect) by connect_code
- supports bookings (create, get, status updates, mark sent_at)
- Railway-compatible: postgres:// -> postgresql:// normalize, SSL support

ENV:
- DATABASE_URL (required)
- DB_SSL (optional): "require" | "disable" (default: "require" on Railway)
"""

from __future__ import annotations

import os
import json
import logging
from uuid import UUID
from typing import Any, Optional

import asyncpg

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _normalize_database_url(url: str) -> str:
    """
    Railway sometimes provides postgres://... which is valid in many libs,
    but we normalize to postgresql://... just in case.
    """
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def _should_require_ssl() -> bool:
    """
    On Railway, public endpoints typically need SSL.
    You can override via DB_SSL=disable if you're sure.
    """
    v = os.getenv("DB_SSL", "").strip().lower()
    if v in ("disable", "false", "0", "no"):
        return False
    if v in ("require", "true", "1", "yes"):
        return True

    # Auto-detect Railway env
    # If running on Railway, it's safer to require SSL.
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"):
        return True

    # Default: require (safe)
    return True


# ---------------------------------------------------------------------
# Schema (auto-create)
# ---------------------------------------------------------------------
_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS partners (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type         text NOT NULL CHECK (type IN ('guide', 'hotel', 'taxi')),
    display_name text NOT NULL,
    connect_code text UNIQUE NOT NULL,
    telegram_id  bigint UNIQUE,
    is_active    boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),

    latitude     double precision,
    longitude    double precision,
    address      text
);

CREATE TABLE IF NOT EXISTS bookings (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    service_type     text NOT NULL CHECK (service_type IN ('guide', 'hotel', 'taxi')),
    partner_id       uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    user_telegram_id bigint NOT NULL,
    payload          jsonb NOT NULL DEFAULT '{}'::jsonb,
    status           text NOT NULL DEFAULT 'new',
    created_at       timestamptz NOT NULL DEFAULT now(),
    sent_at          timestamptz
);

CREATE INDEX IF NOT EXISTS idx_partners_type_active
    ON partners(type, is_active);

CREATE INDEX IF NOT EXISTS idx_bookings_user_created
    ON bookings(user_telegram_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bookings_partner_created
    ON bookings(partner_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bookings_status_created
    ON bookings(status, created_at DESC);
"""


async def ensure_schema() -> bool:
    """Create tables/indexes if missing. Safe to run multiple times."""
    global _pool
    if not _pool:
        logger.error("DB pool not initialized; cannot ensure schema")
        return False

    try:
        async with _pool.acquire() as conn:
            # asyncpg can execute multiple statements separated by semicolons
            await conn.execute(_SCHEMA_SQL)
        logger.info("DB schema ensured (partners, bookings)")
        return True
    except Exception as e:
        logger.exception(f"Failed to ensure schema: {e}")
        return False


# ---------------------------------------------------------------------
# Pool lifecycle
# ---------------------------------------------------------------------
async def init_db_pool() -> bool:
    """
    Initialize PostgreSQL pool and ensure schema.
    Must be called before any other DB operations.
    """
    global _pool

    if _pool:
        return True

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    database_url = _normalize_database_url(database_url)
    require_ssl = _should_require_ssl()

    try:
        _pool = await asyncpg.create_pool(
            dsn=database_url,
            min_size=1,
            max_size=10,
            command_timeout=30,
            ssl="require" if require_ssl else None,
        )
        logger.info("PostgreSQL pool initialized")

        ok = await ensure_schema()
        if not ok:
            # If schema creation failed, close pool to avoid half-broken state
            await close_db_pool()
            return False

        return True
    except Exception as e:
        logger.exception(f"Failed to create DB pool: {e}")
        _pool = None
        return False


async def close_db_pool() -> None:
    global _pool
    try:
        if _pool:
            await _pool.close()
            logger.info("PostgreSQL pool closed")
    finally:
        _pool = None


async def healthcheck() -> tuple[bool, str]:
    """Basic healthcheck: can we read partners count?"""
    if not _pool:
        return False, "Pool not initialized"
    try:
        async with _pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM partners")
            return True, f"OK ({count} partners)"
    except Exception as e:
        return False, f"Error: {e}"


# ---------------------------------------------------------------------
# Partner functions
# ---------------------------------------------------------------------
async def fetch_partners_by_type(partner_type: str) -> list[dict]:
    """Fetch active partners by type ('guide', 'taxi', 'hotel')."""
    if not _pool:
        logger.error("DB pool not initialized")
        return []

    partner_type = partner_type.strip().lower()

    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, display_name, telegram_id
                FROM partners
                WHERE type = $1 AND is_active = true
                ORDER BY display_name
                """,
                partner_type,
            )
            return [
                {
                    "id": str(r["id"]),
                    "display_name": r["display_name"],
                    "telegram_id": r["telegram_id"],
                }
                for r in rows
            ]
    except Exception as e:
        logger.exception(f"Error fetching partners by type={partner_type}: {e}")
        return []


async def get_partner_by_id(partner_id: str) -> Optional[dict]:
    """Get partner by UUID string, including location fields."""
    if not _pool:
        logger.error("DB pool not initialized")
        return None

    try:
        pid = UUID(partner_id)
    except Exception:
        return None

    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, type, display_name, connect_code, telegram_id, is_active, created_at,
                       latitude, longitude, address
                FROM partners
                WHERE id = $1
                """,
                pid,
            )
            if not row:
                return None
            return {
                "id": str(row["id"]),
                "type": row["type"],
                "display_name": row["display_name"],
                "connect_code": row["connect_code"],
                "telegram_id": row["telegram_id"],
                "is_active": row["is_active"],
                "created_at": row["created_at"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "address": row["address"],
            }
    except Exception as e:
        logger.exception(f"Error getting partner by id={partner_id}: {e}")
        return None


async def get_partner_location(partner_id: str) -> tuple[float, float, str] | None:
    """
    Get partner location (lat, lng, address) by UUID.
    Returns tuple (latitude, longitude, address) or None if not found or no location.
    """
    partner = await get_partner_by_id(partner_id)
    if not partner:
        return None
    
    lat = partner.get("latitude")
    lng = partner.get("longitude")
    address = partner.get("address") or ""
    
    if lat is None or lng is None:
        return None
    
    return (float(lat), float(lng), address)


async def get_partner_by_code(connect_code: str) -> Optional[dict]:
    """Get partner by connect_code (for admin testing)."""
    if not _pool:
        logger.error("DB pool not initialized")
        return None

    connect_code = connect_code.strip().upper()
    if not connect_code:
        return None

    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, type, display_name, connect_code, telegram_id, is_active,
                       latitude, longitude, address
                FROM partners
                WHERE UPPER(connect_code) = $1
                """,
                connect_code,
            )
            if not row:
                return None
            return {
                "id": str(row["id"]),
                "type": row["type"],
                "display_name": row["display_name"],
                "connect_code": row["connect_code"],
                "telegram_id": row["telegram_id"],
                "is_active": row["is_active"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "address": row["address"],
            }
    except Exception as e:
        logger.exception(f"Error getting partner by code={connect_code}: {e}")
        return None


async def connect_partner(connect_code: str, telegram_id: int) -> Optional[dict]:
    """
    Partner botga /connect CODE yuboradi.
    Biz partner telegram_id ni DB'ga bog'lab qo'yamiz.
    """
    if not _pool:
        logger.error("DB pool not initialized")
        return None

    connect_code = connect_code.strip()
    if not connect_code:
        return None

    try:
        async with _pool.acquire() as conn:
            partner = await conn.fetchrow(
                """
                SELECT id, type, display_name, is_active
                FROM partners
                WHERE connect_code = $1
                """,
                connect_code,
            )
            if not partner or not partner["is_active"]:
                return None

            # telegram_id unique bo‘lgani uchun conflict bo‘lsa ham tushunarli log bo‘lsin
            await conn.execute(
                """
                UPDATE partners
                SET telegram_id = $1
                WHERE connect_code = $2
                """,
                int(telegram_id),
                connect_code,
            )

            return {
                "id": str(partner["id"]),
                "type": partner["type"],
                "display_name": partner["display_name"],
            }
    except asyncpg.UniqueViolationError:
        logger.warning("This telegram_id is already linked to another partner")
        return None
    except Exception as e:
        logger.exception(f"Error connecting partner (code={connect_code}): {e}")
        return None


async def get_all_partners() -> list[dict]:
    """Admin uchun: hamma partnerlar."""
    if not _pool:
        logger.error("DB pool not initialized")
        return []

    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, type, display_name, connect_code, telegram_id, is_active,
                       latitude, longitude, address
                FROM partners
                ORDER BY type, display_name
                """
            )
            return [
                {
                    "id": str(r["id"]),
                    "type": r["type"],
                    "display_name": r["display_name"],
                    "connect_code": r["connect_code"],
                    "telegram_id": r["telegram_id"],
                    "is_active": r["is_active"],
                    "latitude": r["latitude"],
                    "longitude": r["longitude"],
                    "address": r["address"],
                }
                for r in rows
            ]
    except Exception as e:
        logger.exception(f"Error fetching all partners: {e}")
        return []


# Optional: seed partners (4 guide, 5 taxi, 0/any hotel)
async def seed_partners(sample_guides: list[dict], sample_taxis: list[dict], sample_hotels: list[dict] | None = None) -> int:
    """
    Insert sample partners. Each dict expected:
    - type: 'guide'|'taxi'|'hotel'
    - display_name
    - connect_code
    - is_active (optional)
    - latitude/longitude/address (optional, mostly for hotels)
    """
    if not _pool:
        logger.error("DB pool not initialized")
        return 0

    items = []
    for g in sample_guides:
        g = dict(g)
        g["type"] = "guide"
        items.append(g)
    for t in sample_taxis:
        t = dict(t)
        t["type"] = "taxi"
        items.append(t)
    if sample_hotels:
        for h in sample_hotels:
            h = dict(h)
            h["type"] = "hotel"
            items.append(h)

    if not items:
        return 0

    inserted = 0
    try:
        async with _pool.acquire() as conn:
            for it in items:
                display_name = it["display_name"]
                connect_code = it["connect_code"]
                is_active = bool(it.get("is_active", True))
                latitude = it.get("latitude")
                longitude = it.get("longitude")
                address = it.get("address")

                # Upsert by connect_code (kechroq qayta seed qilsa duplicate bo‘lmasin)
                await conn.execute(
                    """
                    INSERT INTO partners(type, display_name, connect_code, is_active, latitude, longitude, address)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (connect_code)
                    DO UPDATE SET
                        type = EXCLUDED.type,
                        display_name = EXCLUDED.display_name,
                        is_active = EXCLUDED.is_active,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        address = EXCLUDED.address
                    """,
                    it["type"],
                    display_name,
                    connect_code,
                    is_active,
                    latitude,
                    longitude,
                    address,
                )
                inserted += 1
        return inserted
    except Exception as e:
        logger.exception(f"Error seeding partners: {e}")
        return 0


# ---------------------------------------------------------------------
# Booking functions
# ---------------------------------------------------------------------
async def create_booking(
    service_type: str,
    partner_id: str,
    user_telegram_id: int,
    payload: dict[str, Any],
    status: str = "new",
) -> Optional[str]:
    """Create booking row; returns booking_id."""
    if not _pool:
        logger.error("DB pool not initialized")
        return None

    service_type = service_type.strip().lower()
    status = status.strip().lower()

    try:
        pid = UUID(partner_id)
    except Exception:
        return None

    try:
        async with _pool.acquire() as conn:
            booking_id = await conn.fetchval(
                """
                INSERT INTO bookings(service_type, partner_id, user_telegram_id, payload, status)
                VALUES ($1, $2, $3, $4::jsonb, $5)
                RETURNING id
                """,
                service_type,
                pid,
                int(user_telegram_id),
                json.dumps(payload or {}),
                status,
            )
            return str(booking_id) if booking_id else None
    except Exception as e:
        logger.exception(f"Error creating booking: {e}")
        return None


async def get_booking(booking_id: str) -> Optional[dict]:
    """Get booking by id."""
    if not _pool:
        logger.error("DB pool not initialized")
        return None

    try:
        bid = UUID(booking_id)
    except Exception:
        return None

    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, service_type, partner_id, user_telegram_id, payload, status, created_at, sent_at
                FROM bookings
                WHERE id = $1
                """,
                bid,
            )
            if not row:
                return None
            return {
                "id": str(row["id"]),
                "service_type": row["service_type"],
                "partner_id": str(row["partner_id"]),
                "user_telegram_id": row["user_telegram_id"],
                "payload": dict(row["payload"]) if row["payload"] else {},
                "status": row["status"],
                "created_at": row["created_at"],
                "sent_at": row["sent_at"],
            }
    except Exception as e:
        logger.exception(f"Error getting booking: {e}")
        return None


async def set_booking_status(booking_id: str, status: str) -> bool:
    """Update booking status."""
    if not _pool:
        logger.error("DB pool not initialized")
        return False

    try:
        bid = UUID(booking_id)
    except Exception:
        return False

    status = status.strip().lower()
    try:
        async with _pool.acquire() as conn:
            res = await conn.execute(
                """
                UPDATE bookings
                SET status = $1
                WHERE id = $2
                """,
                status,
                bid,
            )
            return res == "UPDATE 1"
    except Exception as e:
        logger.exception(f"Error updating booking status: {e}")
        return False


async def get_bookings_by_user(user_telegram_id: int, limit: int = 10) -> list[dict]:
    """Userning oxirgi bookinglari."""
    if not _pool:
        logger.error("DB pool not initialized")
        return []

    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT b.id, b.service_type, b.partner_id, b.payload, b.status, b.created_at, b.sent_at,
                       p.display_name AS partner_name
                FROM bookings b
                LEFT JOIN partners p ON p.id = b.partner_id
                WHERE b.user_telegram_id = $1
                ORDER BY b.created_at DESC
                LIMIT $2
                """,
                int(user_telegram_id),
                int(limit),
            )
            return [
                {
                    "id": str(r["id"]),
                    "service_type": r["service_type"],
                    "partner_id": str(r["partner_id"]),
                    "partner_name": r["partner_name"],
                    "payload": dict(r["payload"]) if r["payload"] else {},
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "sent_at": r["sent_at"],
                }
                for r in rows
            ]
    except Exception as e:
        logger.exception(f"Error fetching user bookings: {e}")
        return []


async def update_booking_sent(booking_id: str) -> bool:
    """Mark booking as sent_to_partner and set sent_at."""
    if not _pool:
        logger.error("DB pool not initialized")
        return False

    try:
        bid = UUID(booking_id)
    except Exception:
        return False

    try:
        async with _pool.acquire() as conn:
            res = await conn.execute(
                """
                UPDATE bookings
                SET status = 'sent_to_partner', sent_at = NOW()
                WHERE id = $1
                """,
                bid,
            )
            return res == "UPDATE 1"
    except Exception as e:
        logger.exception(f"Error updating booking sent: {e}")
        return False


async def get_partner_telegram_id(partner_id: str) -> Optional[int]:
    """Partner telegram_id ni olish (xabar yuborish uchun)."""
    if not _pool:
        logger.error("DB pool not initialized")
        return None
    try:
        pid = UUID(partner_id)
    except Exception:
        return None

    try:
        async with _pool.acquire() as conn:
            tg_id = await conn.fetchval(
                """
                SELECT telegram_id
                FROM partners
                WHERE id = $1 AND is_active = true
                """,
                pid,
            )
            return int(tg_id) if tg_id else None
    except Exception as e:
        logger.exception(f"Error getting partner telegram_id: {e}")
        return None
