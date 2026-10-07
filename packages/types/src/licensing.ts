import { z } from "zod";

export const MANDATORY_FTO_DISCLAIMER =
  "DISCLAIMER: IP analysis provided is competitive and scientific decision intelligence, " +
  "not legal advice. No Freedom to Operate (FTO) is claimed or warranted. " +
  "Consult qualified patent counsel for formal legal opinions.";

export const LicensingStatusSchema = z.enum([
  "VERIFIED_AVAILABLE",
  "POTENTIALLY_AVAILABLE",
  "PARTNERED",
  "OWNERSHIP_UNCLEAR",
  "NO_PUBLIC_SIGNAL",
  "NO_PUBLIC_LICENSING_SIGNAL",
  "UNKNOWN",
]);
export type LicensingStatus = z.infer<typeof LicensingStatusSchema>;

import { DealTypeSchema, DealType } from "./canonical_domain";
export { DealTypeSchema, type DealType };

export const PatentJurisdictionSchema = z.enum([
  "US",
  "EP",
  "WO",
  "JP",
  "CN",
  "CA",
  "OTHER",
]);
export type PatentJurisdiction = z.infer<typeof PatentJurisdictionSchema>;

export const PatentClaimTypeSchema = z.enum([
  "COMPOSITION_OF_MATTER",
  "THERAPEUTIC_USE",
  "FORMULATION",
  "COMBINATION",
  "BIOMARKER_CLAIMS",
]);
export type PatentClaimType = z.infer<typeof PatentClaimTypeSchema>;

export const PatentStatusSchema = z.enum([
  "GRANTED",
  "PENDING",
  "EXPIRED",
  "ABANDONED",
  "REVOKED",
]);
export type PatentStatus = z.infer<typeof PatentStatusSchema>;

export const PatentFamilySchema = z.object({
  family_id: z.string(),
  title: z.string(),
  earliest_priority_date: z.string(),
  created_at: z.string().datetime().optional(),
});
export type PatentFamily = z.infer<typeof PatentFamilySchema>;

export const PatentRecordSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  family_id: z.string().nullable().optional(),
  patent_number: z.string(),
  title: z.string(),
  assignee: z.string(),
  inventors: z.array(z.string()).default([]),
  jurisdiction: PatentJurisdictionSchema,
  filing_date: z.string(),
  priority_date: z.string(),
  expiration_date: z.string(),
  grant_date: z.string().nullable().optional(),
  status: PatentStatusSchema.default("GRANTED"),
  claim_types: z.array(PatentClaimTypeSchema).default([]),
  composition_of_matter_expiry: z.string().nullable().optional(),
  source_citation: z.string(),
  source_url: z.string().nullable().optional(),
  is_verified_evidence: z.boolean().default(true),
  created_at: z.string().datetime().optional(),
});
export type PatentRecord = z.infer<typeof PatentRecordSchema>;

export const OwnershipAndDealEventSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  deal_type: DealTypeSchema,
  licensor: z.string().nullable().optional(),
  licensee: z.string().nullable().optional(),
  partner: z.string().nullable().optional(),
  territory: z.string().default("Global"),
  effective_date: z.string(),
  disclosed_upfront_usd: z.number().int().nullable().optional(),
  disclosed_milestones_usd: z.number().int().nullable().optional(),
  royalty_rate_pct: z.string().nullable().optional(),
  funding_round: z.string().nullable().optional(),
  investors: z.array(z.string()).default([]),
  summary: z.string(),
  source_citation: z.string(),
  source_url: z.string().nullable().optional(),
  is_verified_evidence: z.boolean().default(true),
  created_at: z.string().datetime().optional(),
});
export type OwnershipAndDealEvent = z.infer<typeof OwnershipAndDealEventSchema>;

export const AssetOwnershipProfileSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  developer: z.string(),
  originator: z.string(),
  current_owner: z.string(),
  former_owners: z.array(z.string()).default([]),
  academic_origin: z.string().nullable().optional(),
  partner: z.string().nullable().optional(),
  licensing_status: LicensingStatusSchema.default("UNKNOWN"),
  licensing_status_rationale: z.string().default(""),
  licensing_status_verified: z.boolean().default(false),
  licensing_verification_source: z.string().nullable().optional(),
  deal_history: z.array(OwnershipAndDealEventSchema).default([]),
  patents: z.array(PatentRecordSchema).default([]),
  fto_disclaimer: z.string().default(MANDATORY_FTO_DISCLAIMER),
  content_hash: z.string().default(""),
  created_at: z.string().datetime().optional(),
  updated_at: z.string().datetime().optional(),
});
export type AssetOwnershipProfile = z.infer<typeof AssetOwnershipProfileSchema>;

export const BatchPatentIngestRequestSchema = z.object({
  patents: z.array(PatentRecordSchema),
});
export type BatchPatentIngestRequest = z.infer<typeof BatchPatentIngestRequestSchema>;

export const BatchPatentIngestResponseSchema = z.object({
  total_submitted: z.number().int(),
  total_ingested: z.number().int(),
  patents: z.array(PatentRecordSchema),
});
export type BatchPatentIngestResponse = z.infer<typeof BatchPatentIngestResponseSchema>;

