CREATE TABLE IF NOT EXISTS canonical.human_scientific_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL,
    reviewer_id UUID NOT NULL,
    reviewed_object_type TEXT NOT NULL CHECK (length(trim(reviewed_object_type)) BETWEEN 1 AND 120),
    reviewed_object_id TEXT NOT NULL CHECK (length(trim(reviewed_object_id)) BETWEEN 1 AND 500),
    idempotency_key TEXT NOT NULL CHECK (length(trim(idempotency_key)) BETWEEN 1 AND 200),
    review_action TEXT NOT NULL CHECK (
        review_action IN (
            'approve_evidence', 'reject_evidence', 'correct_entity',
            'correct_classification', 'add_evidence', 'change_evidence_quality',
            'review_prediction', 'override_recommendation'
        )
    ),
    review_status TEXT NOT NULL CHECK (
        review_status IN ('pending', 'approved', 'rejected', 'corrected', 'overridden', 'active', 'invalid')
    ),
    rationale TEXT NOT NULL CHECK (length(trim(rationale)) BETWEEN 1 AND 10000),
    original_ai_value JSONB,
    human_decision JSONB,
    original_value JSONB,
    corrected_value JSONB,
    model_version TEXT,
    evidence_version TEXT,
    decision_version TEXT,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    previous_review_id UUID,
    review_hash TEXT NOT NULL CHECK (review_hash ~ '^[a-f0-9]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
    UNIQUE (organization_id, idempotency_key),
    UNIQUE (id, organization_id),
    FOREIGN KEY (previous_review_id, organization_id)
        REFERENCES canonical.human_scientific_reviews(id, organization_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS human_scientific_reviews_tenant_history_idx
    ON canonical.human_scientific_reviews (organization_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS human_scientific_reviews_object_history_idx
    ON canonical.human_scientific_reviews (organization_id, reviewed_object_type, reviewed_object_id, created_at DESC);

CREATE TABLE IF NOT EXISTS canonical.human_scientific_review_audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL,
    review_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    action TEXT NOT NULL CHECK (action = 'human_review_recorded'),
    review_hash TEXT NOT NULL CHECK (review_hash ~ '^[a-f0-9]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
    FOREIGN KEY (review_id, organization_id)
        REFERENCES canonical.human_scientific_reviews(id, organization_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS human_scientific_review_audit_history_idx
    ON canonical.human_scientific_review_audit_events (organization_id, created_at DESC, id DESC);

CREATE OR REPLACE FUNCTION canonical.reject_human_review_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'human scientific reviews and audit events are append-only';
END;
$$;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'human_scientific_reviews', 'human_scientific_review_audit_events'
    ] LOOP
        EXECUTE format('ALTER TABLE canonical.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE canonical.%I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS %I ON canonical.%I', table_name || '_scope', table_name);
        EXECUTE format(
            'CREATE POLICY %I ON canonical.%I FOR ALL USING '
            || '(organization_id = canonical.current_organization_id()) '
            || 'WITH CHECK (organization_id = canonical.current_organization_id())',
            table_name || '_scope', table_name
        );
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON canonical.%I', table_name || '_append_only', table_name);
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON canonical.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION canonical.reject_human_review_mutation()',
            table_name || '_append_only', table_name
        );
    END LOOP;
END $$;
