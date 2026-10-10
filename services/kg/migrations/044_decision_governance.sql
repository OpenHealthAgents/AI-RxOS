CREATE TABLE IF NOT EXISTS canonical.decision_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.entities(id) ON DELETE RESTRICT,
    organization_id UUID NOT NULL,
    user_id UUID NOT NULL,
    idempotency_key TEXT NOT NULL CHECK (length(trim(idempotency_key)) BETWEEN 1 AND 200),
    action TEXT NOT NULL CHECK (action IN (
        'PURSUE', 'INVESTIGATE', 'PARTNER', 'LICENSE', 'MONITOR', 'AVOID',
        'INSUFFICIENT_EVIDENCE'
    )),
    score DOUBLE PRECISION NOT NULL CHECK (score BETWEEN 0 AND 100),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evaluation_cutoff TIMESTAMPTZ NOT NULL,
    policy_name TEXT NOT NULL CHECK (length(trim(policy_name)) > 0),
    policy_version TEXT NOT NULL CHECK (length(trim(policy_version)) > 0),
    prompt_version TEXT CHECK (length(trim(prompt_version)) > 0),
    model_versions JSONB NOT NULL DEFAULT '{}'::jsonb,
    feature_versions JSONB NOT NULL DEFAULT '{}'::jsonb,
    signal_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    explanation JSONB NOT NULL DEFAULT '{}'::jsonb,
    snapshot_hash TEXT NOT NULL CHECK (snapshot_hash ~ '^[a-f0-9]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
    UNIQUE (organization_id, idempotency_key),
    UNIQUE (id, organization_id)
);
CREATE INDEX IF NOT EXISTS decision_snapshots_asset_history_idx
    ON canonical.decision_snapshots (organization_id, asset_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS decision_snapshots_cutoff_idx
    ON canonical.decision_snapshots (organization_id, evaluation_cutoff, id);

CREATE TABLE IF NOT EXISTS canonical.decision_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_snapshot_id UUID NOT NULL,
    organization_id UUID NOT NULL,
    reviewer_id UUID NOT NULL,
    idempotency_key TEXT NOT NULL CHECK (length(trim(idempotency_key)) BETWEEN 1 AND 200),
    review_action TEXT NOT NULL CHECK (review_action IN ('approve', 'reject', 'correct', 'override')),
    review_status TEXT NOT NULL CHECK (review_status IN ('approved', 'rejected', 'corrected', 'overridden')),
    rationale TEXT NOT NULL CHECK (length(trim(rationale)) BETWEEN 1 AND 10000),
    original_ai_value JSONB NOT NULL,
    human_decision JSONB NOT NULL,
    model_version TEXT,
    evidence_version TEXT,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_hash TEXT NOT NULL CHECK (review_hash ~ '^[a-f0-9]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
    UNIQUE (organization_id, idempotency_key),
    UNIQUE (id, organization_id),
    FOREIGN KEY (decision_snapshot_id, organization_id)
        REFERENCES canonical.decision_snapshots(id, organization_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS decision_reviews_snapshot_history_idx
    ON canonical.decision_reviews (organization_id, decision_snapshot_id, created_at, id);

CREATE TABLE IF NOT EXISTS canonical.decision_governance_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL,
    asset_id UUID NOT NULL REFERENCES canonical.entities(id) ON DELETE RESTRICT,
    decision_snapshot_id UUID,
    decision_review_id UUID,
    actor_id UUID NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('decision_snapshotted', 'decision_reviewed')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
    CHECK (
        (event_type = 'decision_snapshotted' AND decision_snapshot_id IS NOT NULL AND decision_review_id IS NULL)
        OR (event_type = 'decision_reviewed' AND decision_snapshot_id IS NOT NULL AND decision_review_id IS NOT NULL)
    ),
    FOREIGN KEY (decision_snapshot_id, organization_id)
        REFERENCES canonical.decision_snapshots(id, organization_id) ON DELETE RESTRICT,
    FOREIGN KEY (decision_review_id, organization_id)
        REFERENCES canonical.decision_reviews(id, organization_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS decision_governance_events_history_idx
    ON canonical.decision_governance_events (organization_id, asset_id, created_at DESC, id DESC);

CREATE OR REPLACE FUNCTION canonical.reject_decision_governance_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'canonical decision snapshots, reviews, and governance events are append-only';
END;
$$;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'decision_snapshots', 'decision_reviews', 'decision_governance_events'
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
            || 'FOR EACH ROW EXECUTE FUNCTION canonical.reject_decision_governance_mutation()',
            table_name || '_append_only', table_name
        );
    END LOOP;
END $$;
