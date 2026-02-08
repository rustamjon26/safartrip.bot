"""
Simple in-memory rate limiter for anti-spam protection.
Limits order creation to 1 per 10 seconds per user.
"""
import time
from typing import Dict

# Store last order timestamp per user_id
_last_order_time: Dict[int, float] = {}

# Rate limit: minimum seconds between orders
RATE_LIMIT_SECONDS = 10


def can_create_order(user_id: int) -> bool:
    """
    Check if user can create an order (not rate limited).
    Returns True if allowed, False if rate limited.
    """
    now = time.time()
    last_time = _last_order_time.get(user_id, 0)
    
    if now - last_time < RATE_LIMIT_SECONDS:
        return False
    
    return True


def record_order_created(user_id: int) -> None:
    """
    Record that user has created an order.
    Call this after successful order creation.
    """
    _last_order_time[user_id] = time.time()


def get_remaining_seconds(user_id: int) -> int:
    """
    Get remaining seconds until user can create next order.
    Returns 0 if not rate limited.
    """
    now = time.time()
    last_time = _last_order_time.get(user_id, 0)
    remaining = RATE_LIMIT_SECONDS - (now - last_time)
    
    return max(0, int(remaining))
