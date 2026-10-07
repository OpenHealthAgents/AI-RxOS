import { z } from "zod";

/**
 * Machine Learning Subsystem Domain Contracts.
 * 
 * Provides types and Zod schemas for:
 * - Dataset Builder & Feature Store
 * - Interpretable Baseline Models (Logistic Regression, Random Forest, Gradient Boosting)
 * - Model Registry & Evaluation Metrics
 * - Model Serving & Explainability
 * - Prediction Store & Outcome Audits
 * - Monitoring & Population Stability Index (PSI) Drift Detection
 */

export const ModelArchitectureSchema = z.enum([
  "logistic_regression",
  "random_forest",
  "gradient_boosting",
]);
export type ModelArchitecture = z.infer<typeof ModelArchitectureSchema>;

export const ModelStageSchema = z.enum([
  "development",
  "staging",
  "production",
  "archived",
]);
export type ModelStage = z.infer<typeof ModelStageSchema>;

export const FeatureDataTypeSchema = z.enum([
  "float",
  "integer",
  "boolean",
  "categorical",
]);
export type FeatureDataType = z.infer<typeof FeatureDataTypeSchema>;

export const DriftStatusSchema = z.enum([
  "no_drift",
  "moderate_drift",
  "severe_drift",
]);
export type DriftStatus = z.infer<typeof DriftStatusSchema>;

export const FeatureDefinitionSchema = z.object({
  name: z.string(),
  feature_group: z.string(),
  data_type: FeatureDataTypeSchema,
  description: z.string(),
  default_value: z.number().default(0.0),
  min_value: z.number().optional().nullable(),
  max_value: z.number().optional().nullable(),
  version: z.string().default("v1"),
});
export type FeatureDefinition = z.infer<typeof FeatureDefinitionSchema>;

export const FeatureVectorSchema = z.object({
  entity_id: z.string(),
  as_of_date: z.string(),
  features: z.record(z.string(), z.number()),
  created_at: z.string().datetime().optional(),
});
export type FeatureVector = z.infer<typeof FeatureVectorSchema>;

export const TargetLabelSchema = z.object({
  entity_id: z.string(),
  target_name: z.string(),
  outcome_value: z.number(),
  observation_horizon_date: z.string(),
  is_known_at_cutoff: z.boolean().default(true),
  outcome_evidence_id: z.string().optional().nullable(),
  created_at: z.string().datetime().optional(),
});
export type TargetLabel = z.infer<typeof TargetLabelSchema>;

export const DatasetRecordSchema = z.object({
  entity_id: z.string(),
  as_of_date: z.string(),
  features: z.record(z.string(), z.number()),
  label: z.number(),
  metadata: z.record(z.string(), z.unknown()).default({}),
});
export type DatasetRecord = z.infer<typeof DatasetRecordSchema>;

export const MLDatasetSchema = z.object({
  dataset_id: z.string().uuid(),
  name: z.string(),
  version: z.string(),
  feature_names: z.array(z.string()),
  target_name: z.string(),
  train_records: z.array(DatasetRecordSchema),
  val_records: z.array(DatasetRecordSchema),
  test_records: z.array(DatasetRecordSchema),
  cutoff_date: z.string().optional().nullable(),
  created_at: z.string().datetime().optional(),
});
export type MLDataset = z.infer<typeof MLDatasetSchema>;

export const ModelEvaluationMetricsSchema = z.object({
  accuracy: z.number().min(0.0).max(1.0),
  precision: z.number().min(0.0).max(1.0),
  recall: z.number().min(0.0).max(1.0),
  f1_score: z.number().min(0.0).max(1.0),
  roc_auc: z.number().min(0.0).max(1.0),
  brier_score: z.number().min(0.0).max(1.0),
  log_loss: z.number().nonnegative(),
});
export type ModelEvaluationMetrics = z.infer<typeof ModelEvaluationMetricsSchema>;

export const ModelArtifactSchema = z.object({
  model_id: z.string().uuid(),
  name: z.string(),
  version: z.string(),
  architecture: ModelArchitectureSchema,
  stage: ModelStageSchema,
  feature_names: z.array(z.string()),
  hyperparameters: z.record(z.string(), z.unknown()).default({}),
  coefficients_or_weights: z.record(z.string(), z.unknown()).default({}),
  intercept: z.number().default(0.0),
  metrics: ModelEvaluationMetricsSchema,
  dataset_version: z.string(),
  registered_at: z.string().datetime().optional(),
  is_active: z.boolean().default(true),
});
export type ModelArtifact = z.infer<typeof ModelArtifactSchema>;

export const FeatureAttributionSchema = z.object({
  feature_name: z.string(),
  feature_value: z.number(),
  importance_weight: z.number(),
  attribution_score: z.number(),
  directional_impact: z.enum(["POSITIVE", "NEGATIVE", "NEUTRAL"]),
  explanation: z.string(),
});
export type FeatureAttribution = z.infer<typeof FeatureAttributionSchema>;

export const PredictionExplanationSchema = z.object({
  prediction_id: z.string().uuid(),
  entity_id: z.string(),
  model_version: z.string(),
  predicted_probability: z.number(),
  base_value: z.number(),
  top_drivers: z.array(FeatureAttributionSchema),
  summary_narrative: z.string(),
});
export type PredictionExplanation = z.infer<typeof PredictionExplanationSchema>;

export const InferenceRequestSchema = z.object({
  entity_id: z.string(),
  features: z.record(z.string(), z.number()).optional().nullable(),
  model_version: z.string().optional().nullable(),
});
export type InferenceRequest = z.infer<typeof InferenceRequestSchema>;

export const StoredPredictionSchema = z.object({
  prediction_id: z.string().uuid(),
  entity_id: z.string(),
  model_id: z.string().uuid(),
  model_version: z.string(),
  architecture: ModelArchitectureSchema,
  predicted_probability: z.number(),
  predicted_class: z.number().int(),
  features_used: z.record(z.string(), z.number()),
  explanation: PredictionExplanationSchema.optional().nullable(),
  actual_outcome: z.number().optional().nullable(),
  outcome_observed_date: z.string().optional().nullable(),
  latency_ms: z.number(),
  created_at: z.string().datetime().optional(),
});
export type StoredPrediction = z.infer<typeof StoredPredictionSchema>;

export const FeatureDriftMetricSchema = z.object({
  feature_name: z.string(),
  baseline_mean: z.number(),
  current_mean: z.number(),
  psi: z.number(),
  drift_status: DriftStatusSchema,
  flagged: z.boolean(),
});
export type FeatureDriftMetric = z.infer<typeof FeatureDriftMetricSchema>;

export const DriftReportSchema = z.object({
  report_id: z.string().uuid(),
  model_version: z.string(),
  evaluation_window_start: z.string(),
  evaluation_window_end: z.string(),
  total_inferences_evaluated: z.number().int(),
  overall_drift_status: DriftStatusSchema,
  feature_drifts: z.record(z.string(), FeatureDriftMetricSchema),
  drift_alert_triggered: z.boolean(),
  recommended_action: z.string(),
  generated_at: z.string().datetime().optional(),
});
export type DriftReport = z.infer<typeof DriftReportSchema>;
