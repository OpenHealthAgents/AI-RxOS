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

export const CanonicalEvidencePolaritySchema = z.enum([
  "SUPPORTING",
  "CONTRADICTING",
  "CONTRADICTORY",
  "NEUTRAL",
  "UNKNOWN",
]);
export type CanonicalEvidencePolarity = z.infer<typeof CanonicalEvidencePolaritySchema>;

export const AliasTypeSchema = z.enum([
  "generic_name",
  "brand_name",
  "former_name",
  "chemical_name",
  "laboratory_code",
  "company_code",
  "development_code",
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
// 2. Company, Institution, Stakeholder Roles, and Ownership Tracking
// ==============================================================================

export const DealTypeSchema = z.enum([
  "acquisition",
  "asset_transfer",
  "license",
  "licensing",
  "co_development",
  "option",
  "partnership",
  "funding",
  "termination",
  "ACQUISITION",
  "ASSET_TRANSFER",
  "LICENSING",
  "LICENSING_ANNOUNCEMENT",
  "CO_DEVELOPMENT",
  "OPTION",
  "OPTION_AGREEMENT",
  "PARTNERSHIP",
  "FUNDING",
]);
export type DealType = z.infer<typeof DealTypeSchema>;

export const CompanySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  normalized_name: z.string().optional(),
  ticker: z.string().nullable().optional(),
  country: z.string().nullable().optional(),
  headquarters: z.string().nullable().optional(),
  company_type: z.string().default("pharma"),
  created_at: z.string().datetime().optional(),
});
export type Company = z.infer<typeof CompanySchema>;

export const InstitutionSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  normalized_name: z.string().optional(),
  institution_type: z.string().default("research_institute"),
  city: z.string().nullable().optional(),
  country: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type Institution = z.infer<typeof InstitutionSchema>;

export const DeveloperSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  company_id: z.string().uuid().nullable().optional(),
  institution_id: z.string().uuid().nullable().optional(),
  role_description: z.string().default("Lead Clinical Development"),
  created_at: z.string().datetime().optional(),
});
export type Developer = z.infer<typeof DeveloperSchema>;

export const SponsorSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  company_id: z.string().uuid().nullable().optional(),
  institution_id: z.string().uuid().nullable().optional(),
  sponsor_type: z.string().default("industry"),
  created_at: z.string().datetime().optional(),
});
export type Sponsor = z.infer<typeof SponsorSchema>;

export const OwnerSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  company_id: z.string().uuid().nullable().optional(),
  institution_id: z.string().uuid().nullable().optional(),
  ownership_type: z.string().default("commercial_sponsor"),
  created_at: z.string().datetime().optional(),
});
export type Owner = z.infer<typeof OwnerSchema>;

export const PartnerSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  company_id: z.string().uuid().nullable().optional(),
  institution_id: z.string().uuid().nullable().optional(),
  scope: z.string().default("Co-Development & Commercialization"),
  created_at: z.string().datetime().optional(),
});
export type Partner = z.infer<typeof PartnerSchema>;

export const LicensorSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  company_id: z.string().uuid().nullable().optional(),
  institution_id: z.string().uuid().nullable().optional(),
  jurisdiction: z.string().default("Global"),
  created_at: z.string().datetime().optional(),
});
export type Licensor = z.infer<typeof LicensorSchema>;

export const LicenseeSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  company_id: z.string().uuid().nullable().optional(),
  institution_id: z.string().uuid().nullable().optional(),
  territory: z.string().default("Global"),
  created_at: z.string().datetime().optional(),
});
export type Licensee = z.infer<typeof LicenseeSchema>;

export const AcquirerSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  company_id: z.string().uuid().nullable().optional(),
  acquisition_date: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type Acquirer = z.infer<typeof AcquirerSchema>;

export const AssetOwnershipTransferSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  deal_type: DealTypeSchema,
  effective_date: z.string(),
  end_date: z.string().nullable().optional(),
  from_entity_name: z.string().nullable().optional(),
  from_entity_id: z.string().uuid().nullable().optional(),
  to_entity_name: z.string().nullable().optional(),
  to_entity_id: z.string().uuid().nullable().optional(),
  licensor: z.string().nullable().optional(),
  licensee: z.string().nullable().optional(),
  partner: z.string().nullable().optional(),
  acquirer: z.string().nullable().optional(),
  territory: z.string().default("Global"),
  scope: z.string().default("Development and Commercialization Rights"),
  is_exclusive: z.boolean().default(true),
  disclosed_upfront_usd: z.number().int().nullable().optional(),
  disclosed_milestones_usd: z.number().int().nullable().optional(),
  royalty_rate_pct: z.string().nullable().optional(),
  is_active: z.boolean().default(true),
  termination_reason: z.string().nullable().optional(),
  source_citation: z.string().default(""),
  source_url: z.string().nullable().optional(),
  is_verified: z.boolean().default(true),
  created_at: z.string().datetime().optional(),
});
export type AssetOwnershipTransfer = z.infer<typeof AssetOwnershipTransferSchema>;

// ==============================================================================
// 3. Target, Gene, Protein, Pathway
// ==============================================================================

export const PathwaySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  identifier: z.string().nullable().optional(), // e.g. KEGG:hsa04012, Reactome:R-HSA-1257604
  category: z.string().default("signal_transduction"),
  description: z.string().nullable().optional(),
  gene_ids: z.array(z.string().uuid()).default([]),
  target_ids: z.array(z.string().uuid()).default([]),
  created_at: z.string().datetime().optional(),
});
export type Pathway = z.infer<typeof PathwaySchema>;

export const GeneSchema = z.object({
  id: z.string().uuid(),
  hgnc_symbol: z.string(),
  hgnc_id: z.string().nullable().optional(),
  entrez_id: z.string().nullable().optional(),
  ensembl_id: z.string().nullable().optional(),
  full_name: z.string(),
  chromosome: z.string().nullable().optional(),
  pathway_ids: z.array(z.string().uuid()).default([]),
  created_at: z.string().datetime().optional(),
});
export type Gene = z.infer<typeof GeneSchema>;

export const ProteinSchema = z.object({
  id: z.string().uuid(),
  uniprot_id: z.string(),
  gene_id: z.string().uuid().nullable().optional(),
  protein_name: z.string(),
  sequence_length: z.number().int().nullable().optional(),
  molecular_weight: z.number().nullable().optional(),
  isoforms: z.array(z.string()).default([]),
  created_at: z.string().datetime().optional(),
});
export type Protein = z.infer<typeof ProteinSchema>;

export const TargetSchema = z.object({
  id: z.string().uuid(),
  symbol: z.string(),
  name: z.string(),
  gene_id: z.string().uuid().nullable().optional(),
  protein_id: z.string().uuid().nullable().optional(),
  pathway_ids: z.array(z.string().uuid()).default([]),
  target_class: z.string().default("kinase"),
  validation_level: z.string().default("clinically_validated"),
  created_at: z.string().datetime().optional(),
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
  created_at: z.string().datetime().optional(),
});
export type Disease = z.infer<typeof DiseaseSchema>;

export const IndicationSchema = z.object({
  id: z.string().uuid(),
  disease_id: z.string().uuid().nullable().optional(),
  name: z.string(),
  setting: z.string().nullable().optional(),
  line_of_therapy: z.number().int().nullable().optional(),
  prevalence_annual: z.number().int().nullable().optional(),
  subtype_ids: z.array(z.string().uuid()).default([]),
  biomarker_ids: z.array(z.string().uuid()).default([]),
  created_at: z.string().datetime().optional(),
});
export type Indication = z.infer<typeof IndicationSchema>;

export const CancerSubtypeSchema = z.object({
  id: z.string().uuid(),
  disease_id: z.string().uuid().nullable().optional(),
  indication_id: z.string().uuid().nullable().optional(),
  name: z.string(),
  receptor_status: z.string().nullable().optional(),
  histology: z.string().nullable().optional(),
  frequency_percentage: z.number().nullable().optional(),
  biomarker_ids: z.array(z.string().uuid()).default([]),
  created_at: z.string().datetime().optional(),
});
export type CancerSubtype = z.infer<typeof CancerSubtypeSchema>;

// ==============================================================================
// 5. Biomarker & Mutation
// ==============================================================================

export const BiomarkerSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  target_id: z.string().uuid().nullable().optional(),
  gene_id: z.string().uuid().nullable().optional(),
  biomarker_type: z.string().default("mutation"),
  diagnostic_test_available: z.boolean().default(true),
  cdx_test_name: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type Biomarker = z.infer<typeof BiomarkerSchema>;

export const MutationSchema = z.object({
  id: z.string().uuid(),
  biomarker_id: z.string().uuid().nullable().optional(),
  gene_id: z.string().uuid().nullable().optional(),
  target_id: z.string().uuid().nullable().optional(),
  protein_change: z.string(),
  exon: z.number().int().nullable().optional(),
  functional_consequence: z.string().default("activating"),
  resistance_mechanism_ids: z.array(z.string().uuid()).default([]),
  created_at: z.string().datetime().optional(),
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
  created_at: z.string().datetime().optional(),
});
export type Modality = z.infer<typeof ModalitySchema>;

export const MechanismOfActionSchema = z.object({
  id: z.string().uuid(),
  target_id: z.string().uuid().nullable().optional(),
  pathway_id: z.string().uuid().nullable().optional(),
  name: z.string(),
  binding_type: z.string().default("irreversible_covalent"),
  selectivity_profile: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
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
  confidence: z.number().min(0).max(1).default(1.0),
  source_context: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type AssetAlias = z.infer<typeof AssetAliasSchema>;

export const AssetIdentitySchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  preferred_name: z.string(),
  generic_name: z.string().nullable().optional(),
  development_code: z.string().default(""),
  former_names: z.array(z.string()).default([]),
  company_codes: z.array(z.string()).default([]),
  aliases: z.array(AssetAliasSchema).default([]),
  registry_identifiers: z.record(z.string(), z.string()).default({}),
  normalized_tokens: z.array(z.string()).default([]),
  resolution_hash: z.string().default(""),
  confidence: z.number().min(0).max(1).default(1.0),
  created_at: z.string().datetime().optional(),
  updated_at: z.string().datetime().optional(),
});
export type AssetIdentity = z.infer<typeof AssetIdentitySchema>;

export const AssetRelationshipPredicateSchema = z.enum([
  "TARGETS",
  "HAS_MODALITY",
  "ACTS_VIA_MECHANISM",
  "MODULATES_PATHWAY",
  "INDICATED_FOR",
  "ASSOCIATED_WITH_DISEASE",
  "SUBTYPE_CLASSIFIED",
  "STRATIFIED_BY_BIOMARKER",
  "ENROLLS_POPULATION",
  "AT_DEVELOPMENT_STAGE",
  "OWNED_BY",
  "DEVELOPED_BY",
  "SPONSORED_BY",
  "ORIGINATED_BY",
  "COMBINED_WITH",
  "COMPETES_WITH",
  "HAS_RESISTANCE_MECHANISM",
  "OVERCOMES_RESISTANCE",
]);
export type AssetRelationshipPredicate = z.infer<typeof AssetRelationshipPredicateSchema>;

export const DomainRelationshipPredicateSchema = z.enum([
  "ENCODES",
  "TARGET_DERIVED_FROM",
  "PART_OF_PATHWAY",
  "MODULATES_PATHWAY",
  "HARBORS_MUTATION",
  "STRATIFIES",
  "CONCURRENT_WITH",
  "CONFERS_RESISTANCE",
  "OVERCOMES_RESISTANCE",
  "HAS_INDICATION",
  "CLASSIFIED_AS_SUBTYPE",
  "POPULATION_DEFINED_BY",
  "TREATS",
  "ACTS_VIA_MECHANISM",
  "HAS_MODALITY",
  "SYNERGIZES_WITH",
]);
export type DomainRelationshipPredicate = z.infer<typeof DomainRelationshipPredicateSchema>;

export const AssetRelationshipSchema = z.object({
  id: z.string().uuid(),
  subject_asset_id: z.string().uuid(),
  predicate: AssetRelationshipPredicateSchema,
  object_entity_id: z.string().uuid(),
  object_entity_type: z.string().default("target"),
  object_entity_name: z.string(),
  confidence: z.number().min(0).max(1).default(1.0),
  verification_state: z.string().default("verified"),
  attributes: z.record(z.string(), z.unknown()).default({}),
  evidence_ids: z.array(z.string().uuid()).default([]),
  created_at: z.string().datetime().optional(),
});
export type AssetRelationship = z.infer<typeof AssetRelationshipSchema>;

export const DomainRelationshipSchema = z.object({
  id: z.string().uuid(),
  source_entity_id: z.string().uuid(),
  source_entity_type: z.string(),
  predicate: DomainRelationshipPredicateSchema,
  target_entity_id: z.string().uuid(),
  target_entity_type: z.string(),
  confidence: z.number().min(0).max(1).default(1.0),
  verification_state: z.string().default("verified"),
  evidence_ids: z.array(z.string().uuid()).default([]),
  attributes: z.record(z.string(), z.unknown()).default({}),
  created_at: z.string().datetime().optional(),
});
export type DomainRelationship = z.infer<typeof DomainRelationshipSchema>;

// ==============================================================================
// 8. Trial, Study, TrialArm, Intervention, Population, Endpoint, AdverseEvent, TrialStatusHistory
// ==============================================================================

export const TrialPhaseSchema = z.enum([
  "Phase I",
  "Phase Ib",
  "Phase II",
  "Phase II/III",
  "Phase III",
  "Phase IV",
  "Early Phase 1",
  "Not Applicable",
]);
export type TrialPhase = z.infer<typeof TrialPhaseSchema>;

export const TrialLifecycleStatusSchema = z.enum([
  "Phase I",
  "Phase Ib",
  "Phase II",
  "Phase II/III",
  "Phase III",
  "Regulatory review",
  "Approved",
  "Withdrawn",
  "Terminated",
  "Discontinued",
  "Active, not recruiting",
  "Recruiting",
  "Completed",
  "Suspended",
  "Not yet recruiting",
  "Unknown",
]);
export type TrialLifecycleStatus = z.infer<typeof TrialLifecycleStatusSchema>;

export const TrialArmSchema = z.object({
  id: z.string().uuid(),
  trial_id: z.string().uuid().nullable().optional(),
  arm_label: z.string(),
  arm_type: z.string().default("experimental"),
  description: z.string().nullable().optional(),
  cohort_size: z.number().int().nullable().optional(),
  intervention_names: z.array(z.string()).default([]),
  intervention_ids: z.array(z.string().uuid()).default([]),
  created_at: z.string().datetime().optional(),
});
export type TrialArm = z.infer<typeof TrialArmSchema>;

export const InterventionSchema = z.object({
  id: z.string().uuid(),
  trial_id: z.string().uuid().nullable().optional(),
  arm_id: z.string().uuid().nullable().optional(),
  asset_id: z.string().uuid().nullable().optional(),
  name: z.string(),
  intervention_type: z.string().default("drug"),
  description: z.string().nullable().optional(),
  dosage_form: z.string().nullable().optional(),
  dose_regimen: z.string().nullable().optional(),
  is_investigational: z.boolean().default(true),
  created_at: z.string().datetime().optional(),
});
export type Intervention = z.infer<typeof InterventionSchema>;

export const PopulationSchema = z.object({
  id: z.string().uuid(),
  trial_id: z.string().uuid().nullable().optional(),
  asset_id: z.string().uuid().nullable().optional(),
  population_name: z.string(),
  condition: z.string().nullable().optional(),
  disease_id: z.string().uuid().nullable().optional(),
  indication_id: z.string().uuid().nullable().optional(),
  cancer_subtype_id: z.string().uuid().nullable().optional(),
  cancer_subtype: z.string().nullable().optional(),
  biomarker_ids: z.array(z.string().uuid()).default([]),
  biomarker_criteria: z.array(z.string()).default([]),
  mutation_ids: z.array(z.string().uuid()).default([]),
  prior_lines: z.string().nullable().optional(),
  line_of_therapy: z.string().nullable().optional(),
  cns_metastases_allowed: z.boolean().nullable().optional(),
  cns_metastases_benefit: z.boolean().default(true),
  match_score: z.number().min(0).max(100).default(80.0),
  inclusion_criteria: z.array(z.string()).default([]),
  exclusion_criteria: z.array(z.string()).default([]),
  created_at: z.string().datetime().optional(),
});
export type Population = z.infer<typeof PopulationSchema>;

export const EndpointSchema = z.object({
  id: z.string().uuid(),
  trial_id: z.string().uuid().nullable().optional(),
  endpoint_title: z.string(),
  endpoint_type: z.string().default("primary"),
  metric: z.string().nullable().optional(),
  time_frame: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  is_met: z.boolean().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type Endpoint = z.infer<typeof EndpointSchema>;

export const AdverseEventSchema = z.object({
  id: z.string().uuid(),
  trial_id: z.string().uuid().nullable().optional(),
  arm_id: z.string().uuid().nullable().optional(),
  asset_id: z.string().uuid().nullable().optional(),
  term: z.string(),
  category: z.string().nullable().optional(),
  grade: z.string().nullable().default("Grade 3+"),
  affected_count: z.number().int().nullable().optional(),
  total_evaluated: z.number().int().nullable().optional(),
  frequency_pct: z.number().nullable().optional(),
  is_serious: z.boolean().default(false),
  dose_limiting: z.boolean().default(false),
  treatment_emergent: z.boolean().default(true),
  source_citation: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type AdverseEvent = z.infer<typeof AdverseEventSchema>;

import {
  TrialStatusHistorySchema,
  type TrialStatusHistory,
} from "./clinicaltrials";
export { TrialStatusHistorySchema, type TrialStatusHistory };

export const ClinicalOutcomeSchema = z.object({
  id: z.string().uuid(),
  trial_id: z.string().uuid(),
  asset_id: z.string().uuid().nullable().optional(),
  arm_id: z.string().uuid().nullable().optional(),
  endpoint_id: z.string().uuid().nullable().optional(),
  endpoint_name: z.string(),
  endpoint_type: z.string().default("primary"),
  cohort_description: z.string().nullable().optional(),
  metric: z.string().nullable().optional(),
  response_rate: z.number().nullable().optional(),
  median_months: z.number().nullable().optional(),
  hazard_ratio: z.number().nullable().optional(),
  confidence_interval: z.string().nullable().optional(),
  p_value: z.number().nullable().optional(),
  sample_size: z.number().int().nullable().optional(),
  is_statistically_significant: z.boolean().nullable().optional(),
  observation_state: ScientificEvidenceStateSchema.default("verified_fact"),
  source_citation: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type ClinicalOutcome = z.infer<typeof ClinicalOutcomeSchema>;

export const TrialSchema = z.object({
  id: z.string().uuid(),
  nct_id: z.string(),
  brief_title: z.string(),
  official_title: z.string().nullable().optional(),
  phase: z.string().default("Phase 2"),
  overall_status: z.string().default("Active, not recruiting"),
  normalized_stage: DevelopmentStageSchema.default("Phase II"),
  sponsor_id: z.string().uuid().nullable().optional(),
  sponsor_name: z.string().nullable().optional(),
  collaborators: z.array(z.string()).default([]),
  enrollment: z.number().int().nullable().optional(),
  start_date: z.string().nullable().optional(),
  primary_completion_date: z.string().nullable().optional(),
  completion_date: z.string().nullable().optional(),
  results_first_posted: z.string().nullable().optional(),
  study_type: z.string().default("interventional"),
  allocation: z.string().nullable().optional(),
  intervention_model: z.string().nullable().optional(),
  masking: z.string().nullable().optional(),
  primary_purpose: z.string().nullable().optional(),
  why_stopped: z.string().nullable().optional(),
  arms: z.array(TrialArmSchema).default([]),
  interventions: z.array(InterventionSchema).default([]),
  populations: z.array(PopulationSchema).default([]),
  endpoints: z.array(EndpointSchema).default([]),
  outcomes: z.array(ClinicalOutcomeSchema).default([]),
  adverse_events: z.array(AdverseEventSchema).default([]),
  status_history: z.array(TrialStatusHistorySchema).default([]),
  created_at: z.string().datetime().optional(),
});
export type Trial = z.infer<typeof TrialSchema>;

export const StudySchema = z.object({
  id: z.string().uuid(),
  trial_id: z.string().uuid().nullable().optional(),
  name: z.string(),
  study_code: z.string().nullable().optional(),
  study_type: z.string().default("interventional_trial"),
  lead_institution_id: z.string().uuid().nullable().optional(),
  lead_institution_name: z.string().nullable().optional(),
  protocol_id: z.string().nullable().optional(),
  phase: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  trials: z.array(TrialSchema).default([]),
  created_at: z.string().datetime().optional(),
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
// 10. PreclinicalResult
// ==============================================================================

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

export const PatientPopulationSchema = PopulationSchema;
export type PatientPopulation = Population;

export const CanonicalResistanceMechanismSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid().nullable().optional(),
  target_id: z.string().uuid().nullable().optional(),
  gene_id: z.string().uuid().nullable().optional(),
  mutation_id: z.string().uuid().nullable().optional(),
  pathway_id: z.string().uuid().nullable().optional(),
  name: z.string(),
  impact_level: z.string().default("High"),
  is_predicted: z.boolean().default(false),
  mechanism_type: z.string().default("on_target_mutation"),
  mechanism_description: z.string(),
  counteracting_combination_ids: z.array(z.string().uuid()).default([]),
  created_at: z.string().datetime().optional(),
});
export type CanonicalResistanceMechanism = z.infer<typeof CanonicalResistanceMechanismSchema>;

export const CombinationSchema = z.object({
  id: z.string().uuid(),
  primary_asset_id: z.string().uuid().nullable().optional(),
  partner_name: z.string(),
  partner_asset_id: z.string().uuid().nullable().optional(),
  target_ids: z.array(z.string().uuid()).default([]),
  pathway_ids: z.array(z.string().uuid()).default([]),
  synergy_type: z.string(),
  rationale: z.string(),
  clinical_status: z.string(),
  addressed_resistance_mechanism_ids: z.array(z.string().uuid()).default([]),
  created_at: z.string().datetime().optional(),
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

  // 17 Core Canonical Domain Properties
  development_code: z.string().default(""),
  generic_name: z.string().nullable().optional(),
  former_names: z.array(z.string()).default([]),
  aliases: z.array(AssetAliasSchema).default([]),
  company_codes: z.array(z.string()).default([]),
  target: z.string().default(""),
  modality: ModalityCodeSchema.default("SMALL_MOLECULE"),
  mechanism: z.string().nullable().optional(),
  indication: z.string().nullable().optional(),
  disease: z.string().nullable().optional(),
  cancer_subtype: z.string().nullable().optional(),
  biomarker: z.string().nullable().optional(),
  stage: DevelopmentStageSchema.default("Phase II"),
  owner: z.string().nullable().optional(),
  developer: z.string().nullable().optional(),
  sponsor: z.string().nullable().optional(),
  originator: z.string().nullable().optional(),

  // Identity and Relationships
  identity: AssetIdentitySchema.nullable().optional(),
  relationships: z.array(AssetRelationshipSchema).default([]),

  // Legacy & Relational Foreign Keys / Backwards Compatibility
  modality_id: z.string().uuid().nullable().optional(),
  modality_code: ModalityCodeSchema.default("SMALL_MOLECULE"),
  primary_target_id: z.string().uuid().nullable().optional(),
  primary_target_symbol: z.string().default(""),
  primary_moa_id: z.string().uuid().nullable().optional(),
  primary_moa_name: z.string().nullable().optional(),
  owner_company_id: z.string().uuid().nullable().optional(),
  owner_company_name: z.string().default(""),
  developer_company_id: z.string().uuid().nullable().optional(),
  developer_company_name: z.string().nullable().optional(),
  sponsor_id: z.string().uuid().nullable().optional(),
  current_development_stage: DevelopmentStageSchema.default("Phase II"),
  status_label: z.string().default("Investigational"),
  primary_indication_id: z.string().uuid().nullable().optional(),
  primary_indication_name: z.string().default(""),
  is_deprecated: z.boolean().default(false),
  merged_into_asset_id: z.string().uuid().nullable().optional(),
  attributes: z.record(z.string(), z.unknown()).default({}),
  created_at: z.string().datetime().optional(),
  updated_at: z.string().datetime().optional(),

  // Relational sub-collections
  development_codes: z.array(AssetDevelopmentCodeSchema).default([]),
  targets: z.array(TargetSchema).default([]),
  indications: z.array(IndicationSchema).default([]),
  trials: z.array(TrialSchema).default([]),
  publications: z.array(PublicationSchema).default([]),
  evidence: z.array(EvidenceSchema).default([]),
  outcomes: z.array(ClinicalOutcomeSchema).default([]),
  adverse_events: z.array(AdverseEventSchema).default([]),
  patient_populations: z.array(PopulationSchema).default([]),
  patents: z.array(PatentSchema).default([]),
  partnerships: z.array(PartnershipSchema).default([]),
  regulatory_events: z.array(RegulatoryEventSchema).default([]),
  ownership_transfers: z.array(AssetOwnershipTransferSchema).default([]),
});
export type Asset = z.infer<typeof AssetSchema>;

// ==============================================================================
// 18. Entity Resolution Types & Match Contracts
// ==============================================================================

export const ResolutionMatchTypeSchema = z.enum([
  "PRIMARY_NAME",
  "GENERIC_NAME",
  "DEVELOPMENT_CODE",
  "COMPANY_CODE",
  "FORMER_NAME",
  "ALIAS",
  "REGISTRY_ID",
  "NORMALIZED_TOKEN",
  "CONTEXTUAL_MATCH",
  "FUZZY",
  "AMBIGUOUS",
  "UNRESOLVED",
]);
export type ResolutionMatchType = z.infer<typeof ResolutionMatchTypeSchema>;

export const ResolutionMatchSchema = z.object({
  asset_id: z.string().uuid(),
  canonical_name: z.string(),
  matched_term: z.string(),
  match_type: ResolutionMatchTypeSchema,
  confidence: z.number().min(0).max(1),
  is_canonical: z.boolean().default(true),
  target: z.string().default(""),
  modality: z.string().default(""),
  owner: z.string().nullable().optional(),
  stage: z.string().nullable().optional(),
});
export type ResolutionMatch = z.infer<typeof ResolutionMatchSchema>;

export const ResolutionResultSchema = z.object({
  query: z.string(),
  resolved: z.boolean(),
  confidence: z.number().min(0).max(1).default(0),
  match_type: ResolutionMatchTypeSchema.default("UNRESOLVED"),
  match: ResolutionMatchSchema.nullable().optional(),
  candidates: z.array(ResolutionMatchSchema).default([]),
  disambiguation_notes: z.string().nullable().optional(),
});
export type ResolutionResult = z.infer<typeof ResolutionResultSchema>;
