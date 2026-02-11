"""
db_postgres.py - PostgreSQL Database Layer for Safar.uz Bot (Final Phase)

Unified CMS architecture with:
- listings table: hotels, guides, taxis, places
- bookings table: references listings

Uses asyncpg pool for Railway PostgreSQL.
FULLY IDEMPOTENT migrations - safe to run on existing databases.
"""

import asyncio
import html
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
# Database URL + SSL Config
# =============================================================================

def get_database_url() -> str:
    """Get and normalize DATABASE_URL for asyncpg."""
    url = os.getenv("DATABASE_URL", "")
    
    # Railway uses postgres:// but asyncpg needs postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    return url


def get_ssl_context():
    """Get SSL context for Railway PostgreSQL."""
    import ssl
    ssl_mode = os.getenv("PGSSLMODE", "require")
    
    if ssl_mode == "disable":
        return None
    
    # Railway requires SSL
    if ssl_mode in ("require", "verify-ca", "verify-full"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    
    return "prefer"


# =============================================================================
# Schema Migration - FULLY IDEMPOTENT
# =============================================================================

async def _table_exists(conn, table_name: str) -> bool:
    """Check if a table exists."""
    result = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = $1
        )
        """,
        table_name,
    )
    return result


async def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    result = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = $1 
            AND column_name = $2
        )
        """,
        table_name,
        column_name,
    )
    return result


async def _constraint_exists(conn, constraint_name: str) -> bool:
    """Check if a constraint exists."""
    result = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.table_constraints 
            WHERE constraint_schema = 'public' 
            AND constraint_name = $1
        )
        """,
        constraint_name,
    )
    return result


async def _index_exists(conn, index_name: str) -> bool:
    """Check if an index exists."""
    result = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND indexname = $1
        )
        """,
        index_name,
    )
    return result


async def _add_column_if_not_exists(conn, table: str, column: str, definition: str):
    """Add a column if it doesn't exist."""
    if not await _column_exists(conn, table, column):
        await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        logger.info(f"Added column {table}.{column}")


async def _create_index_safe(conn, index_name: str, table: str, columns: str, where: str = None):
    """Create index if it doesn't exist."""
    if not await _index_exists(conn, index_name):
        where_clause = f" WHERE {where}" if where else ""
        await conn.execute(
            f"CREATE INDEX {index_name} ON {table}({columns}){where_clause}"
        )
        logger.info(f"Created index {index_name}")


async def ensure_schema() -> bool:
    """
    Create tables/columns/indexes if missing. 
    FULLY IDEMPOTENT - safe to run multiple times on existing databases.
    Handles migration from old schema (partner_id -> listing_id).
    """
    global _pool
    if not _pool:
        logger.error("DB pool not initialized; cannot ensure schema")
        return False

    try:
        async with _pool.acquire() as conn:
            # Ensure pgcrypto extension for gen_random_uuid() on PG < 13
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            except Exception as e:
                # Non-fatal: gen_random_uuid() is built-in on PG 13+
                logger.warning(f"Could not enable pgcrypto (OK on PG 13+): {e}")

            # =========================================================
            # 1. LISTINGS TABLE
            # =========================================================
            if not await _table_exists(conn, "listings"):
                await conn.execute("""
                    CREATE TABLE listings (
                        id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                        region            text NOT NULL DEFAULT 'zomin',
                        category          text NOT NULL,
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
                    )
                """)
                logger.info("Created listings table")
            else:
                # Add missing columns to existing listings table
                await _add_column_if_not_exists(conn, "listings", "currency", "text NOT NULL DEFAULT 'UZS'")
                await _add_column_if_not_exists(conn, "listings", "phone", "text")
                await _add_column_if_not_exists(conn, "listings", "latitude", "double precision")
                await _add_column_if_not_exists(conn, "listings", "longitude", "double precision")
                await _add_column_if_not_exists(conn, "listings", "address", "text")
                await _add_column_if_not_exists(conn, "listings", "photos", "jsonb NOT NULL DEFAULT '[]'::jsonb")
                await _add_column_if_not_exists(conn, "listings", "is_active", "boolean NOT NULL DEFAULT true")
                await _add_column_if_not_exists(conn, "listings", "subtype", "text")
                await _add_column_if_not_exists(conn, "listings", "region", "text NOT NULL DEFAULT 'zomin'")
                await _add_column_if_not_exists(conn, "listings", "category", "text NOT NULL DEFAULT 'hotel'")
                await _add_column_if_not_exists(conn, "listings", "telegram_admin_id", "bigint NOT NULL DEFAULT 0")

            # =========================================================
            # 2. BOOKINGS TABLE - with partner_id -> listing_id migration
            # =========================================================
            if not await _table_exists(conn, "bookings"):
                await conn.execute("""
                    CREATE TABLE bookings (
                        id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                        listing_id       uuid,
                        user_telegram_id bigint NOT NULL,
                        payload          jsonb NOT NULL DEFAULT '{}'::jsonb,
                        status           text NOT NULL DEFAULT 'new',
                        expires_at       timestamptz,
                        created_at       timestamptz NOT NULL DEFAULT now()
                    )
                """)
                logger.info("Created bookings table")
            else:
                # Handle migration from old schema
                has_partner_id = await _column_exists(conn, "bookings", "partner_id")
                has_listing_id = await _column_exists(conn, "bookings", "listing_id")
                
                if has_partner_id and not has_listing_id:
                    # Rename partner_id to listing_id
                    await conn.execute("ALTER TABLE bookings RENAME COLUMN partner_id TO listing_id")
                    logger.info("Renamed bookings.partner_id -> listing_id")
                elif not has_listing_id:
                    # Add listing_id column
                    await conn.execute("ALTER TABLE bookings ADD COLUMN listing_id uuid")
                    logger.info("Added bookings.listing_id column")
                
                # Add other missing columns
                await _add_column_if_not_exists(conn, "bookings", "user_telegram_id", "bigint NOT NULL DEFAULT 0")
                await _add_column_if_not_exists(conn, "bookings", "payload", "jsonb NOT NULL DEFAULT '{}'::jsonb")
                await _add_column_if_not_exists(conn, "bookings", "status", "text NOT NULL DEFAULT 'new'")
                await _add_column_if_not_exists(conn, "bookings", "expires_at", "timestamptz")
                await _add_column_if_not_exists(conn, "bookings", "created_at", "timestamptz NOT NULL DEFAULT now()")
                
                # Drop old columns that might conflict (service_type from old schema)
                if await _column_exists(conn, "bookings", "service_type"):
                    # Keep it for now, just log
                    logger.info("Note: bookings.service_type exists from old schema")
            
            # =========================================================
            # 3. FOREIGN KEY CONSTRAINT
            # =========================================================
            if not await _constraint_exists(conn, "bookings_listing_id_fkey"):
                # Only add FK if both tables exist and have the required columns
                try:
                    await conn.execute("""
                        ALTER TABLE bookings 
                        ADD CONSTRAINT bookings_listing_id_fkey 
                        FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
                    """)
                    logger.info("Added FK bookings.listing_id -> listings.id")
                except Exception as e:
                    # FK might fail if there's orphaned data
                    logger.warning(f"Could not add FK constraint (likely orphaned data): {e}")
            
            # =========================================================
            # 4. INDEXES
            # =========================================================
            await _create_index_safe(conn, "idx_listings_region_category", "listings", "region, category, is_active")
            await _create_index_safe(conn, "idx_listings_admin", "listings", "telegram_admin_id")
            await _create_index_safe(conn, "idx_bookings_listing_status", "bookings", "listing_id, status")
            await _create_index_safe(conn, "idx_bookings_user_created", "bookings", "user_telegram_id, created_at DESC")
            await _create_index_safe(conn, "idx_bookings_expires", "bookings", "expires_at, status", "expires_at IS NOT NULL")
            
        logger.info("DB schema ensured (listings, bookings) - migration complete")
        return True
        
    except Exception as e:
        logger.exception(f"Failed to ensure schema: {e}")
        return False


async def reset_schema() -> bool:
    """
    Drop and recreate all tables.
    ONLY WORKS IF ALLOW_DB_RESET=true environment variable is set.
    Returns True if reset was performed.
    """
    if os.getenv("ALLOW_DB_RESET", "").lower() != "true":
        logger.warning("DB reset blocked - ALLOW_DB_RESET is not set to 'true'")
        return False
    
    global _pool
    if not _pool:
        return False
    
    try:
        async with _pool.acquire() as conn:
            await conn.execute("DROP TABLE IF EXISTS bookings CASCADE")
            await conn.execute("DROP TABLE IF EXISTS listings CASCADE")
            await conn.execute("DROP TABLE IF EXISTS partners CASCADE")  # Old table
            logger.warning("All tables dropped!")
        
        return await ensure_schema()
    except Exception as e:
        logger.exception(f"Failed to reset schema: {e}")
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
        
        ssl_ctx = get_ssl_context()
        
        _pool = await asyncpg.create_pool(
            url,
            min_size=2,
            max_size=10,
            command_timeout=30,
            ssl=ssl_ctx,
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
# Extended Health Check
# =============================================================================

async def get_schema_info() -> dict:
    """Get detailed schema information for health check."""
    if not _pool:
        return {"error": "Pool not initialized"}
    
    try:
        async with _pool.acquire() as conn:
            info = {"tables": {}}
            
            # Check which tables exist
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
            """)
            
            for t in tables:
                tname = t["table_name"]
                if tname in ("listings", "bookings", "partners"):
                    # Get column info
                    cols = await conn.fetch("""
                        SELECT column_name, data_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = $1
                        ORDER BY ordinal_position
                    """, tname)
                    
                    # Get row count
                    count = await conn.fetchval(f"SELECT COUNT(*) FROM {tname}")
                    
                    info["tables"][tname] = {
                        "columns": [c["column_name"] for c in cols],
                        "count": count,
                    }
            
            return info
    except Exception as e:
        return {"error": str(e)}


async def get_listings_stats() -> dict:
    """Get listing counts by category and subtype."""
    if not _pool:
        return {}
    
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT category, subtype, COUNT(*) as cnt, 
                       SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active
                FROM listings
                GROUP BY category, subtype
                ORDER BY category, subtype
            """)
            
            result = {}
            for r in rows:
                key = r["category"]
                if r["subtype"]:
                    key += f"/{r['subtype']}"
                result[key] = {"total": r["cnt"], "active": r["active"]}
            
            return result
    except Exception as e:
        logger.error(f"Error getting listings stats: {e}")
        return {}


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
    photos = row.get("photos") or []
    if isinstance(photos, str):
        try:
            photos = json.loads(photos)
        except:
            photos = []
    
    return {
        "id": str(row["id"]),
        "region": row.get("region", "zomin"),
        "category": row.get("category", ""),
        "subtype": row.get("subtype"),
        "title": row.get("title", ""),
        "description": row.get("description"),
        "price_from": row.get("price_from"),
        "currency": row.get("currency", "UZS"),
        "phone": row.get("phone"),
        "telegram_admin_id": row.get("telegram_admin_id", 0),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "address": row.get("address"),
        "photos": list(photos) if photos else [],
        "is_active": row.get("is_active", True),
        "created_at": row.get("created_at"),
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
                LEFT JOIN listings l ON b.listing_id = l.id
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
                    "listing_title": r.get("listing_title", "Unknown"),
                }
                for r in rows
            ]
    except Exception as e:
        logger.exception(f"Error fetching expired bookings: {e}")
        return []


def _row_to_booking(row) -> dict:
    """Convert asyncpg row to booking dict."""
    payload = row.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except:
            payload = {}
    
    return {
        "id": str(row["id"]),
        "listing_id": str(row["listing_id"]) if row.get("listing_id") else None,
        "user_telegram_id": row.get("user_telegram_id", 0),
        "payload": dict(payload) if payload else {},
        "status": row.get("status", "new"),
        "expires_at": row.get("expires_at"),
        "created_at": row.get("created_at"),
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


async def get_listings_by_category() -> dict[str, int]:
    """Get active listings counts grouped by category."""
    if not _pool:
        return {}
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT category, COUNT(*) as cnt FROM listings WHERE is_active = true GROUP BY category"
            )
            return {r["category"]: r["cnt"] for r in rows}
    except:
        return {}


async def get_tables_list() -> list[str]:
    """Get list of tables in the database."""
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
                """
            )
            return [r["table_name"] for r in rows]
    except:
        return []


def get_pool_status() -> dict[str, Any]:
    """Get connection pool status."""
    if not _pool:
        return {"status": "not_initialized"}
    
    return {
        "status": "initialized",
        "size": _pool.get_size(),
        "min_size": _pool.get_min_size(),
        "max_size": _pool.get_max_size(),
        "free_connections": _pool.get_size() - _pool.get_idle_size(),
        "idle_connections": _pool.get_idle_size(),
    }


async def reset_database() -> bool:
    """
    Drop and recreate all tables. 
    DANGEROUS: Only use if ALLOW_DB_RESET=true in environment.
    """
    if not _pool:
        logger.error("Pool not initialized")
        return False
    
    # Safety check
    allow_reset = os.getenv("ALLOW_DB_RESET", "false").lower() == "true"
    if not allow_reset:
        logger.error("Database reset blocked: ALLOW_DB_RESET is not 'true'")
        return False
    
    try:
        async with _pool.acquire() as conn:
            logger.warning("🔥 DROPPING ALL TABLES (reset_database called)")
            await conn.execute("DROP TABLE IF EXISTS bookings CASCADE")
            await conn.execute("DROP TABLE IF EXISTS listings CASCADE")
            await conn.execute("DROP TABLE IF EXISTS partners CASCADE")
            logger.info("Tables dropped, recreating schema...")
        
        # Recreate schema
        return await ensure_schema()
    except Exception as e:
        logger.exception(f"Failed to reset database: {e}")
        return False


# =============================================================================
# HTML Safety Helpers (for admin commands)
# =============================================================================

def escape_html(text) -> str:
    """Escape text for safe HTML display in Telegram."""
    if text is None:
        return ""
    return html.escape(str(text), quote=False)
