from __future__ import annotations

import asyncio
import base64
import os

import redis.asyncio as redis


def valid_key(value: str | None) -> bool:
    if not value or value.startswith("<") or "placeholder" in value.lower():
        return False
    try:
        return len(base64.urlsafe_b64decode(value.encode())) == 32 and len(value) == 44
    except (ValueError, TypeError):
        return False


async def main() -> None:
    url = os.getenv("REDIS_URL")
    reachable = False
    if url and not url.startswith("<") and "placeholder" not in url.lower():
        client = redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        try:
            reachable = bool(await client.ping())
        except Exception:
            reachable = False
        finally:
            await client.aclose()
    print(f"LIVE_OPT_IN={os.getenv('AI_RXOS_LIVE_WORKER_TESTS') == '1'}")
    print(f"PAYLOAD_KEY_PRESENT={bool(os.getenv('EXECUTION_PAYLOAD_KEY'))}")
    print(f"PAYLOAD_KEY_VALID={valid_key(os.getenv('EXECUTION_PAYLOAD_KEY'))}")
    print(f"REDIS_URL_PRESENT={bool(url)}")
    print(f"REDIS_URL_VALID={bool(url and not url.startswith('<') and 'placeholder' not in url.lower())}")
    print(f"REDIS_REACHABLE={reachable}")


asyncio.run(main())
