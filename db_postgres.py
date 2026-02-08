"""
Async PostgreSQL database layer for partner booking system.

Uses asyncpg with connection pooling for high performance.
All functions include try/except to handle errors gracefully.

Tables:
- partners (id, type, display_name, connect_code, telegram_id, is_active, created_at)
- bookings (id, service_type, partner_id, user_telegram_id, payload, status, created_at)
"""
import os
import asyncio
import json
import logging
from typing import Optional
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# Connection pool
_pool: asyncpg.Pool | None = None


async def init_db_pool() -> bool:
    """
    Initialize the database connection pool.
    Must be called before any other DB operations.
    Returns True if successful.
    """
    global _pool
    
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        logger.error("DATABASE_URL not set, cannot use PostgreSQL")
        return False
    
    try:
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("PostgreSQL connection pool initialized")
        return True
    except Exception as e:
        logger.error(f"Failed to create DB pool: {e}")
        return False


async def close_db_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed")


async def healthcheck() -> tuple[bool, str]:
    """Check database connectivity."""
    if not _pool:
        return False, "Pool not initialized"
    try:
        async with _pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM partners")
            return True, f"OK ({count} partners)"
    except Exception as e:
        return False, f"Error: {e}"


# =============================================================================
# PARTNER FUNCTIONS
# =============================================================================

async def fetch_partners_by_type(partner_type: str) -> list[dict]:
    """
    Fetch active partners by type ('guide', 'taxi', 'hotel').
    Returns list of dict with id, display_name, telegram_id.
    """
    if not _pool:
        logger.error("DB pool not initialized")
        return []
    
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, display_name, telegram_id
                FROM partners
                WHERE type = $1 AND is_active = true
                ORDER BY display_name
            """, partner_type)
            return [
                {
                    "id": str(row["id"]),
                    "display_name": row["display_name"],
                    "telegram_id": row["telegram_id"],
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error fetching partners by type: {e}")
        return []


async def get_partner_by_id(partner_id: str) -> dict | None:
    """Get partner by UUID string."""
    if not _pool:
        return None
    
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, type, display_name, connect_code, telegram_id, is_active, created_at
                FROM partners
                WHERE id = $1
            """, UUID(partner_id))
            if row:
                return {
                    "id": str(row["id"]),
                    "type": row["type"],
                    "display_name": row["display_name"],
                    "connect_code": row["connect_code"],
                    "telegram_id": row["telegram_id"],
                    "is_active": row["is_active"],
                    "created_at": row["created_at"],
                }
            return None
    except Exception as e:
        logger.error(f"Error getting partner by id: {e}")
        return None


async def connect_partner(connect_code: str, telegram_id: int) -> dict | None:
    """
    Connect a partner by their connect_code.
    Sets the telegram_id for the partner.
    Returns partner dict if successful, None if code not found or inactive.
    """
    if not _pool:
        return None
    
    try:
        async with _pool.acquire() as conn:
            # First check if code exists and is active
            partner = await conn.fetchrow("""
                SELECT id, type, display_name, is_active
                FROM partners
                WHERE connect_code = $1
            """, connect_code)
            
            if not partner:
                return None
            
            if not partner["is_active"]:
                return None
            
            # Update telegram_id
            await conn.execute("""
                UPDATE partners
                SET telegram_id = $1
                WHERE connect_code = $2
            """, telegram_id, connect_code)
            
            return {
                "id": str(partner["id"]),
                "type": partner["type"],
                "display_name": partner["display_name"],
            }
    except Exception as e:
        logger.error(f"Error connecting partner: {e}")
        return None


async def get_all_partners() -> list[dict]:
    """Get all partners for admin view."""
    if not _pool:
        return []
    
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, type, display_name, connect_code, telegram_id, is_active
                FROM partners
                ORDER BY type, display_name
            """)
            return [
                {
                    "id": str(row["id"]),
                    "type": row["type"],
                    "display_name": row["display_name"],
                    "connect_code": row["connect_code"],
                    "telegram_id": row["telegram_id"],
                    "is_active": row["is_active"],
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error fetching all partners: {e}")
        return []


# =============================================================================
# BOOKING FUNCTIONS
# =============================================================================

async def create_booking(
    service_type: str,
    partner_id: str,
    user_telegram_id: int,
    payload: dict,
    status: str = "new"
) -> str | None:
    """
    Create a new booking.
    Returns booking ID (UUID string) if successful, None on error.
    """
    if not _pool:
        return None
    
    try:
        async with _pool.acquire() as conn:
            booking_id = await conn.fetchval("""
                INSERT INTO bookings (service_type, partner_id, user_telegram_id, payload, status)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """, service_type, UUID(partner_id), user_telegram_id, json.dumps(payload), status)
            return str(booking_id) if booking_id else None
    except Exception as e:
        logger.error(f"Error creating booking: {e}")
        return None


async def get_booking(booking_id: str) -> dict | None:
    """Get booking by UUID string."""
    if not _pool:
        return None
    
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, service_type, partner_id, user_telegram_id, payload, status, created_at
                FROM bookings
                WHERE id = $1
            """, UUID(booking_id))
            if row:
                return {
                    "id": str(row["id"]),
                    "service_type": row["service_type"],
                    "partner_id": str(row["partner_id"]),
                    "user_telegram_id": row["user_telegram_id"],
                    "payload": json.loads(row["payload"]) if row["payload"] else {},
                    "status": row["status"],
                    "created_at": row["created_at"],
                }
            return None
    except Exception as e:
        logger.error(f"Error getting booking: {e}")
        return None


async def set_booking_status(booking_id: str, status: str) -> bool:
    """Update booking status. Returns True if updated."""
    if not _pool:
        return False
    
    try:
        async with _pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE bookings
                SET status = $1
                WHERE id = $2
            """, status, UUID(booking_id))
            return result == "UPDATE 1"
    except Exception as e:
        logger.error(f"Error updating booking status: {e}")
        return False


async def get_bookings_by_user(user_telegram_id: int, limit: int = 10) -> list[dict]:
    """Get recent bookings for a user."""
    if not _pool:
        return []
    
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT b.id, b.service_type, b.partner_id, b.payload, b.status, b.created_at,
                       p.display_name as partner_name
                FROM bookings b
                LEFT JOIN partners p ON b.partner_id = p.id
                WHERE b.user_telegram_id = $1
                ORDER BY b.created_at DESC
                LIMIT $2
            """, user_telegram_id, limit)
            return [
                {
                    "id": str(row["id"]),
                    "service_type": row["service_type"],
                    "partner_id": str(row["partner_id"]),
                    "partner_name": row["partner_name"],
                    "payload": json.loads(row["payload"]) if row["payload"] else {},
                    "status": row["status"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error fetching user bookings: {e}")
        return []
