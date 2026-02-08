"""
HTTP client with timeouts and retries for external API calls.

All external HTTP requests should use this module to ensure:
- Proper timeouts (no hanging requests)
- Retry logic with exponential backoff
- 429 rate limit handling
"""
import asyncio
from typing import Any

import aiohttp

# Default timeouts (seconds)
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(
    total=30,
    connect=10,
    sock_read=20,
)


async def fetch_json(
    url: str,
    *,
    method: str = "GET",
    json_data: dict | None = None,
    headers: dict | None = None,
    timeout: aiohttp.ClientTimeout | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """
    Fetch JSON from URL with retries and timeouts.
    
    Args:
        url: Target URL
        method: HTTP method (GET, POST, etc.)
        json_data: JSON body for POST/PUT requests
        headers: Custom headers
        timeout: Custom timeout (uses DEFAULT_TIMEOUT if not specified)
        max_retries: Maximum retry attempts
    
    Returns:
        Parsed JSON response as dict
    
    Raises:
        aiohttp.ClientError: On network failure after retries
        ValueError: On non-JSON response
    """
    timeout = timeout or DEFAULT_TIMEOUT
    last_error: Exception | None = None
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method,
                    url,
                    json=json_data,
                    headers=headers,
                ) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        print(f"⏳ HTTP 429, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
        except asyncio.TimeoutError as e:
            last_error = e
            delay = 2 ** attempt
            print(f"⏳ Timeout, retry {attempt + 1}/{max_retries} in {delay}s")
            await asyncio.sleep(delay)
        except aiohttp.ClientError as e:
            last_error = e
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)
    
    raise last_error or RuntimeError("Fetch failed")
