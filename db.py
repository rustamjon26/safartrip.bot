"""
SQLite database module for Safar.uz bot.
Handles users and orders persistence with extended query capabilities.

All functions include try/except to handle SQLite errors gracefully and
prevent crashes during database operations.

Production-hardened features:
- WAL mode for better concurrency
- 30s timeout for lock waits
- Exponential backoff retry on "database is locked"
"""
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, TypeVar, Callable

# Database file path (same directory as this module)
DB_PATH = Path(__file__).parent / "bot.db"

# Retry configuration
MAX_RETRIES = 5
BASE_DELAY = 0.1  # seconds

T = TypeVar("T")


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply production PRAGMA settings to a connection."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")


def get_connection() -> sqlite3.Connection:
    """Get a database connection with production settings."""
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30.0,  # Wait up to 30s for locks
        check_same_thread=False,  # Safe for async context
    )
    conn.row_factory = sqlite3.Row
    _configure_connection(conn)
    return conn


@contextmanager
def get_db():
    """Context manager for database connections with auto-close."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def run_with_retry(fn: Callable[[], T]) -> T:
    """
    Execute function with exponential backoff on OperationalError.
    
    Handles 'database is locked' errors by retrying up to MAX_RETRIES times
    with exponential backoff (0.1s, 0.2s, 0.4s, 0.8s, 1.6s).
    """
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                last_error = e
                delay = BASE_DELAY * (2 ** attempt)
                print(f"⏳ Database locked, retry {attempt + 1}/{MAX_RETRIES} in {delay:.2f}s")
                time.sleep(delay)
            else:
                raise
    if last_error:
        raise last_error
    raise RuntimeError("Unexpected retry loop exit")




def init_db() -> bool:
    """Initialize database tables. Called on bot startup. Returns True if successful."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                lang TEXT DEFAULT 'uz'
            )
        """)
        
        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                service TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                date_text TEXT NOT NULL,
                details TEXT NOT NULL,
                status TEXT DEFAULT 'new',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        
        conn.commit()
        conn.close()
        print("✅ Database initialized")
        return True
    except sqlite3.Error as e:
        print(f"❌ Database init error: {e}")
        return False


# ============== USER FUNCTIONS ==============

def upsert_user(user_id: int, username: str | None) -> bool:
    """Insert or update user record. Returns True if successful."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO users (user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
        """, (user_id, username))
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"⚠️ DB error in upsert_user: {e}")
        return False


def get_user_lang(user_id: int) -> str:
    """Get user's language preference. Default 'uz'. Never raises."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        return row["lang"] if row else "uz"
    except sqlite3.Error as e:
        print(f"⚠️ DB error in get_user_lang: {e}")
        return "uz"


def set_user_lang(user_id: int, lang: str) -> bool:
    """Update user's language preference. Returns True if successful."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE users SET lang = ? WHERE user_id = ?
        """, (lang, user_id))
        
        # If user doesn't exist, insert them
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT INTO users (user_id, lang) VALUES (?, ?)
            """, (user_id, lang))
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"⚠️ DB error in set_user_lang: {e}")
        return False


# ============== ORDER FUNCTIONS ==============

def create_order(
    user_id: int,
    username: str | None,
    service: str,
    name: str,
    phone: str,
    date_text: str,
    details: str
) -> int:
    """Create a new order and return its ID. Returns -1 on error."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO orders (user_id, username, service, name, phone, date_text, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, service, name, phone, date_text, details))
        
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return order_id if order_id else -1
    except sqlite3.Error as e:
        print(f"❌ DB error in create_order: {e}")
        return -1  # Consistent with docstring, handlers check for -1


def get_order(order_id: int) -> dict | None:
    """Get order by ID. Returns None if not found or on error."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"⚠️ DB error in get_order: {e}")
        return None


def update_order_status(order_id: int, status: str) -> bool:
    """Update order status and updated_at timestamp. Returns True if updated."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            UPDATE orders 
            SET status = ?, updated_at = ?
            WHERE id = ?
        """, (status, now, order_id))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    except sqlite3.Error as e:
        print(f"⚠️ DB error in update_order_status: {e}")
        return False


def get_orders_by_user(user_id: int, limit: int = 10, offset: int = 0) -> list[dict]:
    """
    Get orders for a specific user.
    Returns list of order dicts, newest first. Empty list on error.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM orders 
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (user_id, limit, offset))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"⚠️ DB error in get_orders_by_user: {e}")
        return []


# ============== ADMIN QUERY FUNCTIONS ==============

def get_orders(
    status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0
) -> list[dict]:
    """
    Get orders with optional status filter.
    Returns list of order dicts, newest first. Empty list on error.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        if status:
            cursor.execute("""
                SELECT * FROM orders 
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (status, limit, offset))
        else:
            cursor.execute("""
                SELECT * FROM orders 
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"⚠️ DB error in get_orders: {e}")
        return []


def get_order_by_id(order_id: int) -> dict | None:
    """Get single order by ID. Alias for get_order."""
    return get_order(order_id)


def search_orders(query: str, limit: int = 10) -> list[dict]:
    """
    Search orders by partial match in name, phone, service, details, username.
    Uses parameterized LIKE queries for safety. Empty list on error.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        search_pattern = f"%{query}%"
        
        cursor.execute("""
            SELECT * FROM orders 
            WHERE name LIKE ? 
               OR phone LIKE ? 
               OR service LIKE ? 
               OR details LIKE ?
               OR username LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (search_pattern, search_pattern, search_pattern, 
              search_pattern, search_pattern, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"⚠️ DB error in search_orders: {e}")
        return []


def filter_orders_by_service(value: str, limit: int = 10) -> list[dict]:
    """Filter orders where service contains value (case-insensitive). Empty list on error."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        search_pattern = f"%{value}%"
        
        cursor.execute("""
            SELECT * FROM orders 
            WHERE LOWER(service) LIKE LOWER(?)
            ORDER BY created_at DESC
            LIMIT ?
        """, (search_pattern, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"⚠️ DB error in filter_orders_by_service: {e}")
        return []


def filter_orders_by_date(value: str, limit: int = 10) -> list[dict]:
    """Filter orders where date_text contains value (case-insensitive). Empty list on error."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        search_pattern = f"%{value}%"
        
        cursor.execute("""
            SELECT * FROM orders 
            WHERE LOWER(date_text) LIKE LOWER(?)
            ORDER BY created_at DESC
            LIMIT ?
        """, (search_pattern, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"⚠️ DB error in filter_orders_by_date: {e}")
        return []


def export_orders(status: Optional[str] = None) -> list[dict]:
    """
    Get all orders for CSV export. Empty list on error.
    If status provided, filter by that status.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        if status:
            cursor.execute("""
                SELECT id, user_id, username, service, name, phone, 
                       date_text, details, status, created_at, updated_at
                FROM orders 
                WHERE status = ?
                ORDER BY created_at DESC
            """, (status,))
        else:
            cursor.execute("""
                SELECT id, user_id, username, service, name, phone, 
                       date_text, details, status, created_at, updated_at
                FROM orders 
                ORDER BY created_at DESC
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"⚠️ DB error in export_orders: {e}")
        return []


def get_orders_count(status: Optional[str] = None) -> int:
    """Get total count of orders, optionally filtered by status. 0 on error."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        if status:
            cursor.execute("SELECT COUNT(*) as cnt FROM orders WHERE status = ?", (status,))
        else:
            cursor.execute("SELECT COUNT(*) as cnt FROM orders")
        
        row = cursor.fetchone()
        conn.close()
        
        return row["cnt"] if row else 0
    except sqlite3.Error as e:
        print(f"⚠️ DB error in get_orders_count: {e}")
        return 0


def backup_database(backup_path: Path) -> bool:
    """
    Create a backup of the database using SQLite backup API.
    Returns True if successful.
    """
    try:
        source = sqlite3.connect(DB_PATH)
        dest = sqlite3.connect(backup_path)
        
        source.backup(dest)
        
        dest.close()
        source.close()
        
        return True
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False
