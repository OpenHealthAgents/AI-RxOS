from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from app.core.config import get_settings
from app.database.canonical_store import canonical_store


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Queue canonical PostgreSQL state for projection replay")
    parser.add_argument("--organization-id", type=UUID, default=None)
    parser.add_argument("--entity-type", default=None)
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    settings = get_settings()
    await canonical_store.initialize(settings.database_url)
    try:
        count = await canonical_store.enqueue_reindex_events(args.organization_id, args.entity_type)
        print(json.dumps({"queued": count, "organization_id": str(args.organization_id) if args.organization_id else None, "entity_type": args.entity_type}))
    finally:
        await canonical_store.close()


if __name__ == "__main__":
    asyncio.run(run())
