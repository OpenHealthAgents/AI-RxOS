import json
from uuid import UUID
from datetime import datetime
from typing import Any, Optional, Dict, List
from neo4j import AsyncTransaction

# Generic `MATCH (n)` scans (list_nodes, search_nodes) match every node in
# the database when no label filter is given, including internal bookkeeping
# nodes (:GraphVersion) and any node that didn't come through the validated
# NodeCreate write path (e.g. manually seeded via Cypher) and therefore
# doesn't actually conform to the NodeResponse schema. Both queries filter
# on this fragment so they only ever return well-formed domain entity nodes.
VALID_DOMAIN_NODE_FILTER = """NOT n:GraphVersion
      AND n.id IS NOT NULL
      AND n.id =~ '(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
      AND n.name IS NOT NULL
      AND n.created_at IS NOT NULL
      AND n.updated_at IS NOT NULL"""

async def create_constraints_and_indexes(tx: AsyncTransaction) -> None:
    labels = [
        "Gene", "Protein", "Disease", "Drug", "Target", "Mutation",
        "Publication", "Patent", "ClinicalTrial", "Company", "Conference",
        "Biomarker"
    ]
    for label in labels:
        constraint_query = f"CREATE CONSTRAINT {label.lower()}_id_unique IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
        await tx.run(constraint_query)
        index_query = f"CREATE INDEX {label.lower()}_name_idx IF NOT EXISTS FOR (n:{label}) ON (n.name)"
        await tx.run(index_query)

async def get_max_active_version(tx: AsyncTransaction) -> int:
    query = 'MATCH (v:GraphVersion {status: "active"}) RETURN max(v.version_number) AS max_v'
    result = await tx.run(query)
    record = await result.single()
    if record and record["max_v"] is not None:
        return record["max_v"]
    return 0

async def create_node(
    tx: AsyncTransaction,
    label: str,
    node_id: str,
    name: str,
    description: Optional[str],
    source: Optional[str],
    metadata_json: str,
    created_at: str,
    updated_at: str,
    version: int
) -> Dict[str, Any]:
    query = f"""
    CREATE (n:{label} {{
        id: $id,
        name: $name,
        description: $description,
        source: $source,
        metadata: $metadata,
        created_at: $created_at,
        updated_at: $updated_at,
        version: $version
    }})
    RETURN n, labels(n)[0] AS label
    """
    result = await tx.run(
        query,
        id=node_id,
        name=name,
        description=description,
        source=source,
        metadata=metadata_json,
        created_at=created_at,
        updated_at=updated_at,
        version=version
    )
    record = await result.single()
    if not record:
        raise RuntimeError("Failed to create node")
    return dict(record["n"].items()) | {"label": record["label"]}

async def get_node(tx: AsyncTransaction, node_id: str, max_version: int) -> Optional[Dict[str, Any]]:
    query = """
    MATCH (n)
    WHERE n.id = $id AND (n.version IS NULL OR n.version <= $max_version)
    RETURN n, labels(n)[0] AS label
    """
    result = await tx.run(query, id=node_id, max_version=max_version)
    record = await result.single()
    if not record:
        return None
    return dict(record["n"].items()) | {"label": record["label"]}

async def update_node(
    tx: AsyncTransaction,
    node_id: str,
    name: Optional[str],
    description: Optional[str],
    source: Optional[str],
    metadata_json: Optional[str],
    updated_at: str,
    max_version: int
) -> Optional[Dict[str, Any]]:
    # Dynamic SET construction to avoid overwriting with nulls if patch updates are partial
    set_clauses = ["n.updated_at = $updated_at"]
    params: Dict[str, Any] = {"id": node_id, "updated_at": updated_at, "max_version": max_version}
    
    if name is not None:
        set_clauses.append("n.name = $name")
        params["name"] = name
    if description is not None:
        set_clauses.append("n.description = $description")
        params["description"] = description
    if source is not None:
        set_clauses.append("n.source = $source")
        params["source"] = source
    if metadata_json is not None:
        set_clauses.append("n.metadata = $metadata")
        params["metadata"] = metadata_json

    set_str = ", ".join(set_clauses)
    query = f"""
    MATCH (n)
    WHERE n.id = $id AND (n.version IS NULL OR n.version <= $max_version)
    SET {set_str}
    RETURN n, labels(n)[0] AS label
    """
    result = await tx.run(query, **params)
    record = await result.single()
    if not record:
        return None
    return dict(record["n"].items()) | {"label": record["label"]}

async def delete_node(tx: AsyncTransaction, node_id: str, max_version: int) -> int:
    query = """
    MATCH (n)
    WHERE n.id = $id AND (n.version IS NULL OR n.version <= $max_version)
    DETACH DELETE n
    RETURN count(n) AS deleted_count
    """
    result = await tx.run(query, id=node_id, max_version=max_version)
    record = await result.single()
    return record["deleted_count"] if record else 0

async def list_nodes(
    tx: AsyncTransaction,
    max_version: int,
    label: Optional[str] = None,
    page: int = 1,
    size: int = 20
) -> tuple[List[Dict[str, Any]], int]:
    skip = (page - 1) * size
    label_clause = f":{label}" if label else ""
    
    query = f"""
    MATCH (n{label_clause})
    WHERE {VALID_DOMAIN_NODE_FILTER}
      AND (n.version IS NULL OR n.version <= $max_version)
    RETURN n, labels(n)[0] AS label
    ORDER BY n.created_at DESC
    SKIP $skip LIMIT $size
    """
    count_query = f"""
    MATCH (n{label_clause})
    WHERE {VALID_DOMAIN_NODE_FILTER}
      AND (n.version IS NULL OR n.version <= $max_version)
    RETURN count(n) AS total
    """

    res = await tx.run(query, max_version=max_version, skip=skip, size=size)
    nodes = []
    async for record in res:
        nodes.append(dict(record["n"].items()) | {"label": record["label"]})
        
    count_res = await tx.run(count_query, max_version=max_version)
    count_record = await count_res.single()
    total = count_record["total"] if count_record else 0
    return nodes, total

async def create_relationship(
    tx: AsyncTransaction,
    from_node_id: str,
    to_node_id: str,
    relationship_type: str,
    rel_id: str,
    evidence: Optional[str],
    confidence: Optional[float],
    source: Optional[str],
    created_at: str,
    version: int,
    max_version: int
) -> Optional[Dict[str, Any]]:
    query = f"""
    MATCH (from) WHERE from.id = $from_node_id AND (from.version IS NULL OR from.version <= $max_version)
    MATCH (to) WHERE to.id = $to_node_id AND (to.version IS NULL OR to.version <= $max_version)
    CREATE (from)-[r:{relationship_type} {{
        id: $id,
        evidence: $evidence,
        confidence: $confidence,
        source: $source,
        created_at: $created_at,
        version: $version
    }}]->(to)
    RETURN r, from.id AS from_id, to.id AS to_id, type(r) AS rel_type
    """
    result = await tx.run(
        query,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        id=rel_id,
        evidence=evidence,
        confidence=confidence,
        source=source,
        created_at=created_at,
        version=version,
        max_version=max_version
    )
    record = await result.single()
    if not record:
        return None
    r_properties = dict(record["r"].items())
    return r_properties | {
        "from_node_id": record["from_id"],
        "to_node_id": record["to_id"],
        "type": record["rel_type"]
    }

async def count_relationships_between(
    tx: AsyncTransaction,
    from_node_id: str,
    to_node_id: str,
    relationship_type: str,
    max_version: int
) -> int:
    query = f"""
    MATCH (from)-[r:{relationship_type}]->(to)
    WHERE from.id = $from_node_id AND to.id = $to_node_id
      AND (r.version IS NULL OR r.version <= $max_version)
    RETURN count(r) AS cnt
    """
    result = await tx.run(
        query,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        max_version=max_version
    )
    record = await result.single()
    return record["cnt"] if record else 0

async def delete_relationship(tx: AsyncTransaction, rel_id: str, max_version: int) -> int:
    query = """
    MATCH ()-[r]->()
    WHERE r.id = $id AND (r.version IS NULL OR r.version <= $max_version)
    DELETE r
    RETURN count(r) AS deleted_count
    """
    result = await tx.run(query, id=rel_id, max_version=max_version)
    record = await result.single()
    return record["deleted_count"] if record else 0

async def list_relationships(
    tx: AsyncTransaction,
    max_version: int,
    rel_type: Optional[str] = None,
    page: int = 1,
    size: int = 20
) -> tuple[List[Dict[str, Any]], int]:
    skip = (page - 1) * size
    type_clause = f":{rel_type}" if rel_type else ""
    
    query = f"""
    MATCH (from)-[r{type_clause}]->(to)
    WHERE (r.version IS NULL OR r.version <= $max_version)
      AND (from.version IS NULL OR from.version <= $max_version)
      AND (to.version IS NULL OR to.version <= $max_version)
    RETURN r, from.id AS from_id, to.id AS to_id, type(r) AS rel_type
    ORDER BY r.created_at DESC
    SKIP $skip LIMIT $size
    """
    count_query = f"""
    MATCH (from)-[r{type_clause}]->(to)
    WHERE (r.version IS NULL OR r.version <= $max_version)
      AND (from.version IS NULL OR from.version <= $max_version)
      AND (to.version IS NULL OR to.version <= $max_version)
    RETURN count(r) AS total
    """
    
    res = await tx.run(query, max_version=max_version, skip=skip, size=size)
    relationships = []
    async for record in res:
        r_properties = dict(record["r"].items())
        relationships.append(r_properties | {
            "from_node_id": record["from_id"],
            "to_node_id": record["to_id"],
            "type": record["rel_type"]
        })
        
    count_res = await tx.run(count_query, max_version=max_version)
    count_record = await count_res.single()
    total = count_record["total"] if count_record else 0
    return relationships, total

async def get_neighbors(tx: AsyncTransaction, node_id: str, max_version: int) -> Optional[Dict[str, Any]]:
    query = """
    MATCH (n)
    WHERE n.id = $node_id AND (n.version IS NULL OR n.version <= $max_version)
    OPTIONAL MATCH (n)-[r]-(m)
    WHERE (r.version IS NULL OR r.version <= $max_version)
      AND (m.version IS NULL OR m.version <= $max_version)
    RETURN n, labels(n)[0] AS label, r, m, labels(m)[0] AS m_label, startNode(r).id AS start_id, endNode(r).id AS end_id, type(r) AS rel_type
    """
    result = await tx.run(query, node_id=node_id, max_version=max_version)
    
    core_node = None
    neighbors_list = []
    
    async for record in result:
        if not core_node:
            node_props = dict(record["n"].items())
            core_node = node_props | {"label": record["label"]}
            
        if record["r"] is not None and record["m"] is not None:
            r_props = dict(record["r"].items())
            relationship = r_props | {
                "from_node_id": record["start_id"],
                "to_node_id": record["end_id"],
                "type": record["rel_type"]
            }
            m_props = dict(record["m"].items())
            neighbor_node = m_props | {"label": record["m_label"]}
            
            neighbors_list.append({
                "relationship": relationship,
                "node": neighbor_node
            })
            
    if not core_node:
        return None
        
    return {
        "node": core_node,
        "neighbors": neighbors_list
    }

async def get_path(
    tx: AsyncTransaction,
    start_node_id: str,
    end_node_id: str,
    max_depth: int,
    max_version: int
) -> Optional[Dict[str, Any]]:
    query = f"""
    MATCH (start) WHERE start.id = $start_id AND (start.version IS NULL OR start.version <= $max_version)
    MATCH (end) WHERE end.id = $end_id AND (end.version IS NULL OR end.version <= $max_version)
    MATCH path = (start)-[*..{max_depth}]-(end)
    WHERE all(x IN nodes(path) WHERE x.version IS NULL OR x.version <= $max_version)
      AND all(y IN relationships(path) WHERE y.version IS NULL OR y.version <= $max_version)
    RETURN path
    ORDER BY length(path)
    LIMIT 1
    """
    result = await tx.run(
        query,
        start_id=start_node_id,
        end_id=end_node_id,
        max_version=max_version
    )
    record = await result.single()
    if not record or not record["path"]:
        return None
        
    path = record["path"]
    nodes = []
    relationships = []
    
    for node in path.nodes:
        # Retrieve primary label
        label = list(node.labels)[0] if node.labels else "Unknown"
        nodes.append(dict(node.items()) | {"label": label})
        
    for rel in path.relationships:
        r_properties = dict(rel.items())
        relationships.append(r_properties | {
            "from_node_id": dict(rel.start_node.items()).get("id"),
            "to_node_id": dict(rel.end_node.items()).get("id"),
            "type": rel.type
        })
        
    return {"nodes": nodes, "relationships": relationships}

async def get_subgraph(
    tx: AsyncTransaction,
    node_ids: List[str],
    relationship_types: Optional[List[str]],
    max_version: int
) -> Dict[str, Any]:
    type_clause = ""
    if relationship_types:
        type_clause = " AND type(r) IN $relationship_types"
        
    query = f"""
    MATCH (n)
    WHERE n.id IN $node_ids AND (n.version IS NULL OR n.version <= $max_version)
    WITH collect(n) AS matched_nodes
    UNWIND matched_nodes AS n
    OPTIONAL MATCH (n)-[r]-(m)
    WHERE m IN matched_nodes 
      AND (r.version IS NULL OR r.version <= $max_version)
      {type_clause}
    RETURN n, labels(n)[0] AS label, r, m, labels(m)[0] AS m_label, startNode(r).id AS start_id, endNode(r).id AS end_id, type(r) AS rel_type
    """
    result = await tx.run(
        query,
        node_ids=node_ids,
        relationship_types=relationship_types,
        max_version=max_version
    )
    
    nodes_map = {}
    relationships_map = {}
    
    async for record in result:
        if record["n"] is not None:
            n_id = record["n"].items().get("id")
            if n_id and n_id not in nodes_map:
                n_props = dict(record["n"].items())
                nodes_map[n_id] = n_props | {"label": record["label"]}
                
        if record["r"] is not None:
            r_id = record["r"].items().get("id")
            if r_id and r_id not in relationships_map:
                r_props = dict(record["r"].items())
                relationships_map[r_id] = r_props | {
                    "from_node_id": record["start_id"],
                    "to_node_id": record["end_id"],
                    "type": record["rel_type"]
                }
                
    return {
        "nodes": list(nodes_map.values()),
        "relationships": list(relationships_map.values())
    }

async def search_nodes(
    tx: AsyncTransaction,
    q: str,
    label: Optional[str],
    max_version: int,
    limit: int = 10
) -> List[Dict[str, Any]]:
    label_clause = f":{label}" if label else ""
    query = f"""
    MATCH (n{label_clause})
    WHERE {VALID_DOMAIN_NODE_FILTER}
      AND (n.version IS NULL OR n.version <= $max_version)
      AND (toLower(n.name) CONTAINS toLower($q) OR toLower(n.description) CONTAINS toLower($q))
    RETURN n, labels(n)[0] AS label
    LIMIT $limit
    """
    result = await tx.run(query, q=q, max_version=max_version, limit=limit)
    nodes = []
    async for record in result:
        nodes.append(dict(record["n"].items()) | {"label": record["label"]})
    return nodes

async def get_next_version_number(tx: AsyncTransaction) -> int:
    query = "MATCH (v:GraphVersion) RETURN max(v.version_number) AS max_v"
    result = await tx.run(query)
    record = await result.single()
    if record and record["max_v"] is not None:
        return record["max_v"] + 1
    return 1

async def create_version(
    tx: AsyncTransaction,
    version_id: str,
    version_number: int,
    description: str,
    created_at: str
) -> Dict[str, Any]:
    query = """
    CREATE (v:GraphVersion {
        id: $id,
        version_number: $version_number,
        description: $description,
        status: "active",
        created_at: $created_at
    })
    RETURN v
    """
    result = await tx.run(
        query,
        id=version_id,
        version_number=version_number,
        description=description,
        created_at=created_at
    )
    record = await result.single()
    if not record:
        raise RuntimeError("Failed to create GraphVersion record")
    return dict(record["v"].items())

async def get_version_by_number(tx: AsyncTransaction, version_number: int) -> Optional[Dict[str, Any]]:
    query = "MATCH (v:GraphVersion {version_number: $version_number}) RETURN v"
    result = await tx.run(query, version_number=version_number)
    record = await result.single()
    if not record:
        return None
    return dict(record["v"].items())

async def rollback_to_version(tx: AsyncTransaction, target_version: int) -> int:
    query = """
    MATCH (v:GraphVersion)
    WHERE v.version_number > $target_version
    SET v.status = "rolled_back"
    RETURN count(v) AS updated_count
    """
    result = await tx.run(query, target_version=target_version)
    record = await result.single()
    updated_count = record["updated_count"] if record else 0

    # The target version itself may have been rolled back by a prior
    # rollback (e.g. rollback to 5, then to 3, then back to 5) — reactivate
    # it so get_max_active_version resolves to it again.
    await tx.run(
        'MATCH (v:GraphVersion {version_number: $target_version}) SET v.status = "active"',
        target_version=target_version
    )

    return updated_count

async def list_versions(tx: AsyncTransaction) -> List[Dict[str, Any]]:
    query = """
    MATCH (v:GraphVersion)
    RETURN v ORDER BY v.version_number DESC
    """
    result = await tx.run(query)
    versions = []
    async for record in result:
        versions.append(dict(record["v"].items()))
    return versions

async def merge_import_nodes_batch(
    tx: AsyncTransaction,
    label: str,
    rows: List[Dict[str, Any]]
) -> None:
    query = f"""
    UNWIND $rows AS row
    MERGE (n:{label} {{id: row.id}})
    ON CREATE SET n.name = row.name,
                  n.description = row.description,
                  n.source = row.source,
                  n.metadata = row.metadata,
                  n.created_at = row.created_at,
                  n.updated_at = row.updated_at,
                  n.version = row.version
    ON MATCH SET n.name = coalesce(row.name, n.name),
                 n.description = coalesce(row.description, n.description),
                 n.source = coalesce(row.source, n.source),
                 n.metadata = coalesce(row.metadata, n.metadata),
                 n.updated_at = row.updated_at
    """
    await tx.run(query, rows=rows)

async def merge_import_relationships_batch(
    tx: AsyncTransaction,
    relationship_type: str,
    rows: List[Dict[str, Any]]
) -> List[str]:
    """Merges a batch of same-type relationships in one UNWIND. Rows whose
    from/to node doesn't exist are silently excluded by the MATCH join;
    returns the ids of rows that were actually merged so the caller can
    report an accurate imported count."""
    query = f"""
    UNWIND $rows AS row
    MATCH (from) WHERE from.id = row.from_node_id
    MATCH (to) WHERE to.id = row.to_node_id
    MERGE (from)-[r:{relationship_type} {{id: row.id}}]->(to)
    ON CREATE SET r.evidence = row.evidence,
                  r.confidence = row.confidence,
                  r.source = row.source,
                  r.created_at = row.created_at,
                  r.version = row.version
    RETURN row.id AS id
    """
    result = await tx.run(query, rows=rows)
    return [record["id"] async for record in result]

