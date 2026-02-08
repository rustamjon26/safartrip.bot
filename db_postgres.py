"""
db_postgres.py - PostgreSQL Database Layer for Safar.uz Bot (Final Phase)

Unified CMS architecture with:
- listings table: hotels, guides, taxis, places
- bookings table: references listings

Uses asyncpg pool for Railway PostgreSQL.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# Global pool
_pool = None


# =============================================================================
# Schema SQL
# =============================================================================

_SCHEMA_SQL = """
-- Listings table (unified for all categories)
CREATE TABLE IF NOT EXISTS listings (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    region            text NOT NULL DEFAULT 'zomin',
    category          text NOT NULL CHECK (category IN ('hotel', 'guide', 'taxi', 'place')),
    subtype           text,
    title             text NOT NULL,
    description       text,
    price_from        integer,
    currency          text NOT NULL DEFAULT 'UZS',
    phone             text,
    telegram_admin_id bigint NOT NULL,
    latitude          double precision,
    longitude         double precision,
    address           text,
    photos            jsonb NOT NULL DEFAULT '[]'::jsonb,
    is_active         boolean NOT NULL DEFAULT true,
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- Bookings table (references listings)
CREATE TABLE IF NOT EXISTS bookings (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id       uuid NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    user_telegram_id bigint NOT NULL,
    payload          jsonb NOT NULL DEFAULT '{}'::jsonb,
    status           text NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'sent', 'accepted', 'rejected', 'timeout')),
    expires_at       timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_listings_region_category
    ON listings(region, category, is_active);

CREATE INDEX IF NOT EXISTS idx_listings_admin
    ON listings(telegram_admin_id);

CREATE INDEX IF NOT EXISTS idx_bookings_listing_status
    ON bookings(listing_id, status);

CREATE INDEX IF NOT EXISTS idx_bookings_user_created
    ON bookings(user_telegram_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bookings_expires
    ON bookings(expires_at, status) WHERE expires_at IS NOT NULL;
"""

# Migration SQL for backward compatibility
_MIGRATIONS_SQL = [
    "ALTER TABLE listings ADD COLUMN IF NOT EXISTS currency text NOT NULL DEFAULT 'UZS'",
    "ALTER TABLE listings ADD COLUMN IF NOT EXISTS phone text",
    "ALTER TABLE listings ADD COLUMN IF NOT EXISTS latitude double precision",
    "ALTER TABLE listings ADD COLUMN IF NOT EXISTS longitude double precision",
    "ALTER TABLE listings ADD COLUMN IF NOT EXISTS address text",
]


def get_database_url() -> str:
    """Get and normalize DATABASE_URL for asyncpg."""
    url = os.getenv("DATABASE_URL", "")
    
    # Railway uses postgres:// but asyncpg needs postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    return url


async def ensure_schema() -> bool:
    """Create tables/indexes if missing. Safe to run multiple times."""
    global _pool
    if not _pool:
        logger.error("DB pool not initialized; cannot ensure schema")
        return False

    try:
        async with _pool.acquire() as conn:
            # Create tables and indexes
            await conn.execute(_SCHEMA_SQL)
            
            # Run migrations
            for sql in _MIGRATIONS_SQL:
                try:
                    await conn.execute(sql)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        logger.warning(f"Migration warning: {e}")
                        
        logger.info("DB schema ensured (listings, bookings)")
        return True
    except Exception as e:
        logger.exception(f"Failed to ensure schema: {e}")
        return False


# =============================================================================
# Pool Lifecycle
# =============================================================================

async def init_pool() -> bool:
    """Initialize asyncpg connection pool."""
    global _pool
    
    if _pool:
        logger.info("Pool already initialized")
        return True
    
    url = get_database_url()
    if not url:
        logger.error("DATABASE_URL not set")
        return False
    
    try:
        import asyncpg
        
        # Railway may require SSL
        ssl_mode = os.getenv("PGSSLMODE", "prefer")
        
        _pool = await asyncpg.create_pool(
            url,
            min_size=2,
            max_size=10,
            command_timeout=30,
            ssl=ssl_mode if ssl_mode != "disable" else None,
        )
        
        logger.info("PostgreSQL pool initialized")
        return True
    except Exception as e:
        logger.exception(f"Failed to init pool: {e}")
        return False


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")


async def healthcheck() -> tuple[bool, str]:
    """Check database connectivity."""
    global _pool
    if not _pool:
        return False, "Pool not initialized"
    
    try:
        async with _pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            return result == 1, "OK"
    except Exception as e:
        return False, str(e)


# =============================================================================
# Listings CRUD
# =============================================================================

async def create_listing(data: dict[str, Any]) -> Optional[str]:
    """
    Create a new listing.
    
    Returns:
        Listing UUID string or None on error
    """
    if not _pool:
        return None

    try:
        async with _pool.acquire() as conn:
            listing_id = await conn.fetchval(
                """
                INSERT INTO listings(
                    region, category, subtype, title, description,
                    price_from, currency, phone, telegram_admin_id,
                    latitude, longitude, address, photos, is_active
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, true)
                RETURNING id
                """,
                data.get("region", "zomin").lower(),
                data.get("category", "").lower(),
                data.get("subtype"),
                data.get("title", ""),
                data.get("description"),
                data.get("price_from"),
                data.get("currency", "UZS"),
                data.get("phone"),
                int(data.get("telegram_admin_id", 0)),
                data.get("latitude"),
                data.get("longitude"),
                data.get("address"),
                json.dumps(data.get("photos", [])),
            )
            logger.info(f"Created listing {listing_id}")
            return str(listing_id) if listing_id else None
    except Exception as e:
        logger.exception(f"Error creating listing: {e}")
        return None


async def get_listing(listing_id: str) -> Optional[dict]:
    """Get a single listing by ID."""
    if not _pool:
        return None

    try:
        lid = UUID(listing_id)
    except:
        return None

    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, region, category, subtype, title, description,
                       price_from, currency, phone, telegram_admin_id,
                       latitude, longitude, address, photos, is_active, created_at
                FROM listings WHERE id = $1
                """,
                lid,
            )
            if not row:
                return None
            return _row_to_listing(row)
    except Exception as e:
        logger.exception(f"Error getting listing: {e}")
        return None


async def fetch_listings(
    region: str = None,
    category: str = None,
    subtype: str = None,
    active_only: bool = True,
) -> list[dict]:
    """Fetch listings with optional filters."""
    if not _pool:
        return []

    try:
        conditions = []
        params = []
        idx = 1

        if active_only:
            conditions.append("is_active = true")

        if region:
            conditions.append(f"region = ${idx}")
            params.append(region.lower())
            idx += 1

        if category:
            conditions.append(f"category = ${idx}")
            params.append(category.lower())
            idx += 1

        if subtype:
            conditions.append(f"subtype = ${idx}")
            params.append(subtype.lower())
            idx += 1

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, region, category, subtype, title, description,
                       price_from, currency, phone, telegram_admin_id,
                       latitude, longitude, address, photos, is_active, created_at
                FROM listings
                {where}
                ORDER BY created_at DESC
                """,
                *params,
            )
            return [_row_to_listing(r) for r in rows]
    except Exception as e:
        logger.exception(f"Error fetching listings: {e}")
        return []


async def fetch_listings_by_admin(admin_id: int) -> list[dict]:
    """Get all listings owned by a specific admin."""
    if not _pool:
        return []

    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, region, category, subtype, title, description,
                       price_from, currency, phone, telegram_admin_id,
                       latitude, longitude, address, photos, is_active, created_at
                FROM listings
                WHERE telegram_admin_id = $1
                ORDER BY created_at DESC
                """,
                int(admin_id),
            )
            return [_row_to_listing(r) for r in rows]
    except Exception as e:
        logger.exception(f"Error fetching listings by admin: {e}")
        return []


async def toggle_listing_active(listing_id: str, is_active: bool) -> bool:
    """Toggle listing active status."""
    if not _pool:
        return False

    try:
        lid = UUID(listing_id)
    except:
        return False

    try:
        async with _pool.acquire() as conn:
            res = await conn.execute(
                "UPDATE listings SET is_active = $1 WHERE id = $2",
                is_active,
                lid,
            )
            return res == "UPDATE 1"
    except Exception as e:
        logger.exception(f"Error toggling listing: {e}")
        return False


async def delete_listing(listing_id: str) -> bool:
    """Delete a listing."""
    if not _pool:
        return False

    try:
        lid = UUID(listing_id)
    except:
        return False

    try:
        async with _pool.acquire() as conn:
            res = await conn.execute("DELETE FROM listings WHERE id = $1", lid)
            return res == "DELETE 1"
    except Exception as e:
        logger.exception(f"Error deleting listing: {e}")
        return False


def _row_to_listing(row) -> dict:
    """Convert asyncpg row to listing dict."""
    return {
        "id": str(row["id"]),
        "region": row["region"],
        "category": row["category"],
        "subtype": row["subtype"],
        "title": row["title"],
        "description": row["description"],
        "price_from": row["price_from"],
        "currency": row["currency"],
        "phone": row["phone"],
        "telegram_admin_id": row["telegram_admin_id"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "address": row["address"],
        "photos": list(row["photos"]) if row["photos"] else [],
        "is_active": row["is_active"],
        "created_at": row["created_at"],
    }


# =============================================================================
# Bookings CRUD
# =============================================================================

async def create_booking(
    listing_id: str,
    user_telegram_id: int,
    payload: dict,
    expires_minutes: int = 5,
) -> Optional[str]:
    """
    Create a new booking with expiration.
    
    Returns:
        Booking UUID string or None on error
    """
    if not _pool:
        return None

    try:
        lid = UUID(listing_id)
    except:
        return None

    try:
        expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)
        
        async with _pool.acquire() as conn:
            booking_id = await conn.fetchval(
                """
                INSERT INTO bookings(listing_id, user_telegram_id, payload, status, expires_at)
                VALUES ($1, $2, $3::jsonb, 'new', $4)
                RETURNING id
                """,
                lid,
                int(user_telegram_id),
                json.dumps(payload),
                expires_at,
            )
            logger.info(f"Created booking {booking_id}")
            return str(booking_id) if booking_id else None
    except Exception as e:
        logger.exception(f"Error creating booking: {e}")
        return None


async def get_booking(booking_id: str) -> Optional[dict]:
    """Get a booking by ID."""
    if not _pool:
        return None

    try:
        bid = UUID(booking_id)
    except:
        return None

    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT b.id, b.listing_id, b.user_telegram_id, b.payload,
                       b.status, b.expires_at, b.created_at,
                       l.title as listing_title, l.category, l.telegram_admin_id,
                       l.price_from, l.currency
                FROM bookings b
                JOIN listings l ON b.listing_id = l.id
                WHERE b.id = $1
                """,
                bid,
            )
            if not row:
                return None
            return _row_to_booking(row)
    except Exception as e:
        logger.exception(f"Error getting booking: {e}")
        return None


async def update_booking_status(booking_id: str, status: str) -> bool:
    """Update booking status."""
    if not _pool:
        return False

    try:
        bid = UUID(booking_id)
    except:
        return False

    try:
        async with _pool.acquire() as conn:
            res = await conn.execute(
                "UPDATE bookings SET status = $1 WHERE id = $2",
                status,
                bid,
            )
            return res == "UPDATE 1"
    except Exception as e:
        logger.exception(f"Error updating booking status: {e}")
        return False


async def fetch_expired_bookings() -> list[dict]:
    """
    Atomically fetch and mark expired bookings as timeout.
    Uses UPDATE ... RETURNING to be safe with multiple workers.
    
    Returns:
        List of expired bookings (id, user_telegram_id, listing_title)
    """
    if not _pool:
        return []

    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE bookings b
                SET status = 'timeout'
                FROM listings l
                WHERE b.listing_id = l.id
                  AND b.status IN ('new', 'sent')
                  AND b.expires_at < NOW()
                RETURNING b.id, b.user_telegram_id, l.title as listing_title
                """
            )
            return [
                {
                    "id": str(r["id"]),
                    "user_telegram_id": r["user_telegram_id"],
                    "listing_title": r["listing_title"],
                }
                for r in rows
            ]
    except Exception as e:
        logger.exception(f"Error fetching expired bookings: {e}")
        return []


def _row_to_booking(row) -> dict:
    """Convert asyncpg row to booking dict."""
    return {
        "id": str(row["id"]),
        "listing_id": str(row["listing_id"]),
        "user_telegram_id": row["user_telegram_id"],
        "payload": dict(row["payload"]) if row["payload"] else {},
        "status": row["status"],
        "expires_at": row["expires_at"],
        "created_at": row["created_at"],
        "listing_title": row.get("listing_title"),
        "category": row.get("category"),
        "telegram_admin_id": row.get("telegram_admin_id"),
        "price_from": row.get("price_from"),
        "currency": row.get("currency"),
    }


# =============================================================================
# Stats (for admin health check)
# =============================================================================

async def get_listings_count() -> int:
    """Get count of active listings."""
    if not _pool:
        return 0
    try:
        async with _pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM listings WHERE is_active = true") or 0
    except:
        return 0


async def get_bookings_count() -> int:
    """Get total bookings count."""
    if not _pool:
        return 0
    try:
        async with _pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM bookings") or 0
    except:
        return 0


async def get_bookings_by_status() -> dict[str, int]:
    """Get booking counts grouped by status."""
    if not _pool:
        return {}
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT status, COUNT(*) as cnt FROM bookings GROUP BY status"
            )
            return {r["status"]: r["cnt"] for r in rows}
    except:
        return {}
