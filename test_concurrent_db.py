"""
Test script for concurrent database writes.
Simulates multiple simultaneous order creations to verify WAL mode and retry logic.

Run: python test_concurrent_db.py
"""
import asyncio
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import db


def create_test_order(i: int) -> tuple[int, float, int]:
    """Create a test order and return (order_id, elapsed_time, thread_id)."""
    import threading
    
    start = time.time()
    order_id = db.create_order(
        user_id=1000000 + i,
        username=f"test_user_{i}",
        service="🏨 Test Service",
        name=f"Test User {i}",
        phone=f"+998901234{i:03d}",
        date_text="2025-02-10",
        details=f"Concurrent test order #{i}",
    )
    elapsed = time.time() - start
    return order_id, elapsed, threading.current_thread().ident


def main():
    print("=" * 60)
    print("SQLite Concurrency Test")
    print("=" * 60)
    
    # Initialize database
    print("\n🔧 Initializing database...")
    db.init_db()
    
    # Count initial orders
    initial_count = db.get_orders_count()
    print(f"📊 Initial order count: {initial_count}")
    
    # Test configuration
    num_concurrent = 20  # Number of concurrent writes
    
    print(f"\n🚀 Starting {num_concurrent} concurrent order creations...")
    start_time = time.time()
    
    # Use ThreadPoolExecutor for true concurrency
    with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        futures = [executor.submit(create_test_order, i) for i in range(num_concurrent)]
        results = [f.result() for f in futures]
    
    total_time = time.time() - start_time
    
    # Analyze results
    successful = [r for r in results if r[0] > 0]
    failed = [r for r in results if r[0] <= 0]
    
    print(f"\n📈 Results:")
    print(f"   ✅ Successful: {len(successful)}")
    print(f"   ❌ Failed: {len(failed)}")
    print(f"   ⏱️  Total time: {total_time:.2f}s")
    
    if successful:
        avg_time = sum(r[1] for r in successful) / len(successful)
        max_time = max(r[1] for r in successful)
        print(f"   📊 Avg write time: {avg_time:.3f}s")
        print(f"   📊 Max write time: {max_time:.3f}s")
    
    # Verify final count
    final_count = db.get_orders_count()
    expected_count = initial_count + len(successful)
    print(f"\n📊 Final order count: {final_count}")
    print(f"   Expected: {expected_count}")
    
    if final_count == expected_count and len(failed) == 0:
        print("\n✅ PASS: All concurrent writes succeeded!")
        return 0
    else:
        print("\n❌ FAIL: Some writes failed or count mismatch")
        return 1


if __name__ == "__main__":
    sys.exit(main())
