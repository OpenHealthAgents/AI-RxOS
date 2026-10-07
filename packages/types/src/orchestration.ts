import { z } from "zod";

export const PipelineStatusSchema = z.enum(["IDLE", "RUNNING", "PAUSED", "ERROR"]);
export type PipelineStatus = z.infer<typeof PipelineStatusSchema>;

export const IngestionRunStatusSchema = z.enum([
  "QUEUED",
  "RUNNING",
  "COMPLETED",
  "PARTIAL_SUCCESS",
  "FAILED",
]);
export type IngestionRunStatus = z.infer<typeof IngestionRunStatusSchema>;

export const DeadLetterStatusSchema = z.enum([
  "PENDING",
  "REPLAYED",
  "RESOLVED",
  "DISCARDED",
]);
export type DeadLetterStatus = z.infer<typeof DeadLetterStatusSchema>;

export const QualityValidationStatusSchema = z.enum(["PASSED", "WARNING", "FAILED"]);
export type QualityValidationStatus = z.infer<typeof QualityValidationStatusSchema>;

export const RetryPolicySchema = z.object({
  max_retries: z.number().int().min(0).max(10).default(3),
  initial_backoff_seconds: z.number().min(0.01).default(0.5),
  backoff_multiplier: z.number().min(1.0).default(2.0),
  max_backoff_seconds: z.number().min(1.0).default(30.0),
  jitter: z.boolean().default(true),
});
export type RetryPolicy = z.infer<typeof RetryPolicySchema>;

export const PipelineScheduleSchema = z.object({
  cron_expression: z.string().nullable().optional(),
  interval_seconds: z.number().int().positive().nullable().optional(),
  is_enabled: z.boolean().default(true),
  next_run_at: z.string().datetime().nullable().optional(),
});
export type PipelineSchedule = z.infer<typeof PipelineScheduleSchema>;

export const WatermarkSchema = z.object({
  pipeline_id: z.string(),
  last_processed_timestamp: z.string().datetime().nullable().optional(),
  last_processed_id: z.string().nullable().optional(),
  high_watermark_value: z.string().nullable().optional(),
  updated_at: z.string().datetime().optional(),
});
export type Watermark = z.infer<typeof WatermarkSchema>;

export const IngestionItemSchema = z.object({
  item_id: z.string(),
  source: z.string(),
  payload: z.record(z.any()),
  timestamp: z.string().datetime().nullable().optional(),
  version_or_hash: z.string().nullable().optional(),
});
export type IngestionItem = z.infer<typeof IngestionItemSchema>;

export const IngestionTelemetrySchema = z.object({
  items_fetched: z.number().int().default(0),
  items_processed: z.number().int().default(0),
  items_succeeded: z.number().int().default(0),
  items_failed: z.number().int().default(0),
  items_retried: z.number().int().default(0),
  items_deduplicated: z.number().int().default(0),
  items_dead_lettered: z.number().int().default(0),
  duration_seconds: z.number().default(0.0),
  error_summary: z.record(z.number().int()).default({}),
});
export type IngestionTelemetry = z.infer<typeof IngestionTelemetrySchema>;

export const DeadLetterRecordSchema = z.object({
  id: z.string().uuid(),
  pipeline_id: z.string(),
  item_id: z.string(),
  source: z.string(),
  payload: z.record(z.any()),
  failure_reason: z.string(),
  failure_category: z.string(),
  stack_trace: z.string().nullable().optional(),
  retry_attempts: z.number().int().default(0),
  status: DeadLetterStatusSchema.default("PENDING"),
  created_at: z.string().datetime().optional(),
  resolved_at: z.string().datetime().nullable().optional(),
  resolution_note: z.string().nullable().optional(),
});
export type DeadLetterRecord = z.infer<typeof DeadLetterRecordSchema>;

export const IngestionRunRecordSchema = z.object({
  id: z.string().uuid(),
  pipeline_id: z.string(),
  triggered_by: z.string().default("MANUAL"),
  status: IngestionRunStatusSchema.default("QUEUED"),
  started_at: z.string().datetime().optional(),
  completed_at: z.string().datetime().nullable().optional(),
  watermark_start: z.string().datetime().nullable().optional(),
  watermark_end: z.string().datetime().nullable().optional(),
  telemetry: IngestionTelemetrySchema.default({}),
  error_message: z.string().nullable().optional(),
  quality_reports: z.array(z.record(z.any())).default([]),
});
export type IngestionRunRecord = z.infer<typeof IngestionRunRecordSchema>;

export const IngestionPipelineSchema = z.object({
  id: z.string(),
  name: z.string(),
  source_name: z.string(),
  schedule: PipelineScheduleSchema.default({}),
  retry_policy: RetryPolicySchema.default({}),
  watermark: WatermarkSchema,
  status: PipelineStatusSchema.default("IDLE"),
  concurrency_limit: z.number().int().default(5),
  quality_gate_strict: z.boolean().default(true),
  created_at: z.string().datetime().optional(),
  updated_at: z.string().datetime().optional(),
});
export type IngestionPipeline = z.infer<typeof IngestionPipelineSchema>;
