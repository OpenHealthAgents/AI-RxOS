import { z } from "zod";
import {
  StrategicActionSchema,
  StrategicAction,
  DevelopmentStageSchema,
  DevelopmentStage,
  ScientificEvidenceStateSchema,
  ScientificEvidenceState,
} from "./opportunity";

export {
  StrategicActionSchema,
  type StrategicAction,
  DevelopmentStageSchema,
  type DevelopmentStage,
  ScientificEvidenceStateSchema,
  type ScientificEvidenceState,
};

// ==============================================================================
// Enumerations
// ==============================================================================

export const ModalityCodeSchema = z.enum([
  "SMALL_MOLECULE",
  "ANTIBODY",
  "ADC",
  "PROTEIN",
  "PEPTIDE",
  "CELL_THERAPY",
  "GENE_THERAPY",
  "RNA_THERAPY",
  "RADIOPHARMACEUTICAL",
  "VACCINE",
  "OTHER",
]);
export type ModalityCode = z.infer<typeof ModalityCodeSchema>;

export const CanonicalEvidencePolaritySchema = z.enum(["SUPPORTING", "CONTRADICTING", "NEUTRAL"]);
export type CanonicalEvidencePolarity = z.infer<typeof CanonicalEvidencePolaritySchema>;

export const AliasTypeSchema = z.enum([
  "generic_name",
  "brand_name",
  "former_name",
  "chemical_name",
  "laboratory_code",
  "synonym",
]);
export type AliasType = z.infer<typeof AliasTypeSchema>;

export const RegulatoryAuthoritySchema = z.enum([
  "FDA",
  "EMA",
  "PMDA",
  "NMPA",
  "MHRA",
  "Health_Canada",
]);
export type RegulatoryAuthority = z.infer<typeof RegulatoryAuthoritySchema>;

export const RegulatoryEventTypeSchema = z.enum([
  "IND_cleared",
  "orphan_designation",
  "fast_track",
  "breakthrough_therapy",
  "priority_review",
  "NDA_BLA_accepted",
  "approval",
  "complete_response_letter",
  "clinical_hold",
]);
export type RegulatoryEventType = z.infer<typeof RegulatoryEventTypeSchema>;

export const AuditEventTypeSchema = z.enum([
  "ASSET_CREATED",
  "ALIAS_ATTACHED",
  "DEV_CODE_ATTACHED",
  "ASSET_MERGED",
  "DECISION_RATIFIED",
  "DECISION_OVERRIDDEN",
  "EVIDENCE_INGESTED",
  "SCORE_RECALCULATED",
]);
export type AuditEventType = z.infer<typeof AuditEventTypeSchema>;

// ==============================================================================
// 1. Organization & User
// ==============================================================================

export const CanonicalOrganizationSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  slug: z.string(),
  tier: z.string().default("enterprise"),
  created_at: z.string().datetime().optional(),
});
export type CanonicalOrganization = z.infer<typeof CanonicalOrganizationSchema>;

export const CanonicalUserSchema = z.object({
  id: z.string().uuid(),
  organization_id: z.string().uuid().nullable().optional(),
  email: z.string().email(),
  full_name: z.string(),
  role: z.string().default("researcher"),
  is_active: z.boolean().default(true),
  created_at: z.string().datetime().optional(),
});
export type CanonicalUser = z.infer<typeof CanonicalUserSchema>;

// ==============================================================================
// 2. Company, Institution, Sponsor
// ==============================================================================

export const CompanySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  normalized_name: z.string().optional(),
  ticker: z.string().nullable().optional(),
  country: z.string().nullable().optional(),
  headquarters: z.string().nullable().optional(),
  company_type: z.string().default("pharma"),
});
export type Company = z.infer<typeof CompanySchema>;

export const InstitutionSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  normalized_name: z.string().optional(),
  institution_type: z.string().default("research_institute"),
  city: z.string().nullable().optional(),
  country: z.string().nullable().optional(),
});
export type Institution = z.infer<typeof InstitutionSchema>;

export const SponsorSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  company_id: z.string().uuid().nullable().optional(),
  institution_id: z.string().uuid().nullable().optional(),
  sponsor_type: z.string().default("industry"),
});
export type Sponsor = z.infer<typeof SponsorSchema>;

// ==============================================================================
// 3. Target, Gene, Protein
// ==============================================================================

export const GeneSchema = z.object({
  id: z.string().uuid(),
  hgnc_symbol: z.string(),
  hgnc_id: z.string().nullable().optional(),
  entrez_id: z.string().nullable().optional(),
  ensembl_id: z.string().nullable().optional(),
  full_name: z.string(),
  chromosome: z.string().nullable().optional(),
});
export type Gene = z.infer<typeof GeneSchema>;

export const ProteinSchema = z.object({
  id: z.string().uuid(),
  uniprot_id: z.string(),
  gene_id: z.string().uuid().nullable().optional(),
  protein_name: z.string(),
  sequence_length: z.number().int().nullable().optional(),
  molecular_weight: z.number().nullable().optional(),
});
export type Protein = z.infer<typeof ProteinSchema>;

export const TargetSchema = z.object({
  id: z.string().uuid(),
  symbol: z.string(),
  name: z.string(),
  gene_id: z.string().uuid().nullable().optional(),
  protein_id: z.string().uuid().nullable().optional(),
  target_class: z.string().default("kinase"),
  validation_level: z.string().default("clinically_validated"),
});
export type Target = z.infer<typeof TargetSchema>;

// ==============================================================================
// 4. Disease, Indication, CancerSubtype
// ==============================================================================

export const DiseaseSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  mesh_id: z.string().nullable().optional(),
  icd10_code: z.string().nullable().optional(),
  doid: z.string().nullable().optional(),
  category: z.string().default("oncology"),
});
export type Disease = z.infer<typeof DiseaseSchema>;

export const IndicationSchema = z.object({
  id: z.string().uuid(),
  disease_id: z.string().uuid().nullable().optional(),
  name: z.string(),
  setting: z.string().nullable().optional(),
  line_of_therapy: z.number().int().nullable().optional(),
  prevalence_annual: z.number().int().nullable().optional(),
});
export type Indication = z.infer<typeof IndicationSchema>;

export const CancerSubtypeSchema = z.object({
  id: z.string().uuid(),
  disease_id: z.string().uuid().nullable().optional(),
  name: z.string(),
  receptor_status: z.string().nullable().optional(),
  histology: z.string().nullable().optional(),
  frequency_percentage: z.number().nullable().optional(),
});
export type CancerSubtype = z.infer<typeof CancerSubtypeSchema>;

// ==============================================================================
// 5. Biomarker & Mutation
// ==============================================================================

export const BiomarkerSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  target_id: z.string().uuid().nullable().optional(),
  biomarker_type: z.string().default("mutation"),
  diagnostic_test_available: z.boolean().default(true),
});
export type Biomarker = z.infer<typeof BiomarkerSchema>;

export const MutationSchema = z.object({
  id: z.string().uuid(),
  biomarker_id: z.string().uuid().nullable().optional(),
  gene_id: z.string().uuid().nullable().optional(),
  protein_change: z.string(),
  exon: z.number().int().nullable().optional(),
  functional_consequence: z.string().default("activating"),
});
export type Mutation = z.infer<typeof MutationSchema>;

// ==============================================================================
// 6. Modality & MechanismOfAction
// ==============================================================================

export const ModalitySchema = z.object({
  id: z.string().uuid(),
  code: ModalityCodeSchema,
  name: z.string(),
  description: z.string().nullable().optional(),
});
export type Modality = z.infer<typeof ModalitySchema>;

export const MechanismOfActionSchema = z.object({
  id: z.string().uuid(),
  target_id: z.string().uuid().nullable().optional(),
  name: z.string(),
  binding_type: z.string().default("irreversible_covalent"),
  selectivity_profile: z.string().nullable().optional(),
});
export type MechanismOfAction = z.infer<typeof MechanismOfActionSchema>;

// ==============================================================================
// 7. Asset Identification, Development Codes, Aliases
// ==============================================================================

export const AssetDevelopmentCodeSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  code: z.string(),
  normalized_code: z.string().optional(),
  originator_company_id: z.string().uuid().nullable().optional(),
  is_primary: z.boolean().default(false),
  notes: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type AssetDevelopmentCode = z.infer<typeof AssetDevelopmentCodeSchema>;

export const AssetAliasSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  alias: z.string(),
  normalized_alias: z.string().optional(),
  alias_type: AliasTypeSchema.default("synonym"),
  is_primary_for_type: z.boolean().default(false),
  verification_state: z.string().default("verified"),
  created_at: z.string().datetime().optional(),
});
export type AssetAlias = z.infer<typeof AssetAliasSchema>;

// ==============================================================================
// 8. Trial, Study, Publication
// ==============================================================================

export const TrialSchema = z.object({
  id: z.string().uuid(),
  nct_id: z.string(),
  brief_title: z.string(),
  official_title: z.string().nullable().optional(),
  phase: z.string().default("Phase 2"),
  overall_status: z.string().default("Active, not recruiting"),
  sponsor_id: z.string().uuid().nullable().optional(),
  enrollment: z.number().int().nullable().optional(),
  primary_completion_date: z.string().nullable().optional(),
  results_first_posted: z.string().nullable().optional(),
});
export type Trial = z.infer<typeof TrialSchema>;

export const StudySchema = z.object({
  id: z.string().uuid(),
  trial_id: z.string().uuid().nullable().optional(),
  name: z.string(),
  study_type: z.string().default("interventional_trial"),
  lead_institution_id: z.string().uuid().nullable().optional(),
});
export type Study = z.infer<typeof StudySchema>;

export const PublicationSchema = z.object({
  id: z.string().uuid(),
  pmid: z.string().nullable().optional(),
  doi: z.string().nullable().optional(),
  pmcid: z.string().nullable().optional(),
  title: z.string(),
  journal: z.string().nullable().optional(),
  publication_year: z.number().int(),
  published_date: z.string().nullable().optional(),
  url: z.string().url().nullable().optional(),
  authors: z.array(z.string()).default([]),
  abstract: z.string().nullable().optional(),
});
export type Publication = z.infer<typeof PublicationSchema>;

// ==============================================================================
// 9. Evidence & EvidenceObservation
// ==============================================================================

export const EvidenceSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  publication_id: z.string().uuid().nullable().optional(),
  trial_id: z.string().uuid().nullable().optional(),
  evidence_type: z.string().default("literature"),
  source_ref: z.string(),
  citation: z.string(),
  publication_year: z.number().int(),
  as_of_date: z.string(),
  polarity: CanonicalEvidencePolaritySchema.default("SUPPORTING"),
  is_verified: z.boolean().default(true),
  excerpt: z.string(),
  created_at: z.string().datetime().optional(),
});
export type Evidence = z.infer<typeof EvidenceSchema>;

export const EvidenceObservationSchema = z.object({
  id: z.string().uuid(),
  evidence_id: z.string().uuid(),
  asset_id: z.string().uuid(),
  parameter_name: z.string(),
  observed_value: z.string(),
  numeric_value: z.number().nullable().optional(),
  unit: z.string().nullable().optional(),
  statistical_significance: z.string().nullable().optional(),
  observation_state: ScientificEvidenceStateSchema.default("verified_fact"),
});
export type EvidenceObservation = z.infer<typeof EvidenceObservationSchema>;

// ==============================================================================
// 10. ClinicalOutcome & PreclinicalResult
// ==============================================================================

export const ClinicalOutcomeSchema = z.object({
  id: z.string().uuid(),
  trial_id: z.string().uuid(),
  asset_id: z.string().uuid(),
  endpoint_name: z.string(),
  endpoint_type: z.string().default("primary"),
  cohort_description: z.string().nullable().optional(),
  response_rate: z.number().nullable().optional(),
  median_months: z.number().nullable().optional(),
  hazard_ratio: z.number().nullable().optional(),
  confidence_interval: z.string().nullable().optional(),
  is_statistically_significant: z.boolean().nullable().optional(),
});
export type ClinicalOutcome = z.infer<typeof ClinicalOutcomeSchema>;

export const PreclinicalResultSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  assay_type: z.string().default("biochemical_kinase"),
  target_id: z.string().uuid().nullable().optional(),
  cell_line: z.string().nullable().optional(),
  ic50_nm: z.number().nullable().optional(),
  ec50_nm: z.number().nullable().optional(),
  tumor_growth_inhibition_pct: z.number().nullable().optional(),
  is_wt_sparing: z.boolean().nullable().optional(),
});
export type PreclinicalResult = z.infer<typeof PreclinicalResultSchema>;

// ==============================================================================
// 11. SafetyObservation & CNSObservation
// ==============================================================================

export const SafetyObservationSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  adverse_event_name: z.string(),
  grade_all_rate: z.number().nullable().optional(),
  grade_3_plus_rate: z.number().nullable().optional(),
  dose_limiting_toxicity: z.boolean().default(false),
  discontinuation_rate: z.number().nullable().optional(),
  therapeutic_index_rating: z.string().default("favorable"),
});
export type SafetyObservation = z.infer<typeof SafetyObservationSchema>;

export const CNSObservationSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  brain_to_plasma_ratio: z.number().nullable().optional(),
  csf_penetration_verified: z.boolean().default(false),
  intracranial_orr: z.number().nullable().optional(),
  intracranial_pfs_months: z.number().nullable().optional(),
  leptomeningeal_activity: z.boolean().default(false),
  cns_score: z.number().int().min(0).max(100).default(50),
});
export type CNSObservation = z.infer<typeof CNSObservationSchema>;

// ==============================================================================
// 12. PatientPopulation, ResistanceMechanism, Combination
// ==============================================================================

export const PatientPopulationSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  population_name: z.string(),
  indication_id: z.string().uuid().nullable().optional(),
  biomarker_id: z.string().uuid().nullable().optional(),
  prior_lines: z.string().nullable().optional(),
  cns_metastases_benefit: z.boolean().default(true),
  match_score: z.number().min(0).max(100).default(80.0),
});
export type PatientPopulation = z.infer<typeof PatientPopulationSchema>;

export const CanonicalResistanceMechanismSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  name: z.string(),
  impact_level: z.string().default("High"),
  is_predicted: z.boolean().default(false),
  mechanism_description: z.string(),
});
export type CanonicalResistanceMechanism = z.infer<typeof CanonicalResistanceMechanismSchema>;

export const CombinationSchema = z.object({
  id: z.string().uuid(),
  primary_asset_id: z.string().uuid(),
  partner_name: z.string(),
  partner_asset_id: z.string().uuid().nullable().optional(),
  synergy_type: z.string(),
  rationale: z.string(),
  clinical_status: z.string(),
});
export type Combination = z.infer<typeof CombinationSchema>;

// ==============================================================================
// 13. Patent, LicenseEvent, Partnership, RegulatoryEvent
// ==============================================================================

export const PatentSchema = z.object({
  id: z.string().uuid(),
  patent_number: z.string(),
  title: z.string(),
  assignee_company_id: z.string().uuid().nullable().optional(),
  priority_date: z.string().nullable().optional(),
  filing_date: z.string().nullable().optional(),
  grant_date: z.string().nullable().optional(),
  expiration_date: z.string().nullable().optional(),
  status: z.string().default("granted"),
});
export type Patent = z.infer<typeof PatentSchema>;

export const LicenseEventSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  licensor_company_id: z.string().uuid(),
  licensee_company_id: z.string().uuid(),
  event_type: z.string().default("exclusive_license"),
  territory: z.string().default("Global"),
  effective_date: z.string(),
  disclosed_upfront_usd: z.number().int().nullable().optional(),
  disclosed_milestones_usd: z.number().int().nullable().optional(),
});
export type LicenseEvent = z.infer<typeof LicenseEventSchema>;

export const PartnershipSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  partner_company_id: z.string().uuid(),
  scope: z.string(),
  start_date: z.string(),
  status: z.string().default("active"),
});
export type Partnership = z.infer<typeof PartnershipSchema>;

export const RegulatoryEventSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  authority: RegulatoryAuthoritySchema.default("FDA"),
  event_type: RegulatoryEventTypeSchema.default("fast_track"),
  indication_id: z.string().uuid().nullable().optional(),
  event_date: z.string(),
  dossier_notes: z.string().nullable().optional(),
});
export type RegulatoryEvent = z.infer<typeof RegulatoryEventSchema>;

// ==============================================================================
// 14. CommercialObservation & CompetitiveAsset
// ==============================================================================

export const CommercialObservationSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  estimated_peak_sales_usd: z.number().int().nullable().optional(),
  addressable_market_usd: z.number().int().nullable().optional(),
  target_patient_annual_count: z.number().int().nullable().optional(),
  pricing_strategy: z.string().nullable().optional(),
  market_exclusivity_expiry: z.string().nullable().optional(),
});
export type CommercialObservation = z.infer<typeof CommercialObservationSchema>;

export const CompetitiveAssetSchema = z.object({
  id: z.string().uuid(),
  target_asset_id: z.string().uuid(),
  competitor_asset_id: z.string().uuid(),
  competitive_relationship: z.string().default("direct_benchmark"),
  differentiating_advantage: z.string(),
});
export type CompetitiveAsset = z.infer<typeof CompetitiveAssetSchema>;

// ==============================================================================
// 15. Decision, Recommendation, Score, ScoreComponent, Prediction
// ==============================================================================

export const DecisionSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  organization_id: z.string().uuid().nullable().optional(),
  user_id: z.string().uuid().nullable().optional(),
  action: StrategicActionSchema.default("PURSUE"),
  is_human_override: z.boolean().default(false),
  ai_suggested_action: StrategicActionSchema.default("PURSUE"),
  clinical_justification: z.string(),
  decision_timestamp: z.string().datetime().optional(),
  checklist: z.record(z.string(), z.boolean()).default({}),
});
export type Decision = z.infer<typeof DecisionSchema>;

export const RecommendationSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  action: StrategicActionSchema.default("PURSUE"),
  confidence: z.number().min(0).max(100),
  rationale: z.string(),
  badge_text: z.string(),
  model_version: z.string().default("Model v0.1"),
});
export type Recommendation = z.infer<typeof RecommendationSchema>;

export const ScoreComponentSchema = z.object({
  id: z.string().uuid(),
  score_id: z.string().uuid(),
  component_name: z.string(),
  weight: z.number(),
  raw_value: z.number(),
  weighted_value: z.number(),
});
export type ScoreComponent = z.infer<typeof ScoreComponentSchema>;

export const ScoreSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  score_type: z.string().default("development_potential"),
  numeric_score: z.number().min(0).max(100),
  confidence_interval_low: z.number().nullable().optional(),
  confidence_interval_high: z.number().nullable().optional(),
  model_lineage: z.string().default("Calibrated Multi-Attribute Engine"),
  components: z.array(ScoreComponentSchema).default([]),
});
export type Score = z.infer<typeof ScoreSchema>;

export const PredictionSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  transition_stage: z.string(),
  predicted_probability: z.number().min(0).max(1),
  model_version: z.string().default("Model v0.1"),
  calibration_data: z.string().nullable().optional(),
});
export type Prediction = z.infer<typeof PredictionSchema>;

// ==============================================================================
// 16. BacktestSnapshot & AuditEvent
// ==============================================================================

export const BacktestSnapshotSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  cutoff_date: z.string(),
  predicted_action: StrategicActionSchema,
  predicted_dps: z.number(),
  eligible_evidence_count: z.number().int(),
  suppressed_future_evidence_count: z.number().int(),
  ground_truth_outcome: z.string(),
  prediction_accuracy: z.string(),
  anti_leakage_audit_passed: z.boolean().default(true),
  created_at: z.string().datetime().optional(),
});
export type BacktestSnapshot = z.infer<typeof BacktestSnapshotSchema>;

export const AuditEventSchema = z.object({
  id: z.string().uuid(),
  event_type: AuditEventTypeSchema,
  entity_id: z.string().uuid(),
  entity_type: z.string(),
  actor_id: z.string().uuid().nullable().optional(),
  actor_name: z.string(),
  summary: z.string(),
  metadata: z.record(z.string(), z.unknown()).default({}),
  created_at: z.string().datetime().optional(),
});
export type AuditEvent = z.infer<typeof AuditEventSchema>;

// ==============================================================================
// 17. Core Asset Aggregate
// ==============================================================================

export const AssetSchema = z.object({
  id: z.string().uuid(),
  preferred_name: z.string(),
  canonical_slug: z.string().default(""),
  modality_id: z.string().uuid().nullable().optional(),
  modality_code: ModalityCodeSchema.default("SMALL_MOLECULE"),
  primary_target_id: z.string().uuid().nullable().optional(),
  primary_target_symbol: z.string().default("HER2"),
  primary_moa_id: z.string().uuid().nullable().optional(),
  primary_moa_name: z.string().nullable().optional(),
  owner_company_id: z.string().uuid().nullable().optional(),
  owner_company_name: z.string().default("Boehringer Ingelheim"),
  developer_company_id: z.string().uuid().nullable().optional(),
  developer_company_name: z.string().nullable().optional(),
  sponsor_id: z.string().uuid().nullable().optional(),
  current_development_stage: DevelopmentStageSchema.default("Phase II"),
  status_label: z.string().default("Investigational"),
  primary_indication_id: z.string().uuid().nullable().optional(),
  primary_indication_name: z.string().default("HER2-mutant metastatic breast cancer"),
  is_deprecated: z.boolean().default(false),
  merged_into_asset_id: z.string().uuid().nullable().optional(),
  attributes: z.record(z.string(), z.unknown()).default({}),
  created_at: z.string().datetime().optional(),
  updated_at: z.string().datetime().optional(),

  // Relational sub-collections
  development_codes: z.array(AssetDevelopmentCodeSchema).default([]),
  aliases: z.array(AssetAliasSchema).default([]),
  targets: z.array(TargetSchema).default([]),
  indications: z.array(IndicationSchema).default([]),
  trials: z.array(TrialSchema).default([]),
  publications: z.array(PublicationSchema).default([]),
  evidence: z.array(EvidenceSchema).default([]),
  outcomes: z.array(ClinicalOutcomeSchema).default([]),
  patents: z.array(PatentSchema).default([]),
  partnerships: z.array(PartnershipSchema).default([]),
  regulatory_events: z.array(RegulatoryEventSchema).default([]),
});
export type Asset = z.infer<typeof AssetSchema>;
