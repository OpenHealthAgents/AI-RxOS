-- ==============================================================================
-- Migration: 031_immutable_provenance.sql
-- Description: Cryptographic Immutable Provenance Architecture
-- Tracks all 7 stages:
-- 1. source
-- 2. extraction
-- 3. normalization
-- 4. feature derivation
-- 5. model input
-- 6. model output
-- 7. decision input
-- Guarantees complete unbroken traceback from recommendations back to underlying sources.
-- Computes and verifies Merkle DAG root hashes and content hashes (SHA-256).
-- ==============================================================================

-- 1. Normalization Records (Stage 3)
CREATE TABLE IF NOT EXISTS provenance_normalizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES evidence_extractions(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL,
    raw_value TEXT NOT NULL,
    normalized_value NUMERIC(14, 4) NOT NULL,
    normalized_unit VARCHAR(64) NOT NULL,
    parameter_name VARCHAR(128) NOT NULL,
    normalizer_version VARCHAR(32) NOT NULL DEFAULT 'v1.0',
    transformation_rule TEXT NOT NULL,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.950 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    content_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prov_norm_extraction ON provenance_normalizations (extraction_id);
CREATE INDEX IF NOT EXISTS idx_prov_norm_asset ON provenance_normalizations (asset_id);
CREATE INDEX IF NOT EXISTS idx_prov_norm_hash ON provenance_normalizations (content_hash);

-- 2. Model Input Records (Stage 5)
CREATE TABLE IF NOT EXISTS provenance_model_inputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name VARCHAR(128) NOT NULL,
    model_version VARCHAR(32) NOT NULL DEFAULT 'v0.1',
    asset_id UUID NOT NULL,
    feature_ids UUID[] NOT NULL DEFAULT '{}',
    feature_vector JSONB NOT NULL DEFAULT '{}'::jsonb,
    input_schema_version VARCHAR(32) NOT NULL DEFAULT 'v1.0',
    content_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prov_mi_asset ON provenance_model_inputs (asset_id);
CREATE INDEX IF NOT EXISTS idx_prov_mi_hash ON provenance_model_inputs (content_hash);

-- 3. Decision Input Records (Stage 7)
CREATE TABLE IF NOT EXISTS provenance_decision_inputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_id UUID NOT NULL,
    asset_id UUID NOT NULL,
    action VARCHAR(32) NOT NULL,
    model_output_ids UUID[] NOT NULL DEFAULT '{}',
    model_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    decision_policy_version VARCHAR(32) NOT NULL DEFAULT 'v1.0',
    thresholds_applied JSONB NOT NULL DEFAULT '{}'::jsonb,
    content_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prov_di_rec ON provenance_decision_inputs (recommendation_id);
CREATE INDEX IF NOT EXISTS idx_prov_di_asset ON provenance_decision_inputs (asset_id);
CREATE INDEX IF NOT EXISTS idx_prov_di_hash ON provenance_decision_inputs (content_hash);

-- 4. Canonical Immutable Provenance Nodes
CREATE TABLE IF NOT EXISTS provenance_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    stage VARCHAR(32) NOT NULL CHECK (
        stage IN (
            'source',
            'extraction',
            'normalization',
            'feature_derivation',
            'model_input',
            'model_output',
            'decision_input'
        )
    ),
    node_type VARCHAR(32) NOT NULL CHECK (
        node_type IN (
            'source',
            'extraction',
            'normalization',
            'feature_derivation',
            'model_input',
            'model_output',
            'decision_input',
            'recommendation'
        )
    ),
    entity_id UUID NOT NULL,
    label VARCHAR(255) NOT NULL,
    description TEXT DEFAULT '',
    payload_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    content_hash VARCHAR(64) NOT NULL,
    parent_hashes VARCHAR(64)[] DEFAULT '{}',
    parent_node_ids UUID[] DEFAULT '{}',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_prov_nodes_asset ON provenance_nodes (asset_id);
CREATE INDEX IF NOT EXISTS idx_prov_nodes_stage ON provenance_nodes (stage);
CREATE INDEX IF NOT EXISTS idx_prov_nodes_entity ON provenance_nodes (entity_id);
CREATE INDEX IF NOT EXISTS idx_prov_nodes_hash ON provenance_nodes (content_hash);

-- 5. Canonical Immutable Provenance Directed Edges
CREATE TABLE IF NOT EXISTS provenance_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_node_id UUID NOT NULL REFERENCES provenance_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES provenance_nodes(id) ON DELETE CASCADE,
    source_stage VARCHAR(32) NOT NULL,
    target_stage VARCHAR(32) NOT NULL,
    edge_type VARCHAR(32) NOT NULL CHECK (
        edge_type IN (
            'extracted_from',
            'normalized_from',
            'derived_from',
            'fed_into_model',
            'predicted_by',
            'decided_from',
            'supports',
            'contradicts'
        )
    ),
    weight NUMERIC(5, 4) NOT NULL DEFAULT 1.0000,
    hash_signature VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prov_edges_source ON provenance_edges (source_node_id);
CREATE INDEX IF NOT EXISTS idx_prov_edges_target ON provenance_edges (target_node_id);
CREATE INDEX IF NOT EXISTS idx_prov_edges_type ON provenance_edges (edge_type);

-- 6. Sealed Merkle Audit Snapshots
CREATE TABLE IF NOT EXISTS provenance_merkle_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_id UUID NOT NULL UNIQUE,
    asset_id UUID NOT NULL,
    action VARCHAR(32) NOT NULL,
    merkle_root_hash VARCHAR(64) NOT NULL,
    node_count INTEGER NOT NULL,
    edge_count INTEGER NOT NULL,
    root_source_ids UUID[] NOT NULL DEFAULT '{}',
    unbroken_chain BOOLEAN NOT NULL DEFAULT TRUE,
    is_audit_passed BOOLEAN NOT NULL DEFAULT TRUE,
    sealed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prov_merkle_rec ON provenance_merkle_audits (recommendation_id);
CREATE INDEX IF NOT EXISTS idx_prov_merkle_asset ON provenance_merkle_audits (asset_id);
CREATE INDEX IF NOT EXISTS idx_prov_merkle_hash ON provenance_merkle_audits (merkle_root_hash);
