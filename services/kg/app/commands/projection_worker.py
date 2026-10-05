from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from app.core.config import get_settings
from app.database.canonical_store import canonical_store
from app.database.neo4j import neo4j_manager
from app.services.canonical_projection import CanonicalProjectionWorker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the canonical projection worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--organization-id", type=UUID, default=None)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--interval", type=float, default=5.0)
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    settings = get_settings()
    await canonical_store.initialize(settings.database_url)
    neo4j_manager.init_driver(settings)
    worker = CanonicalProjectionWorker(canonical_store, neo4j_manager, settings)
    try:
        while True:
            delivered = await worker.run_once(args.limit, args.organization_id)
            print(json.dumps({"delivered": delivered, "organization_id": str(args.organization_id) if args.organization_id else None}))
            if args.once:
                return
            await asyncio.sleep(args.interval)
    finally:
        await neo4j_manager.close()
        await canonical_store.close()


if __name__ == "__main__":
    asyncio.run(run())
