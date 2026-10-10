import json
import re
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from pydantic import ValidationError
from app.database.neo4j import neo4j_manager
from app.cypher import queries
from app.schemas.nodes import NodeCreate, NodeResponse, NodeUpdate
from app.schemas.relationships import RelationshipCreate
from app.services import evidence_service
from app.services.version_service import VersionService
from app.utils.logging import get_logger
from app.core.canonical_security import CanonicalPrincipal
from app.core.neo4j_security import tenant_scope

logger = get_logger(__name__)

# How far a caller-supplied confidence may diverge from the computed
# evidence score before it's flagged as suspicious in the logs.
CONFIDENCE_DIVERGENCE_THRESHOLD = 0.3

class GraphService:
    @staticmethod
    def _parse_metadata(metadata_str: Optional[str]) -> Dict[str, Any]:
        if not metadata_str:
            return {}
        try:
            return json.loads(metadata_str)
        except Exception:
            return {"raw": metadata_str}

    @staticmethod
    def _node_to_dict(node_data: Dict[str, Any]) -> Dict[str, Any]:
        if "metadata" in node_data:
            node_data["metadata"] = GraphService._parse_metadata(node_data["metadata"])
        return node_data

    @staticmethod
    async def create_node(node_in: NodeCreate, principal: CanonicalPrincipal) -> Dict[str, Any]:
        node_id = str(node_in.id or uuid4())
        created_at = (node_in.created_at or datetime.now(timezone.utc)).isoformat()
        updated_at = (node_in.updated_at or datetime.now(timezone.utc)).isoformat()
        metadata_json = json.dumps(node_in.metadata)
        
        # Get active version to tag the node
        scope = tenant_scope(principal)
        version = await VersionService.get_max_active_version(principal)
        
        async with neo4j_manager.get_session() as session:
            node_data = await session.execute_write(
                queries.create_node,
                label=node_in.label,
                node_id=node_id,
                name=node_in.name,
                description=node_in.description,
                source=node_in.source,
                metadata_json=metadata_json,
                created_at=created_at,
                updated_at=updated_at,
                version=version,
                scope=scope
            )
            return GraphService._node_to_dict(node_data)

    @staticmethod
    async def get_node(node_id: str, principal: CanonicalPrincipal) -> Optional[Dict[str, Any]]:
        scope = tenant_scope(principal)
        max_version = await VersionService.get_max_active_version(principal)
        async with neo4j_manager.get_session() as session:
            node_data = await session.execute_read(queries.get_node, node_id=node_id, max_version=max_version, scope=scope)
            if not node_data:
                return None
            return GraphService._node_to_dict(node_data)

    @staticmethod
    async def update_node(node_id: str, node_in: NodeUpdate, principal: CanonicalPrincipal) -> Optional[Dict[str, Any]]:
        scope = tenant_scope(principal)
        max_version = await VersionService.get_max_active_version(principal)
        updated_at = (node_in.updated_at or datetime.now(timezone.utc)).isoformat()
        metadata_json = json.dumps(node_in.metadata) if node_in.metadata is not None else None
        
        async with neo4j_manager.get_session() as session:
            node_data = await session.execute_write(
                queries.update_node,
                node_id=node_id,
                name=node_in.name,
                description=node_in.description,
                source=node_in.source,
                metadata_json=metadata_json,
                updated_at=updated_at,
                max_version=max_version,
                scope=scope
            )
            if not node_data:
                return None
            return GraphService._node_to_dict(node_data)

    @staticmethod
    async def delete_node(node_id: str, principal: CanonicalPrincipal) -> bool:
        scope = tenant_scope(principal)
        max_version = await VersionService.get_max_active_version(principal)
        async with neo4j_manager.get_session() as session:
            count = await session.execute_write(queries.delete_node, node_id=node_id, max_version=max_version, scope=scope)
            return count > 0

    @staticmethod
    async def list_nodes(label: Optional[str] = None, page: int = 1, size: int = 20, *, principal: CanonicalPrincipal) -> Tuple[List[Dict[str, Any]], int]:
        scope = tenant_scope(principal)
        max_version = await VersionService.get_max_active_version(principal)
        async with neo4j_manager.get_session() as session:
            nodes_data, total = await session.execute_read(
                queries.list_nodes,
                max_version=max_version,
                label=label,
                page=page,
                size=size,
                scope=scope
            )
            parsed_nodes = []
            for n in nodes_data:
                node = GraphService._node_to_dict(n)
                try:
                    NodeResponse.model_validate(node)
                except ValidationError as e:
                    # Belt-and-suspenders: queries.VALID_DOMAIN_NODE_FILTER
                    # already excludes malformed/internal nodes at the
                    # Cypher level, but a row that somehow still doesn't
                    # match NodeResponse must never crash the whole page.
                    logger.warning(
                        f"Skipping node that doesn't match NodeResponse schema: {str(e)}",
                        extra={"node_id": node.get("id"), "label": node.get("label")}
                    )
                    continue
                parsed_nodes.append(node)
            return parsed_nodes, total

    @staticmethod
    async def create_relationship(rel_in: RelationshipCreate, principal: CanonicalPrincipal) -> Optional[Dict[str, Any]]:
        rel_id = str(rel_in.id or uuid4())
        created_at = (rel_in.created_at or datetime.now(timezone.utc)).isoformat()
        scope = tenant_scope(principal)
        max_version = await VersionService.get_max_active_version(principal)

        async with neo4j_manager.get_session() as session:
            corroboration_count = await session.execute_read(
                queries.count_relationships_between,
                from_node_id=str(rel_in.from_node_id),
                to_node_id=str(rel_in.to_node_id),
                relationship_type=rel_in.type,
                max_version=max_version,
                scope=scope
            )
            computed_confidence = evidence_service.compute_confidence(
                source=rel_in.source,
                evidence=rel_in.evidence,
                corroboration_count=corroboration_count
            )

            if rel_in.confidence is None:
                confidence = computed_confidence
            else:
                confidence = rel_in.confidence
                if abs(confidence - computed_confidence) > CONFIDENCE_DIVERGENCE_THRESHOLD:
                    logger.warning(
                        "Caller-supplied confidence diverges from computed evidence score.",
                        extra={
                            "type": rel_in.type,
                            "caller_confidence": confidence,
                            "computed_confidence": computed_confidence,
                        }
                    )

            rel_data = await session.execute_write(
                queries.create_relationship,
                from_node_id=str(rel_in.from_node_id),
                to_node_id=str(rel_in.to_node_id),
                relationship_type=rel_in.type,
                rel_id=rel_id,
                evidence=rel_in.evidence,
                confidence=confidence,
                source=rel_in.source,
                created_at=created_at,
                version=max_version,
                max_version=max_version,
                scope=scope
            )
            return rel_data

    @staticmethod
    async def delete_relationship(rel_id: str, principal: CanonicalPrincipal) -> bool:
        scope = tenant_scope(principal)
        max_version = await VersionService.get_max_active_version(principal)
        async with neo4j_manager.get_session() as session:
            count = await session.execute_write(queries.delete_relationship, rel_id=rel_id, max_version=max_version, scope=scope)
            return count > 0

    @staticmethod
    async def list_relationships(rel_type: Optional[str] = None, page: int = 1, size: int = 20, *, principal: CanonicalPrincipal) -> Tuple[List[Dict[str, Any]], int]:
        scope = tenant_scope(principal)
        max_version = await VersionService.get_max_active_version(principal)
        async with neo4j_manager.get_session() as session:
            rels_data, total = await session.execute_read(
                queries.list_relationships,
                max_version=max_version,
                rel_type=rel_type,
                page=page,
                size=size,
                scope=scope
            )
            return rels_data, total

    @staticmethod
    async def get_neighbors(node_id: str, principal: CanonicalPrincipal) -> Optional[Dict[str, Any]]:
        scope = tenant_scope(principal)
        max_version = await VersionService.get_max_active_version(principal)
        async with neo4j_manager.get_session() as session:
            data = await session.execute_read(queries.get_neighbors, node_id=node_id, max_version=max_version, scope=scope)
            if not data:
                return None
            data["node"] = GraphService._node_to_dict(data["node"])
            for neighbor in data["neighbors"]:
                neighbor["node"] = GraphService._node_to_dict(neighbor["node"])
            return data

    @staticmethod
    async def get_path(start_node_id: str, end_node_id: str, max_depth: int = 3, *, principal: CanonicalPrincipal) -> Optional[Dict[str, Any]]:
        scope = tenant_scope(principal)
        max_version = await VersionService.get_max_active_version(principal)
        async with neo4j_manager.get_session() as session:
            path_data = await session.execute_read(
                queries.get_path,
                start_node_id=start_node_id,
                end_node_id=end_node_id,
                max_depth=max_depth,
                max_version=max_version,
                scope=scope
            )
            if not path_data:
                return None
            for node in path_data["nodes"]:
                GraphService._node_to_dict(node)
            return path_data

    @staticmethod
    async def get_subgraph(node_ids: List[str], relationship_types: Optional[List[str]] = None, *, principal: CanonicalPrincipal) -> Dict[str, Any]:
        scope = tenant_scope(principal)
        max_version = await VersionService.get_max_active_version(principal)
        async with neo4j_manager.get_session() as session:
            subgraph_data = await session.execute_read(
                queries.get_subgraph,
                node_ids=node_ids,
                relationship_types=relationship_types,
                max_version=max_version,
                scope=scope
            )
            for node in subgraph_data["nodes"]:
                GraphService._node_to_dict(node)
            return subgraph_data

    @staticmethod
    async def search_nodes(q: str, label: Optional[str] = None, limit: int = 10, *, principal: CanonicalPrincipal) -> List[Dict[str, Any]]:
        scope = tenant_scope(principal)
        max_version = await VersionService.get_max_active_version(principal)
        async with neo4j_manager.get_session() as session:
            nodes_data = await session.execute_read(
                queries.search_nodes,
                q=q,
                label=label,
                max_version=max_version,
                limit=limit,
                scope=scope
            )
            return [GraphService._node_to_dict(n) for n in nodes_data]

    @staticmethod
    async def search_relevance(
        query: str, document_ids: List[str], *, principal: CanonicalPrincipal
    ) -> Dict[str, float]:
        scope = tenant_scope(principal)
        tokens = list(dict.fromkeys(
            token for token in re.findall(r"[a-z0-9][a-z0-9-]{2,}", query.casefold())
        ))
        if not tokens or not document_ids:
            return {}
        async with neo4j_manager.get_session() as session:
            return await session.execute_read(
                queries.search_relevance,
                query_tokens=tokens,
                document_ids=document_ids[:100],
                scope=scope,
            )
