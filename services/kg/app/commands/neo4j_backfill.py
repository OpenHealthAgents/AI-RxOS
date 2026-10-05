from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from app.core.canonical_security import CanonicalPrincipal
from app.core.config import get_settings
from app.database.canonical_store import CanonicalStore
from app.database.neo4j import neo4j_manager
from app.services.backfill import CheckpointStore
from app.services.canonical_repository import CanonicalRepository
from app.services.neo4j_backfill import run_neo4j_backfill


def _principal() -> CanonicalPrincipal:
    organization = os.getenv("NEO4J_BACKFILL_ORGANIZATION_ID")
    user = os.getenv("NEO4J_BACKFILL_USER_ID")
    if bool(organization) != bool(user):
        raise RuntimeError("NEO4J_BACKFILL_ORGANIZATION_ID and USER_ID must be set together")
    return CanonicalPrincipal(
        UUID(user) if user else None,
        UUID(organization) if organization else None,
        frozenset({"operator"}),
        frozenset({"graph:system"}) if not organization else frozenset(),
    )


async def _run(args: argparse.Namespace) -> dict[str, object]:
    settings = get_settings()
    store = CanonicalStore()
    await store.initialize(settings.database_url)
    neo4j_manager.init_driver(settings)
    try:
        checkpoint = None if args.dry_run else CheckpointStore(Path(args.checkpoint))
        async with neo4j_manager.get_session() as session:
            return await run_neo4j_backfill(
                CanonicalRepository(store),
                _principal(),
                session,
                checkpoint,
                dry_run=args.dry_run,
                create_if_unresolved=args.create_if_unresolved,
            )
    finally:
        await neo4j_manager.close()
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay legacy Neo4j nodes through B01 into canonical PostgreSQL")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--status", action="store_true")
    parser.add_argument("--create-if-unresolved", action="store_true")
    parser.add_argument("--checkpoint", default=os.getenv("NEO4J_BACKFILL_CHECKPOINT", "data/neo4j-backfill.json"))
    args = parser.parse_args()
    if args.status:
        checkpoint = CheckpointStore(Path(args.checkpoint))
        print(json.dumps({"checkpoint": args.checkpoint, "completed": sorted(checkpoint.completed)}))
        return
    print(json.dumps(asyncio.run(_run(args)), default=str))


if __name__ == "__main__":
    main()
