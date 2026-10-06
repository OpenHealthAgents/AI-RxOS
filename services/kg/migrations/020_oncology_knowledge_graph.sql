-- ==============================================================================
-- Migration: 020_oncology_knowledge_graph.sql
-- Description: Production Oncology Knowledge Graph Schema
-- Represents Asset relationships to:
-- targets, genes, mutations, pathways, diseases, indications, biomarkers,
-- patient populations, trials, publications, companies, institutions,
-- competitors, resistance mechanisms, combinations, patents, licenses,
-- regulatory events.
-- Implements complete graph lineage back to evidence.
-- ==============================================================================

-- 1. Knowledge Graph Nodes
CREATE TABLE IF NOT EXISTS kg_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_type VARCHAR(64) NOT NULL CHECK (
        node_type IN (
            'ASSET',
            'TARGET',
            'GENE',
            'MUTATION',
            'PATHWAY',
            'DISEASE',
            'INDICATION',
            'BIOMARKER',
            'PATIENT_POPULATION',
            'TRIAL',
            'PUBLICATION',
            'COMPANY',
            'INSTITUTION',
            'COMPETITOR',
            'RESISTANCE_MECHANISM',
            'COMBINATION',
            'PATENT',
            'LICENSE',
            'REGULATORY_EVENT'
        )
    ),
    external_id VARCHAR(128) NOT NULL,
    name VARCHAR(255) NOT NULL,
    display_label VARCHAR(255) NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (node_type, external_id)
);

CREATE INDEX IF NOT EXISTS idx_kg_nodes_type ON kg_nodes (node_type);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_name ON kg_nodes (name);

-- 2. Knowledge Graph Directed Edges
CREATE TABLE IF NOT EXISTS kg_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_node_id UUID NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
    relationship_type VARCHAR(64) NOT NULL CHECK (
        relationship_type IN (
            'TARGETS',
            'INVOLVES_GENE',
            'HARBORS_MUTATION',
            'MODULATES_PATHWAY',
            'TREATS_DISEASE',
            'INDICATED_FOR',
            'STRATIFIED_BY_BIOMARKER',
            'ENROLLS_POPULATION',
            'EVALUATED_IN_TRIAL',
            'REPORTED_IN_PUB',
            'DEVELOPED_BY_COMPANY',
            'ORIGINATED_AT_INSTITUTION',
            'COMPETES_WITH',
            'ACQUIRES_RESISTANCE',
            'OVERCOMES_RESISTANCE_VIA',
            'COVERED_BY_PATENT',
            'SUBJECT_TO_LICENSE',
            'GOVERNED_BY_REGULATORY_EVENT'
        )
    ),
    target_node_id UUID NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 1.000 CHECK (confidence >= 0.000 AND confidence <= 1.000),
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_node_id, relationship_type, target_node_id)
);

CREATE INDEX IF NOT EXISTS idx_kg_edges_source ON kg_edges (source_node_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_target ON kg_edges (target_node_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_rel ON kg_edges (relationship_type);

-- 3. Edge Evidence Lineage
CREATE TABLE IF NOT EXISTS kg_edge_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    edge_id UUID NOT NULL REFERENCES kg_edges(id) ON DELETE CASCADE,
    evidence_type VARCHAR(64) NOT NULL CHECK (
        evidence_type IN (
            'LITERATURE',
            'CLINICAL_TRIAL',
            'REGULATORY_RECORD',
            'PATENT',
            'COMPANY_SEC_FILING',
            'CONFERENCE_ABSTRACT'
        )
    ),
    source_citation TEXT NOT NULL,
    source_url TEXT,
    source_document_id VARCHAR(128),
    polarity VARCHAR(32) NOT NULL DEFAULT 'SUPPORTING' CHECK (polarity IN ('SUPPORTING', 'CONTRADICTING', 'NEUTRAL')),
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 1.000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kg_evidence_edge ON kg_edge_evidence (edge_id);
CREATE INDEX IF NOT EXISTS idx_kg_evidence_type ON kg_edge_evidence (evidence_type);
