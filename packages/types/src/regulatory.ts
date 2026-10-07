import { z } from "zod";

export const RegulatoryJurisdictionSchema = z.enum([
  "US",
  "EU",
  "JP",
  "CN",
  "UK",
  "CA",
  "GLOBAL",
]);
export type RegulatoryJurisdiction = z.infer<typeof RegulatoryJurisdictionSchema>;

export const RegulatoryAgencySchema = z.enum([
  "FDA",
  "EMA",
  "PMDA",
  "NMPA",
  "MHRA",
  "HEALTH_CANADA",
  "WHO",
  "OTHER",
]);
export type RegulatoryAgency = z.infer<typeof RegulatoryAgencySchema>;

export const RegulatoryCategorySchema = z.enum([
  "IND_RELATED",
  "FAST_TRACK",
  "BREAKTHROUGH_THERAPY",
  "ORPHAN_DRUG",
  "ACCELERATED_APPROVAL",
  "FULL_APPROVAL",
  "SUPPLEMENTAL_APPROVAL",
  "COMPLETE_RESPONSE_LETTER",
  "WITHDRAWAL",
  "SAFETY_WARNING",
  "LABEL_CHANGE",
  "REGULATORY_MILESTONE",
]);
export type RegulatoryCategory = z.infer<typeof RegulatoryCategorySchema>;

export const RegulatorySourceTypeSchema = z.enum([
  "FDA_DRUGS_AT_FDA",
  "FDA_ACTION_LETTER",
  "FDA_ORANGE_BOOK",
  "EMA_EPAR",
  "PMDA_NOTICE",
  "NMPA_NOTICE",
  "SEC_8K_FILING",
  "FEDERAL_REGISTER",
  "SPONSOR_REGULATORY_DISCLOSURE",
  "UNVERIFIED_MARKETING_CLAIM",
  "OTHER",
]);
export type RegulatorySourceType = z.infer<typeof RegulatorySourceTypeSchema>;

export const VerificationStatusSchema = z.enum([
  "VERIFIED_OFFICIAL_RECORD",
  "PROVISIONAL_PENDING_CONFIRMATION",
  "REJECTED_UNVERIFIED_MARKETING",
]);
export type VerificationStatus = z.infer<typeof VerificationStatusSchema>;

export const RegulatorySourceSchema = z.object({
  source_type: RegulatorySourceTypeSchema,
  source_citation: z.string(),
  source_url: z.string().nullable().optional(),
  source_document_id: z.string().nullable().optional(),
  is_verified_evidence: z.boolean().default(false),
  publication_date: z.string().nullable().optional(),
});
export type RegulatorySource = z.infer<typeof RegulatorySourceSchema>;

export const RegulatoryAssetRefSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
});
export type RegulatoryAssetRef = z.infer<typeof RegulatoryAssetRefSchema>;

export const RegulatoryIndicationRefSchema = z.object({
  indication_id: z.string().uuid().nullable().optional(),
  indication_name: z.string(),
  cancer_subtype: z.string().nullable().optional(),
});
export type RegulatoryIndicationRef = z.infer<typeof RegulatoryIndicationRefSchema>;

export const RegulatoryEventPayloadSchema = z.object({
  event_type: RegulatoryCategorySchema,
  headline: z.string(),
  details: z.string(),
  milestone_type: z.string().nullable().optional(),
  dossier_data: z.record(z.string(), z.unknown()).default({}),
});
export type RegulatoryEventPayload = z.infer<typeof RegulatoryEventPayloadSchema>;

export const RegulatoryEventRecordSchema = z.object({
  id: z.string().uuid(),
  source: RegulatorySourceSchema,
  event_date: z.string(),
  jurisdiction: RegulatoryJurisdictionSchema,
  authority: RegulatoryAgencySchema.default("FDA"),
  asset: RegulatoryAssetRefSchema,
  indication: RegulatoryIndicationRefSchema,
  event: RegulatoryEventPayloadSchema,
  confidence: z.number().min(0).max(1),
  verification_status: VerificationStatusSchema.default("VERIFIED_OFFICIAL_RECORD"),
  policy_violation: z.string().nullable().optional(),
  content_hash: z.string().default(""),
  created_at: z.string().datetime().optional(),
});
export type RegulatoryEventRecord = z.infer<typeof RegulatoryEventRecordSchema>;

export const AssetRegulatoryStatusSummarySchema = z.object({
  asset_id: z.string().uuid(),
  cutoff_date: z.string(),
  overall_standing: z.string(),
  is_approved: z.boolean(),
  has_accelerated_approval: z.boolean(),
  has_full_approval: z.boolean(),
  has_supplemental_approval: z.boolean(),
  has_breakthrough_therapy: z.boolean(),
  has_fast_track: z.boolean(),
  has_orphan_drug: z.boolean(),
  has_crl: z.boolean(),
  has_withdrawal: z.boolean(),
  safety_warnings_count: z.number().int(),
  label_changes_count: z.number().int(),
  total_verifiable_events: z.number().int(),
});
export type AssetRegulatoryStatusSummary = z.infer<typeof AssetRegulatoryStatusSummarySchema>;

export const BatchRegulatoryIngestRequestSchema = z.object({
  events: z.array(RegulatoryEventRecordSchema),
  strict: z.boolean().default(false),
});
export type BatchRegulatoryIngestRequest = z.infer<typeof BatchRegulatoryIngestRequestSchema>;

export const BatchRegulatoryIngestResponseSchema = z.object({
  total_submitted: z.number().int(),
  total_ingested: z.number().int(),
  events: z.array(RegulatoryEventRecordSchema),
});
export type BatchRegulatoryIngestResponse = z.infer<typeof BatchRegulatoryIngestResponseSchema>;

