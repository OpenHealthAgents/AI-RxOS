from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

import asyncpg

from app.core.canonical_security import CanonicalPrincipal
from app.database.canonical_store import CanonicalStore
from app.services.backfill import CheckpointStore, run_literature_backfill
from app.services.canonical_repository import CanonicalRepository


def _principal() -> CanonicalPrincipal:
    organization = os.getenv("LITERATURE_BACKFILL_ORGANIZATION_ID")
    user = os.getenv("LITERATURE_BACKFILL_USER_ID")
    if bool(organization) != bool(user):
        raise RuntimeError("LITERATURE_BACKFILL_ORGANIZATION_ID and USER_ID must be set together")
    organization_id = UUID(organization) if organization else None
    user_id = UUID(user) if user else None
    return CanonicalPrincipal(user_id, organization_id, frozenset({"operator"}), frozenset())


async def _run(args: argparse.Namespace) -> dict[str, object]:
    database_url = os.environ["DATABASE_URL"]
    store = CanonicalStore()
    literature_pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
    try:
        await store.initialize(database_url)
        principal = _principal()
        checkpoint = None if args.dry_run else CheckpointStore(Path(args.checkpoint))
        async with literature_pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.literature_organization_id', $1, true)",
                    str(principal.organization_id) if principal.organization_id else "",
                )
                await connection.execute(
                    "SELECT set_config('app.literature_system_scope', $1, true)",
                    "true" if principal.organization_id is None else "false",
                )
                result = await run_literature_backfill(
                    CanonicalRepository(store),
                    principal,
                    connection,
                    checkpoint,
                    dry_run=args.dry_run,
                    create_if_unresolved=args.create_if_unresolved,
                )
        return result.as_dict()
    finally:
        await literature_pool.close()
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay historical literature through B01 into canonical PostgreSQL")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--status", action="store_true")
    parser.add_argument("--create-if-unresolved", action="store_true")
    parser.add_argument("--checkpoint", default=os.getenv("LITERATURE_BACKFILL_CHECKPOINT", "data/literature-backfill.json"))
    args = parser.parse_args()
    if args.status:
        checkpoint = CheckpointStore(Path(args.checkpoint))
        print(json.dumps({"checkpoint": args.checkpoint, "completed": sorted(checkpoint.completed)}))
        return
    print(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
