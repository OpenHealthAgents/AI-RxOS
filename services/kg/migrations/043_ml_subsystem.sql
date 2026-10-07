-- ==============================================================================
-- Migration: 043_ml_subsystem.sql
-- Description: Database schema for ML Subsystem
--
-- Components:
--   1. Feature Store (Point-in-time asset features)
--   2. Datasets (Splits & snapshots)
--   3. Model Registry (Artifacts, stages, metrics)
--   4. Prediction Store (Inferences, attributions, delayed actuals)
--   5. Drift Monitoring (Population Stability Index / PSI reports)
-- ==============================================================================

-- 1. Feature Store
CREATE TABLE IF NOT EXISTS ml_feature_store (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id VARCHAR(128) NOT NULL,
    as_of_date DATE NOT NULL DEFAULT CURRENT_DATE,
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ml_features_entity ON ml_feature_store (entity_id);
CREATE INDEX IF NOT EXISTS idx_ml_features_as_of_date ON ml_feature_store (as_of_date);

-- 2. ML Datasets Catalog
CREATE TABLE IF NOT EXISTS ml_datasets (
    dataset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL,
    version VARCHAR(64) NOT NULL,
    feature_names TEXT[] NOT NULL DEFAULT '{}',
    target_name VARCHAR(128) NOT NULL,
    train_count INTEGER NOT NULL DEFAULT 0,
    val_count INTEGER NOT NULL DEFAULT 0,
    test_count INTEGER NOT NULL DEFAULT 0,
    cutoff_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name, version)
);

-- 3. Model Registry
CREATE TABLE IF NOT EXISTS ml_model_registry (
    model_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL,
    version VARCHAR(64) NOT NULL,
    architecture VARCHAR(64) NOT NULL CHECK (
        architecture IN ('logistic_regression', 'random_forest', 'gradient_boosting')
    ),
    stage VARCHAR(32) NOT NULL DEFAULT 'development' CHECK (
        stage IN ('development', 'staging', 'production', 'archived')
    ),
    feature_names TEXT[] NOT NULL DEFAULT '{}',
    hyperparameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    coefficients_or_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
    intercept NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    dataset_version VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name, version)
);

CREATE INDEX IF NOT EXISTS idx_ml_models_stage ON ml_model_registry (stage);
CREATE INDEX IF NOT EXISTS idx_ml_models_architecture ON ml_model_registry (architecture);

-- 4. Prediction Store
CREATE TABLE IF NOT EXISTS ml_prediction_store (
    prediction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id VARCHAR(128) NOT NULL,
    model_id UUID NOT NULL REFERENCES ml_model_registry(model_id) ON DELETE CASCADE,
    model_version VARCHAR(64) NOT NULL,
    architecture VARCHAR(64) NOT NULL,
    predicted_probability NUMERIC(5, 4) NOT NULL CHECK (predicted_probability >= 0.0 AND predicted_probability <= 1.0),
    predicted_class SMALLINT NOT NULL CHECK (predicted_class IN (0, 1)),
    features_used JSONB NOT NULL DEFAULT '{}'::jsonb,
    explanation JSONB,
    actual_outcome NUMERIC(5, 4),
    outcome_observed_date DATE,
    latency_ms NUMERIC(8, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ml_predictions_entity ON ml_prediction_store (entity_id);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_model ON ml_prediction_store (model_id);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_created ON ml_prediction_store (created_at DESC);

-- 5. Drift Monitoring Logs
CREATE TABLE IF NOT EXISTS ml_drift_reports (
    report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version VARCHAR(64) NOT NULL,
    evaluation_window_start DATE NOT NULL,
    evaluation_window_end DATE NOT NULL,
    total_inferences_evaluated INTEGER NOT NULL DEFAULT 0,
    overall_drift_status VARCHAR(32) NOT NULL CHECK (
        overall_drift_status IN ('no_drift', 'moderate_drift', 'severe_drift')
    ),
    feature_drifts JSONB NOT NULL DEFAULT '{}'::jsonb,
    drift_alert_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    recommended_action TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ml_drift_status ON ml_drift_reports (overall_drift_status);
CREATE INDEX IF NOT EXISTS idx_ml_drift_generated ON ml_drift_reports (generated_at DESC);

-- 6. Analytical Views
CREATE OR REPLACE VIEW view_active_ml_champions AS
SELECT
    m.model_id,
    m.name,
    m.version,
    m.architecture,
    m.stage,
    (m.metrics->>'accuracy')::NUMERIC AS accuracy,
    (m.metrics->>'roc_auc')::NUMERIC AS roc_auc,
    (m.metrics->>'f1_score')::NUMERIC AS f1_score,
    (m.metrics->>'brier_score')::NUMERIC AS brier_score,
    m.dataset_version,
    m.registered_at
FROM ml_model_registry m
WHERE m.stage = 'production' AND m.is_active = TRUE;
