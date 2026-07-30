import csv
import io
import json
import time
from uuid import UUID, uuid4
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.database.neo4j import neo4j_manager
from app.cypher import queries
from app.schemas.nodes import NodeCreate
from app.schemas.relationships import RelationshipCreate
from app.schemas.imports import ImportJSONRequest, ImportResponse
from app.services.version_service import VersionService
from app.utils.logging import get_logger

logger = get_logger(__name__)

IMPORT_BATCH_SIZE = 500

def _chunks(rows: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [rows[i:i + size] for i in range(0, len(rows), size)]

class ImportService:
    @staticmethod
    def _parse_csv_nodes(content_str: str) -> List[NodeCreate]:
        nodes = []
        reader = csv.DictReader(io.StringIO(content_str))
        for row in reader:
            if not row.get("label") or not row.get("name"):
                continue
            
            node_id = None
            if row.get("id"):
                try:
                    node_id = UUID(row["id"].strip())
                except ValueError:
                    pass

            metadata = {}
            if row.get("metadata"):
                try:
                    metadata = json.loads(row["metadata"])
                except Exception:
                    pass
            
            nodes.append(NodeCreate(
                label=row["label"].strip(),
                id=node_id,
                name=row["name"].strip(),
                description=row.get("description", "").strip() or None,
                source=row.get("source", "").strip() or None,
                metadata=metadata
            ))
        return nodes

    @staticmethod
    def _parse_csv_relationships(content_str: str) -> List[RelationshipCreate]:
        relationships = []
        reader = csv.DictReader(io.StringIO(content_str))
        for row in reader:
            if not row.get("from_node_id") or not row.get("to_node_id") or not row.get("type"):
                continue
            
            rel_id = None
            if row.get("id"):
                try:
                    rel_id = UUID(row["id"].strip())
                except ValueError:
                    pass

            confidence = None
            if row.get("confidence"):
                try:
                    confidence = float(row["confidence"])
                except ValueError:
                    pass

            relationships.append(RelationshipCreate(
                from_node_id=UUID(row["from_node_id"].strip()),
                to_node_id=UUID(row["to_node_id"].strip()),
                type=row["type"].strip(),
                id=rel_id,
                evidence=row.get("evidence", "").strip() or None,
                confidence=confidence,
                source=row.get("source", "").strip() or None
            ))
        return relationships

    @staticmethod
    async def import_json(req: ImportJSONRequest) -> ImportResponse:
        start_time = time.time()
        
        # 1. Create version record
        version_number = await VersionService.create_new_version(req.description)
        
        # 2. Group rows by label/type (Cypher labels & rel-types can't be
        # parameterized, so each distinct group needs its own UNWIND call)
        # and write in chunks to bound transaction size.
        nodes_by_label: Dict[str, List[Dict[str, Any]]] = {}
        for node in req.nodes:
            node_id = str(node.id or uuid4())
            created_at = (node.created_at or datetime.utcnow()).isoformat()
            updated_at = (node.updated_at or datetime.utcnow()).isoformat()
            nodes_by_label.setdefault(node.label, []).append({
                "id": node_id,
                "name": node.name,
                "description": node.description,
                "source": node.source,
                "metadata": json.dumps(node.metadata),
                "created_at": created_at,
                "updated_at": updated_at,
                "version": version_number,
            })

        rels_by_type: Dict[str, List[Dict[str, Any]]] = {}
        for rel in req.relationships:
            rel_id = str(rel.id or uuid4())
            created_at = (rel.created_at or datetime.utcnow()).isoformat()
            rels_by_type.setdefault(rel.type, []).append({
                "id": rel_id,
                "from_node_id": str(rel.from_node_id),
                "to_node_id": str(rel.to_node_id),
                "evidence": rel.evidence,
                "confidence": rel.confidence,
                "source": rel.source,
                "created_at": created_at,
                "version": version_number,
            })

        nodes_imported = 0
        relationships_imported = 0

        async with neo4j_manager.get_session() as session:
            # 2a. Nodes
            for label, rows in nodes_by_label.items():
                for batch in _chunks(rows, IMPORT_BATCH_SIZE):
                    await session.execute_write(queries.merge_import_nodes_batch, label=label, rows=batch)
                    nodes_imported += len(batch)

            # 2b. Relationships
            for rel_type, rows in rels_by_type.items():
                for batch in _chunks(rows, IMPORT_BATCH_SIZE):
                    merged_ids = await session.execute_write(
                        queries.merge_import_relationships_batch,
                        relationship_type=rel_type,
                        rows=batch
                    )
                    relationships_imported += len(merged_ids)
                    skipped = len(batch) - len(merged_ids)
                    if skipped:
                        skipped_ids = {row["id"] for row in batch} - set(merged_ids)
                        logger.warning(
                            f"Skipped {skipped} {rel_type} relationship(s) with missing from/to node.",
                            extra={"type": rel_type, "skipped_ids": list(skipped_ids)}
                        )

        elapsed = time.time() - start_time
        logger.info(
            f"Bulk JSON import complete for version {version_number}.",
            extra={
                "version_number": version_number,
                "nodes_imported": nodes_imported,
                "relationships_imported": relationships_imported,
                "elapsed_seconds": elapsed
            }
        )
        return ImportResponse(
            version_number=version_number,
            nodes_imported=nodes_imported,
            relationships_imported=relationships_imported,
            elapsed_seconds=round(elapsed, 4),
            status="completed"
        )

    @staticmethod
    async def import_csv(
        nodes_csv_content: Optional[str],
        relationships_csv_content: Optional[str],
        description: Optional[str] = None
    ) -> ImportResponse:
        start_time = time.time()
        
        # 1. Parse CSV strings to lists of Pydantic models
        nodes = []
        if nodes_csv_content:
            nodes = ImportService._parse_csv_nodes(nodes_csv_content)
            
        relationships = []
        if relationships_csv_content:
            relationships = ImportService._parse_csv_relationships(relationships_csv_content)
            
        # 2. delegate to import_json logic
        import_req = ImportJSONRequest(
            nodes=nodes,
            relationships=relationships,
            description=description
        )
        return await ImportService.import_json(import_req)
