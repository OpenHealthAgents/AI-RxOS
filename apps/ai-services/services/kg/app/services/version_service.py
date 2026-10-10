import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.database.neo4j import neo4j_manager
from app.cypher import queries
from app.utils.logging import get_logger
from app.core.canonical_security import CanonicalPrincipal
from app.core.neo4j_security import tenant_scope

logger = get_logger(__name__)

class VersionNotFoundError(Exception):
    """Raised when a rollback target references a version that doesn't exist."""

class VersionService:
    @staticmethod
    async def create_new_version(description: Optional[str] = None, *, principal: CanonicalPrincipal) -> int:
        scope = tenant_scope(principal)
        async with neo4j_manager.get_session() as session:
            version_number = await session.execute_write(queries.get_next_version_number, scope=scope)
            version_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc).isoformat()
            desc = description or f"Import version {version_number}"
            await session.execute_write(
                queries.create_version,
                version_id=version_id,
                version_number=version_number,
                description=desc,
                created_at=created_at,
                scope=scope
            )
            logger.info(
                f"Created new graph version {version_number}",
                extra={"version_id": version_id, "version_number": version_number}
            )
            return version_number

    @staticmethod
    async def get_max_active_version(principal: CanonicalPrincipal) -> int:
        scope = tenant_scope(principal)
        async with neo4j_manager.get_session() as session:
            return await session.execute_read(queries.get_max_active_version, scope=scope)

    @staticmethod
    async def list_versions(principal: CanonicalPrincipal) -> List[Dict[str, Any]]:
        scope = tenant_scope(principal)
        async with neo4j_manager.get_session() as session:
            return await session.execute_read(queries.list_versions, scope=scope)

    @staticmethod
    async def rollback_to_version(target_version: int, principal: CanonicalPrincipal) -> int:
        scope = tenant_scope(principal)
        async with neo4j_manager.get_session() as session:
            existing = await session.execute_read(queries.get_version_by_number, version_number=target_version, scope=scope)
            if not existing:
                raise VersionNotFoundError(f"Graph version {target_version} does not exist")

            count = await session.execute_write(queries.rollback_to_version, target_version=target_version, scope=scope)
            logger.info(
                f"Rolled back graph to version {target_version}. Marked {count} newer versions as rolled back.",
                extra={"target_version": target_version, "rolled_back_count": count}
            )
            return count
