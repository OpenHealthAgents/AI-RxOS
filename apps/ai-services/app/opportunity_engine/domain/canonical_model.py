"""Canonical Domain Model for AI Drug Opportunity Discovery Engine.

Defines rich, validated Pydantic v2 domain models for all 43 core entities,
supporting entity resolution across developmental aliases, multi-target biology,
clinical trial outcomes, intellectual property, and auditable decision governance.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ==============================================================================
# Enumerations
# ==============================================================================

class StrategicAction(StrEnum):
    PURSUE = "PURSUE"
    INVESTIGATE = "INVESTIGATE"
    PARTNER = "PARTNER"
    LICENSE = "LICENSE"
    MONITOR = "MONITOR"
    AVOID = "AVOID"


class DevelopmentStage(StrEnum):
    PRECLINICAL = "Preclinical"
    IND_ENABLING = "IND-enabling"
    PHASE_I = "Phase I"
    PHASE_IB = "Phase Ib"
    PHASE_II = "Phase II"
    PHASE_II_III = "Phase II/III"
    PHASE_III = "Phase III"
    REGULATORY_REVIEW = "Regulatory review"
    APPROVED = "Approved"
    WITHDRAWN = "Withdrawn"
    TERMINATED = "Terminated"
    DISCONTINUED = "Discontinued"


# Alias ClinicalStage to DevelopmentStage for full clinical terminology interchangeability
ClinicalStage = DevelopmentStage


class TrialPhase(StrEnum):
    PHASE_I = "Phase I"
    PHASE_IB = "Phase Ib"
    PHASE_II = "Phase II"
    PHASE_II_III = "Phase II/III"
    PHASE_III = "Phase III"
    PHASE_IV = "Phase IV"
    EARLY_PHASE_1 = "Early Phase 1"
    NOT_APPLICABLE = "Not Applicable"


class TrialLifecycleStatus(StrEnum):
    PHASE_I = "Phase I"
    PHASE_IB = "Phase Ib"
    PHASE_II = "Phase II"
    PHASE_II_III = "Phase II/III"
    PHASE_III = "Phase III"
    REGULATORY_REVIEW = "Regulatory review"
    APPROVED = "Approved"
    WITHDRAWN = "Withdrawn"
    TERMINATED = "Terminated"
    DISCONTINUED = "Discontinued"
    ACTIVE_NOT_RECRUITING = "Active, not recruiting"
    RECRUITING = "Recruiting"
    COMPLETED = "Completed"
    SUSPENDED = "Suspended"
    NOT_YET_RECRUITING = "Not yet recruiting"
    UNKNOWN = "Unknown"


class ModalityCode(StrEnum):
    SMALL_MOLECULE = "SMALL_MOLECULE"
    ANTIBODY = "ANTIBODY"
    ADC = "ADC"
    PROTEIN = "PROTEIN"
    PEPTIDE = "PEPTIDE"
    CELL_THERAPY = "CELL_THERAPY"
    GENE_THERAPY = "GENE_THERAPY"
    RNA_THERAPY = "RNA_THERAPY"
    RADIOPHARMACEUTICAL = "RADIOPHARMACEUTICAL"
    VACCINE = "VACCINE"
    OTHER = "OTHER"


class EvidencePolarity(StrEnum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    CONTRADICTORY = "CONTRADICTORY"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class ScientificEvidenceState(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    AI_INFERENCE = "ai_inference"
    VERIFIED_FACT = "verified_fact"


class AliasType(StrEnum):
    GENERIC_NAME = "generic_name"
    BRAND_NAME = "brand_name"
    FORMER_NAME = "former_name"
    CHEMICAL_NAME = "chemical_name"
    LABORATORY_CODE = "laboratory_code"
    COMPANY_CODE = "company_code"
    DEVELOPMENT_CODE = "development_code"
    SYNONYM = "synonym"


class RegulatoryAuthority(StrEnum):
    FDA = "FDA"
    EMA = "EMA"
    PMDA = "PMDA"
    NMPA = "NMPA"
    MHRA = "MHRA"
    HEALTH_CANADA = "Health_Canada"


class RegulatoryEventType(StrEnum):
    IND_CLEARED = "IND_cleared"
    ORPHAN_DESIGNATION = "orphan_designation"
    FAST_TRACK = "fast_track"
    BREAKTHROUGH_THERAPY = "breakthrough_therapy"
    PRIORITY_REVIEW = "priority_review"
    NDA_BLA_ACCEPTED = "NDA_BLA_accepted"
    APPROVAL = "approval"
    COMPLETE_RESPONSE_LETTER = "complete_response_letter"
    CLINICAL_HOLD = "clinical_hold"


class AuditEventType(StrEnum):
    ASSET_CREATED = "ASSET_CREATED"
    ALIAS_ATTACHED = "ALIAS_ATTACHED"
    DEV_CODE_ATTACHED = "DEV_CODE_ATTACHED"
    ASSET_MERGED = "ASSET_MERGED"
    DECISION_RATIFIED = "DECISION_RATIFIED"
    DECISION_OVERRIDDEN = "DECISION_OVERRIDDEN"
    EVIDENCE_INGESTED = "EVIDENCE_INGESTED"
    SCORE_RECALCULATED = "SCORE_RECALCULATED"


# ==============================================================================
# Helper Normalizer
# ==============================================================================

def normalize_key(value: str) -> str:
    """Normalize text keys, code names, and synonyms for robust resolution."""
    cleaned = unicodedata.normalize("NFKC", value).strip().upper()
    return re.sub(r"[\s\-_]+", "", cleaned)


# ==============================================================================
# 1. Organization & User
# ==============================================================================

class Organization(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    slug: str
    tier: str = "enterprise"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    organization_id: Optional[UUID] = None
    email: str
    full_name: str
    role: str = "researcher"
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 2. Company, Institution, Stakeholder Roles, and Ownership Tracking
# ==============================================================================

class DealType(StrEnum):
    ACQUISITION = "acquisition"
    ASSET_TRANSFER = "asset_transfer"
    LICENSE = "license"
    CO_DEVELOPMENT = "co_development"
    OPTION = "option"
    PARTNERSHIP = "partnership"
    TERMINATION = "termination"


class Company(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    normalized_name: str = ""
    ticker: Optional[str] = None
    country: Optional[str] = None
    headquarters: Optional[str] = None
    company_type: str = "pharma"  # pharma, biotech, specialty, academic, etc.
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("normalized_name", mode="before")
    @classmethod
    def set_normalized(cls, v: str, info: Any) -> str:
        if not v and "name" in info.data:
            return normalize_key(info.data["name"])
        return v or ""


class Institution(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    normalized_name: str = ""
    institution_type: str = "research_institute"  # research_institute, university, hospital, cancer_center
    city: Optional[str] = None
    country: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("normalized_name", mode="before")
    @classmethod
    def set_normalized(cls, v: str, info: Any) -> str:
        if not v and "name" in info.data:
            return normalize_key(info.data["name"])
        return v or ""


class Developer(BaseModel):
    """Clinical and preclinical drug developer entity."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    company_id: Optional[UUID] = None
    institution_id: Optional[UUID] = None
    role_description: str = "Lead Clinical Development"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Sponsor(BaseModel):
    """IND/CTA regulatory and trial sponsor entity."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    company_id: Optional[UUID] = None
    institution_id: Optional[UUID] = None
    sponsor_type: str = "industry"  # industry, academic, cooperative_group, government
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Owner(BaseModel):
    """Current or historical legal intellectual property and asset title owner."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    company_id: Optional[UUID] = None
    institution_id: Optional[UUID] = None
    ownership_type: str = "commercial_sponsor"  # commercial_sponsor, academic_inventor, holding_company
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Partner(BaseModel):
    """Strategic co-development, commercialization, or regional partner entity."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    company_id: Optional[UUID] = None
    institution_id: Optional[UUID] = None
    scope: str = "Co-Development & Commercialization"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Licensor(BaseModel):
    """Out-licensing rights holder entity granting asset rights."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    company_id: Optional[UUID] = None
    institution_id: Optional[UUID] = None
    jurisdiction: str = "Global"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Licensee(BaseModel):
    """In-licensing entity receiving development/commercial rights."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    company_id: Optional[UUID] = None
    institution_id: Optional[UUID] = None
    territory: str = "Global"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Acquirer(BaseModel):
    """Corporate or asset acquiring entity executing buyout or asset acquisition."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    company_id: Optional[UUID] = None
    acquisition_date: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AssetOwnershipTransfer(BaseModel):
    """Chronological ownership log and business transaction history tracking asset stewardship over time.

    Supports:
    - acquisition (e.g. Pfizer acquires Seagen -> Tucatinib ownership transferred)
    - asset transfer (e.g. Spectrum transfers Poziotinib)
    - license (e.g. Zymeworks out-licenses Zanidatamab to Jazz Pharmaceuticals)
    - co-development (e.g. BeiGene co-develops in Asia-Pacific)
    - option (e.g. Option agreement prior to license exercise)
    - partnership (e.g. Research alliance)
    - termination (e.g. Handback of rights or alliance dissolved)
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    deal_type: DealType
    effective_date: date
    end_date: Optional[date] = None

    # Counterparties
    from_entity_name: Optional[str] = None
    from_entity_id: Optional[UUID] = None
    to_entity_name: Optional[str] = None
    to_entity_id: Optional[UUID] = None

    # Specific roles in transaction
    licensor: Optional[str] = None
    licensee: Optional[str] = None
    partner: Optional[str] = None
    acquirer: Optional[str] = None

    # Deal Terms & Territorial Scope
    territory: str = "Global"
    scope: str = "Development and Commercialization Rights"
    is_exclusive: bool = True
    disclosed_upfront_usd: Optional[int] = None
    disclosed_milestones_usd: Optional[int] = None
    royalty_rate_pct: Optional[str] = None

    # Status & Provenance
    is_active: bool = True
    termination_reason: Optional[str] = None
    source_citation: str = ""
    source_url: Optional[str] = None
    is_verified: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 3. Target, Gene, Protein, Pathway
# ==============================================================================

class Pathway(BaseModel):
    """Biological signaling or metabolic pathway (e.g., RTK-MAPK, PI3K-AKT-mTOR, Estrogen Receptor Signaling, DNA Damage Repair)."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    identifier: Optional[str] = None  # e.g., KEGG:hsa04012, Reactome:R-HSA-1257604, GO:0007173
    category: str = "signal_transduction"
    description: Optional[str] = None
    gene_ids: List[UUID] = Field(default_factory=list)
    target_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Gene(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    hgnc_symbol: str
    hgnc_id: Optional[str] = None
    entrez_id: Optional[str] = None
    ensembl_id: Optional[str] = None
    full_name: str
    chromosome: Optional[str] = None
    pathway_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Protein(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    uniprot_id: str
    gene_id: Optional[UUID] = None
    protein_name: str
    sequence_length: Optional[int] = None
    molecular_weight: Optional[float] = None
    isoforms: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Target(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    symbol: str
    name: str
    gene_id: Optional[UUID] = None
    protein_id: Optional[UUID] = None
    pathway_ids: List[UUID] = Field(default_factory=list)
    target_class: str = "kinase"  # kinase, nuclear_receptor, gpcr, ion_channel, enzyme, surface_antigen, etc.
    validation_level: str = "clinically_validated"  # clinically_validated, preclinically_validated, exploratory
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 4. Disease, Indication, CancerSubtype
# ==============================================================================

class Disease(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    mesh_id: Optional[str] = None
    icd10_code: Optional[str] = None
    doid: Optional[str] = None
    category: str = "oncology"  # oncology, rare_disease, immunology, neurology, etc.
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Indication(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    disease_id: Optional[UUID] = None
    name: str
    setting: Optional[str] = "second_line"
    line_of_therapy: Optional[int] = 2
    prevalence_annual: Optional[int] = None
    subtype_ids: List[UUID] = Field(default_factory=list)
    biomarker_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CancerSubtype(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    disease_id: Optional[UUID] = None
    indication_id: Optional[UUID] = None
    name: str
    receptor_status: Optional[str] = None  # e.g., ER+/HER2-, HER2-amplified, KRAS-G12C+, Triple-Negative, etc.
    histology: Optional[str] = None
    frequency_percentage: Optional[float] = None
    biomarker_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 5. Biomarker & Mutation
# ==============================================================================

class Biomarker(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    target_id: Optional[UUID] = None
    gene_id: Optional[UUID] = None
    biomarker_type: str = "mutation"  # mutation, amplification, fusion, expression, loss, msi, tmb
    diagnostic_test_available: bool = True
    cdx_test_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Mutation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    biomarker_id: Optional[UUID] = None
    gene_id: Optional[UUID] = None
    target_id: Optional[UUID] = None
    protein_change: str  # e.g., 'Y537S', 'A775_G776insYVMA', 'G12D', 'T790M'
    exon: Optional[int] = None
    functional_consequence: str = "activating"  # activating, resistance_gatekeeper, loss_of_function, unknown
    resistance_mechanism_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 6. Modality & MechanismOfAction
# ==============================================================================

class Modality(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    code: ModalityCode = ModalityCode.SMALL_MOLECULE
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MechanismOfAction(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    target_id: Optional[UUID] = None
    pathway_id: Optional[UUID] = None
    name: str
    binding_type: str = "irreversible_covalent"  # irreversible_covalent, reversible_competitive, allosteric, degrader_protac, antagonist, agonist, etc.
    selectivity_profile: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 7. Asset Identification, Development Codes, Aliases
# ==============================================================================

class AssetDevelopmentCode(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID = Field(default_factory=uuid4)
    code: str
    normalized_code: str = ""
    originator_company_id: Optional[UUID] = None
    is_primary: bool = False
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("normalized_code", mode="before")
    @classmethod
    def set_normalized(cls, v: str, info: Any) -> str:
        if not v and "code" in info.data:
            return normalize_key(info.data["code"])
        return v or ""


class AssetAlias(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID = Field(default_factory=uuid4)
    alias: str
    normalized_alias: str = ""
    alias_type: AliasType = AliasType.SYNONYM
    is_primary_for_type: bool = False
    verification_state: str = "verified"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_context: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("normalized_alias", mode="before")
    @classmethod
    def set_normalized(cls, v: str, info: Any) -> str:
        if not v and "alias" in info.data:
            return normalize_key(info.data["alias"])
        return v or ""


class AssetIdentity(BaseModel):
    """Encapsulates the complete identity composite, synonyms, and resolution fingerprints for an asset."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    preferred_name: str
    generic_name: Optional[str] = None
    development_code: str = ""
    former_names: List[str] = Field(default_factory=list)
    company_codes: List[str] = Field(default_factory=list)
    aliases: List[AssetAlias] = Field(default_factory=list)
    registry_identifiers: Dict[str, str] = Field(default_factory=dict)
    normalized_tokens: List[str] = Field(default_factory=list)
    resolution_hash: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def compute_tokens_and_hash(self) -> AssetIdentity:
        tokens: Set[str] = set()
        if self.preferred_name:
            tokens.add(normalize_key(self.preferred_name))
        if self.generic_name:
            tokens.add(normalize_key(self.generic_name))
        if self.development_code:
            tokens.add(normalize_key(self.development_code))
        for fn in self.former_names:
            if fn:
                tokens.add(normalize_key(fn))
        for cc in self.company_codes:
            if cc:
                tokens.add(normalize_key(cc))
        for al in self.aliases:
            if al.alias:
                tokens.add(normalize_key(al.alias))
        for reg_val in self.registry_identifiers.values():
            if reg_val:
                tokens.add(normalize_key(reg_val))

        cleaned_tokens = sorted(list(tokens - {""}))
        self.normalized_tokens = cleaned_tokens
        if not self.resolution_hash:
            token_blob = "|".join(cleaned_tokens).encode("utf-8")
            self.resolution_hash = hashlib.sha256(token_blob).hexdigest()
        return self

    def matches(self, term: str) -> bool:
        """Check if any identity token exactly matches the normalized query."""
        norm_t = normalize_key(term)
        return bool(norm_t and norm_t in self.normalized_tokens)


class AssetRelationshipPredicate(StrEnum):
    TARGETS = "TARGETS"
    HAS_MODALITY = "HAS_MODALITY"
    ACTS_VIA_MECHANISM = "ACTS_VIA_MECHANISM"
    MODULATES_PATHWAY = "MODULATES_PATHWAY"
    INDICATED_FOR = "INDICATED_FOR"
    ASSOCIATED_WITH_DISEASE = "ASSOCIATED_WITH_DISEASE"
    SUBTYPE_CLASSIFIED = "SUBTYPE_CLASSIFIED"
    STRATIFIED_BY_BIOMARKER = "STRATIFIED_BY_BIOMARKER"
    ENROLLS_POPULATION = "ENROLLS_POPULATION"
    AT_DEVELOPMENT_STAGE = "AT_DEVELOPMENT_STAGE"
    OWNED_BY = "OWNED_BY"
    DEVELOPED_BY = "DEVELOPED_BY"
    SPONSORED_BY = "SPONSORED_BY"
    ORIGINATED_BY = "ORIGINATED_BY"
    COMBINED_WITH = "COMBINED_WITH"
    COMPETES_WITH = "COMPETES_WITH"
    HAS_RESISTANCE_MECHANISM = "HAS_RESISTANCE_MECHANISM"
    OVERCOMES_RESISTANCE = "OVERCOMES_RESISTANCE"


class DomainRelationshipPredicate(StrEnum):
    """Semantic graph ontology predicates connecting all biological and clinical entities."""
    # Gene / Protein / Target / Pathway
    ENCODES = "ENCODES"                          # Gene -> Protein
    TARGET_DERIVED_FROM = "TARGET_DERIVED_FROM"  # Target -> Gene / Protein
    PART_OF_PATHWAY = "PART_OF_PATHWAY"          # Target / Gene -> Pathway
    MODULATES_PATHWAY = "MODULATES_PATHWAY"      # MoA / Drug -> Pathway

    # Biomarker / Mutation / Resistance
    HARBORS_MUTATION = "HARBORS_MUTATION"        # Gene / Protein / Biomarker -> Mutation
    STRATIFIES = "STRATIFIES"                    # Biomarker -> Indication / Subtype / Population
    CONCURRENT_WITH = "CONCURRENT_WITH"          # Mutation -> Mutation / Biomarker
    CONFERS_RESISTANCE = "CONFERS_RESISTANCE"    # Mutation / Pathway -> ResistanceMechanism
    OVERCOMES_RESISTANCE = "OVERCOMES_RESISTANCE"# Combination / Asset -> ResistanceMechanism

    # Disease / Indication / Subtype / Patient Population
    HAS_INDICATION = "HAS_INDICATION"            # Disease -> Indication
    CLASSIFIED_AS_SUBTYPE = "CLASSIFIED_AS_SUBTYPE" # Indication / Disease -> CancerSubtype
    POPULATION_DEFINED_BY = "POPULATION_DEFINED_BY" # PatientPopulation -> Biomarker / Subtype
    TREATS = "TREATS"                            # Asset / Combination -> Indication

    # Mechanism / Modality / Combination
    ACTS_VIA_MECHANISM = "ACTS_VIA_MECHANISM"    # Asset -> MoA
    HAS_MODALITY = "HAS_MODALITY"                # Asset -> Modality
    SYNERGIZES_WITH = "SYNERGIZES_WITH"          # Combination -> Partner


class AssetRelationship(BaseModel):
    """Directional, typed semantic relationship linking an asset to its biological and business ecosystem."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    subject_asset_id: UUID
    predicate: AssetRelationshipPredicate
    object_entity_id: UUID = Field(default_factory=uuid4)
    object_entity_type: str = "target"
    object_entity_name: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    verification_state: str = "verified"
    attributes: Dict[str, Any] = Field(default_factory=dict)
    evidence_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DomainRelationship(BaseModel):
    """Universal directional edge connecting any two domain entities in the oncology knowledge graph."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    source_entity_id: UUID
    source_entity_type: str  # e.g., 'Target', 'Gene', 'Pathway', 'Disease', 'Biomarker', 'Mutation', 'ResistanceMechanism', 'Combination'
    predicate: DomainRelationshipPredicate
    target_entity_id: UUID
    target_entity_type: str  # e.g., 'Pathway', 'Protein', 'Indication', 'ResistanceMechanism'
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    verification_state: str = "verified"  # verified, inferred, hypothesis
    evidence_ids: List[UUID] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 8. Trial, Study, TrialArm, Intervention, Population, Endpoint, AdverseEvent, TrialStatusHistory
# ==============================================================================

class TrialArm(BaseModel):
    """Arm or cohort within a clinical study or trial."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    trial_id: Optional[UUID] = None
    arm_label: str
    arm_type: str = "experimental"  # experimental, active_comparator, placebo_comparator, sham_comparator, no_intervention, other
    description: Optional[str] = None
    cohort_size: Optional[int] = None
    intervention_names: List[str] = Field(default_factory=list)
    intervention_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Intervention(BaseModel):
    """Investigational or comparator agent administered in a clinical trial."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    trial_id: Optional[UUID] = None
    arm_id: Optional[UUID] = None
    asset_id: Optional[UUID] = None
    name: str
    intervention_type: str = "drug"  # drug, biological, dietary_supplement, combination_product, device, procedure, radiation, genetic, other
    description: Optional[str] = None
    dosage_form: Optional[str] = None
    dose_regimen: Optional[str] = None
    is_investigational: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Population(BaseModel):
    """Clinical trial patient population, cohort definition, and inclusion/exclusion criteria."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    trial_id: Optional[UUID] = None
    asset_id: Optional[UUID] = None
    population_name: str
    condition: Optional[str] = None
    disease_id: Optional[UUID] = None
    indication_id: Optional[UUID] = None
    cancer_subtype_id: Optional[UUID] = None
    cancer_subtype: Optional[str] = None
    biomarker_ids: List[UUID] = Field(default_factory=list)
    biomarker_criteria: List[str] = Field(default_factory=list)
    mutation_ids: List[UUID] = Field(default_factory=list)
    prior_lines: Optional[str] = None  # e.g., '1L', '2L+', 'endocrine_pretreated'
    line_of_therapy: Optional[str] = None
    cns_metastases_allowed: Optional[bool] = None
    cns_metastases_benefit: bool = True
    match_score: float = Field(default=80.0, ge=0.0, le=100.0)
    inclusion_criteria: List[str] = Field(default_factory=list)
    exclusion_criteria: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Endpoint(BaseModel):
    """Protocol-defined primary, secondary, or exploratory clinical trial endpoint."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    trial_id: Optional[UUID] = None
    endpoint_title: str
    endpoint_type: str = "primary"  # primary, secondary, exploratory, other
    metric: Optional[str] = None  # ORR, PFS, OS, DCR, DoR
    time_frame: Optional[str] = None
    description: Optional[str] = None
    is_met: Optional[bool] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AdverseEvent(BaseModel):
    """Documented adverse event, toxicity, or safety observation from a clinical trial or study."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    trial_id: Optional[UUID] = None
    arm_id: Optional[UUID] = None
    asset_id: Optional[UUID] = None
    term: str  # e.g., 'Diarrhea', 'Interstitial Lung Disease', 'Transaminase elevation'
    category: Optional[str] = None  # Gastrointestinal, Pulmonary, Hepatic, Hematologic
    grade: Optional[str] = "Grade 3+"  # All Grades, Grade 1-2, Grade 3, Grade 4, Grade 3+, Grade 5
    affected_count: Optional[int] = None
    total_evaluated: Optional[int] = None
    frequency_pct: Optional[float] = None
    is_serious: bool = False
    dose_limiting: bool = False
    treatment_emergent: bool = True
    source_citation: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TrialStatusHistory(BaseModel):
    """Temporal milestone status progression and lifecycle log for a clinical trial."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    trial_id: Optional[UUID] = None
    nct_id: str
    as_of_date: date
    overall_status: str
    normalized_stage: DevelopmentStage = DevelopmentStage.PHASE_II
    why_stopped: Optional[str] = None
    enrollment: Optional[int] = None
    results_posted: bool = False
    change_summary: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ClinicalOutcome(BaseModel):
    """Observed clinical efficacy result, response metric, or survival benchmark."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    trial_id: UUID
    asset_id: Optional[UUID] = None
    arm_id: Optional[UUID] = None
    endpoint_id: Optional[UUID] = None
    endpoint_name: str
    endpoint_type: str = "primary"
    cohort_description: Optional[str] = None
    metric: Optional[str] = None  # ORR, mPFS, mOS, DCR, DoR
    response_rate: Optional[float] = None
    median_months: Optional[float] = None
    hazard_ratio: Optional[float] = None
    confidence_interval: Optional[str] = None
    p_value: Optional[float] = None
    sample_size: Optional[int] = None
    is_statistically_significant: Optional[bool] = None
    observation_state: ScientificEvidenceState = ScientificEvidenceState.VERIFIED_FACT
    source_citation: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Trial(BaseModel):
    """Clinical trial registry record and clinical investigation entity."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    nct_id: str
    brief_title: str
    official_title: Optional[str] = None
    phase: str = "Phase 2"
    overall_status: str = "Active, not recruiting"
    normalized_stage: DevelopmentStage = DevelopmentStage.PHASE_II
    sponsor_id: Optional[UUID] = None
    sponsor_name: Optional[str] = None
    collaborators: List[str] = Field(default_factory=list)
    enrollment: Optional[int] = None
    start_date: Optional[date] = None
    primary_completion_date: Optional[date] = None
    completion_date: Optional[date] = None
    results_first_posted: Optional[date] = None
    study_type: str = "interventional"
    allocation: Optional[str] = None
    intervention_model: Optional[str] = None
    masking: Optional[str] = None
    primary_purpose: Optional[str] = None
    why_stopped: Optional[str] = None
    arms: List[TrialArm] = Field(default_factory=list)
    interventions: List[Intervention] = Field(default_factory=list)
    populations: List[Population] = Field(default_factory=list)
    endpoints: List[Endpoint] = Field(default_factory=list)
    outcomes: List[ClinicalOutcome] = Field(default_factory=list)
    adverse_events: List[AdverseEvent] = Field(default_factory=list)
    status_history: List[TrialStatusHistory] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Study(BaseModel):
    """Clinical study protocol and translational trial aggregate."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    trial_id: Optional[UUID] = None
    name: str
    study_code: Optional[str] = None
    study_type: str = "interventional_trial"
    lead_institution_id: Optional[UUID] = None
    lead_institution_name: Optional[str] = None
    protocol_id: Optional[str] = None
    phase: Optional[str] = None
    description: Optional[str] = None
    trials: List[Trial] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Publication(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    pmid: Optional[str] = None
    doi: Optional[str] = None
    pmcid: Optional[str] = None
    title: str
    journal: Optional[str] = None
    publication_year: int
    published_date: Optional[date] = None
    url: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    abstract: Optional[str] = None


# ==============================================================================
# 9. Evidence Architecture: Source, Extraction, Observation, Claim, Quality, Confidence, Temporal Scope
# ==============================================================================

class SourceType(StrEnum):
    PUBLICATION = "publication"
    CLINICAL_TRIAL = "clinical_trial"
    REGULATORY_SOURCE = "regulatory_source"
    PATENT = "patent"
    COMPANY_SOURCE = "company_source"
    CONFERENCE_ABSTRACT = "conference_abstract"
    SCIENTIFIC_DATABASE = "scientific_database"
    INSTITUTIONAL_SOURCE = "institutional_source"


class ProspectiveOrRetrospective(StrEnum):
    PROSPECTIVE = "prospective"
    RETROSPECTIVE = "retrospective"
    NOT_APPLICABLE = "not_applicable"


class ExtractionMethod(StrEnum):
    LLM_STRUCTURED_EXTRACTION = "llm_structured_extraction"
    REGEX_PIPELINE = "regex_pipeline"
    CURATED_EXPERT = "curated_expert"
    OCR_TABLE_PARSER = "ocr_table_parser"


class RiskOfBias(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNCLEAR = "unclear"


class QualityGrade(StrEnum):
    GRADE_A_HIGH = "GRADE_A_HIGH"
    GRADE_B_MODERATE = "GRADE_B_MODERATE"
    GRADE_C_LOW = "GRADE_C_LOW"
    GRADE_D_VERY_LOW = "GRADE_D_VERY_LOW"


class ConfidenceLevel(StrEnum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class ClaimType(StrEnum):
    EFFICACY = "efficacy"
    SELECTIVITY = "selectivity"
    SAFETY_TOLERABILITY = "safety_tolerability"
    CNS_PENETRATION = "cns_penetration"
    RESISTANCE_RISK = "resistance_risk"
    COMMERCIAL_FTO = "commercial_fto"


class EvidenceTemporalScope(BaseModel):
    """Temporal validity coordinates ensuring point-in-time anti-leakage compliance."""
    model_config = ConfigDict(from_attributes=True)
    valid_from: date
    valid_to: Optional[date] = None
    as_of_date: date
    is_current: bool = True
    cutoff_compliant: bool = True


class EvidenceQuality(BaseModel):
    """Systematic evidence appraisal based on modified GRADE principles and risk-of-bias."""
    model_config = ConfigDict(from_attributes=True)
    quality_score: float = Field(ge=0.0, le=100.0, default=85.0)
    methodological_rigor: float = Field(ge=0.0, le=100.0, default=85.0)
    risk_of_bias: RiskOfBias = RiskOfBias.LOW
    reproducibility_flag: bool = True
    quality_grade: QualityGrade = QualityGrade.GRADE_A_HIGH
    scoring_breakdown: Dict[str, float] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)


class EvidenceConfidence(BaseModel):
    """Calibrated statistical epistemic uncertainty and confidence interval bounds."""
    model_config = ConfigDict(from_attributes=True)
    score: float = Field(ge=0.0, le=1.0, default=0.90)
    confidence_interval_low: Optional[float] = None
    confidence_interval_high: Optional[float] = None
    confidence_level: ConfidenceLevel = ConfidenceLevel.HIGH
    epistemic_uncertainty: float = Field(ge=0.0, le=1.0, default=0.10)
    aleatoric_uncertainty: float = Field(ge=0.0, le=1.0, default=0.05)
    calibration_notes: Optional[str] = None


class EvidenceCitation(BaseModel):
    """Formatted academic and regulatory citation with stable persistent identifiers."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    formatted_citation: str
    short_citation: str
    doi: Optional[str] = None
    pmid: Optional[str] = None
    nct_id: Optional[str] = None
    patent_number: Optional[str] = None
    url: Optional[str] = None
    citation_style: str = "vancouver"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceSource(BaseModel):
    """
    Evidence source provenance capturing all 16 required attributes:
    source_type, source_id, title, authors, organization, publication_date,
    retrieval_date, study_type, phase, species, model, sample_size,
    peer_reviewed / peer_review_status, prospective_or_retrospective, quality, confidence.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    source_type: SourceType
    source_id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    organization: str
    publication_date: date
    retrieval_date: date
    url_reference: str = ""
    study_type: str = "interventional_trial"
    phase: Optional[str] = None
    species: Optional[str] = "Human"
    model: Optional[str] = None
    sample_size: Optional[int] = None
    peer_reviewed: bool = True
    peer_review_status: Optional[str] = None
    prospective_or_retrospective: ProspectiveOrRetrospective = ProspectiveOrRetrospective.NOT_APPLICABLE
    quality_score: float = Field(ge=0.0, le=100.0, default=85.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    temporal_validity: Optional[EvidenceTemporalScope] = None
    quality: Optional[EvidenceQuality] = None
    confidence_details: Optional[EvidenceConfidence] = None
    citation: Optional[EvidenceCitation] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceExtraction(BaseModel):
    """Exact raw passage anchor, coordinate location, and extraction method provenance."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    source_location: str
    extracted_text: str
    extraction_method: ExtractionMethod = ExtractionMethod.LLM_STRUCTURED_EXTRACTION
    extractor_model: Optional[str] = "DeepMind-BioExtractor-v2"
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    extracted_date: date = Field(default_factory=date.today)
    validation_status: str = "validated"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceObservation(BaseModel):
    """
    Normalized scientific observation anchored in verified evidence.
    CRITICAL RULE: Every observation must reference its evidence via evidence_id.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    evidence_id: UUID = Field(default_factory=uuid4)
    extraction_id: Optional[UUID] = None
    source_id: UUID = Field(default_factory=uuid4)
    source_ref: str = ""
    asset_id: UUID
    entity: str = ""
    parameter_name: str
    extracted_text_or_value: str = ""
    observed_value: str = ""
    normalized_value: float = 0.0
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    observation_date: date = Field(default_factory=date.today)
    source_location: str = ""
    statistical_significance: Optional[str] = None
    extraction_method: ExtractionMethod = ExtractionMethod.LLM_STRUCTURED_EXTRACTION
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    polarity: EvidencePolarity = EvidencePolarity.SUPPORTING
    observation_state: ScientificEvidenceState = ScientificEvidenceState.VERIFIED_FACT
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="before")
    @classmethod
    def sync_observation_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Ensure evidence_id and source_id are in sync
        if "evidence_id" not in data or data["evidence_id"] is None:
            if "source_id" in data and data["source_id"] is not None:
                data["evidence_id"] = data["source_id"]
            else:
                data["evidence_id"] = uuid4()
        if "source_id" not in data or data["source_id"] is None:
            data["source_id"] = data["evidence_id"]

        # Ensure extracted_text_or_value and observed_value are in sync
        if "observed_value" in data and ("extracted_text_or_value" not in data or not data["extracted_text_or_value"]):
            data["extracted_text_or_value"] = str(data["observed_value"])
        elif "extracted_text_or_value" in data and ("observed_value" not in data or not data["observed_value"]):
            data["observed_value"] = str(data["extracted_text_or_value"])

        # Ensure numeric_value and normalized_value are in sync
        if "numeric_value" in data and data["numeric_value"] is not None and "normalized_value" not in data:
            data["normalized_value"] = float(data["numeric_value"])
        elif "normalized_value" in data and data["normalized_value"] is not None and "numeric_value" not in data:
            data["numeric_value"] = float(data["normalized_value"])

        return data


class EvidenceClaim(BaseModel):
    """Synthesized scientific statement or hypothesis backed by supporting and contradicting observations."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    claim_text: str
    claim_type: ClaimType = ClaimType.EFFICACY
    polarity: EvidencePolarity = EvidencePolarity.SUPPORTING
    epistemic_status: ScientificEvidenceState = ScientificEvidenceState.VERIFIED_FACT
    supporting_observation_ids: List[UUID] = Field(default_factory=list)
    contradicting_observation_ids: List[UUID] = Field(default_factory=list)
    synthesis_confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Evidence(BaseModel):
    """
    Aggregate Evidence record encapsulating source provenance, quality,
    citations, extractions, observations, and claims.
    Captures all 16 evidence requirements:
    source_type, source_id, title, authors, organization, publication_date,
    retrieval_date, study_type, phase, species, model, sample_size,
    peer_reviewed / peer_review_status, prospective_or_retrospective,
    quality, confidence.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    source_type: SourceType = SourceType.PUBLICATION
    source_id: str = ""
    title: str = ""
    authors: List[str] = Field(default_factory=list)
    organization: str = ""
    publication_date: Optional[date] = None
    retrieval_date: Optional[date] = None
    url_reference: str = ""
    study_type: str = "interventional_trial"
    phase: Optional[str] = None
    species: Optional[str] = "Human"
    model: Optional[str] = None
    sample_size: Optional[int] = None
    peer_reviewed: bool = True
    peer_review_status: Optional[str] = None
    prospective_or_retrospective: ProspectiveOrRetrospective = ProspectiveOrRetrospective.NOT_APPLICABLE
    quality_score: float = Field(ge=0.0, le=100.0, default=85.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    temporal_validity: Optional[EvidenceTemporalScope] = None
    quality: Optional[EvidenceQuality] = None
    confidence_details: Optional[EvidenceConfidence] = None
    citation: Optional[EvidenceCitation] = None
    extractions: List[EvidenceExtraction] = Field(default_factory=list)
    observations: List[EvidenceObservation] = Field(default_factory=list)
    claims: List[EvidenceClaim] = Field(default_factory=list)

    # Legacy & relational foreign keys for backwards compatibility
    publication_id: Optional[UUID] = None
    trial_id: Optional[UUID] = None
    evidence_type: str = "literature"
    source_ref: str = ""
    publication_year: int = 2024
    as_of_date: Optional[date] = None
    polarity: EvidencePolarity = EvidencePolarity.SUPPORTING
    is_verified: bool = True
    excerpt: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="before")
    @classmethod
    def sync_evidence_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "publication_date" in data and data["publication_date"] is not None:
            pub_date = data["publication_date"]
            if hasattr(pub_date, "year"):
                data.setdefault("publication_year", pub_date.year)
                data.setdefault("as_of_date", pub_date)
        elif "as_of_date" in data and data["as_of_date"] is not None:
            data.setdefault("publication_date", data["as_of_date"])
            if hasattr(data["as_of_date"], "year"):
                data.setdefault("publication_year", data["as_of_date"].year)
        if "title" in data and data["title"] and not data.get("excerpt"):
            data["excerpt"] = data["title"]
        elif "excerpt" in data and data["excerpt"] and not data.get("title"):
            data["title"] = data["excerpt"]
        if "source_id" in data and data["source_id"] and not data.get("source_ref"):
            data["source_ref"] = data["source_id"]
        elif "source_ref" in data and data["source_ref"] and not data.get("source_id"):
            data["source_id"] = data["source_ref"]
        if "peer_review_status" in data and data["peer_review_status"]:
            data.setdefault("peer_reviewed", data["peer_review_status"] == "peer_reviewed")
        elif "peer_reviewed" in data:
            data.setdefault("peer_review_status", "peer_reviewed" if data["peer_reviewed"] else "not_peer_reviewed")
        if "citation" in data and isinstance(data["citation"], str):
            citation_str = data["citation"]
            data["citation"] = {
                "source_id": data.get("id") or uuid4(),
                "formatted_citation": citation_str,
                "short_citation": citation_str[:50],
            }
        return data


# ==============================================================================
# 10. PreclinicalResult
# ==============================================================================


class PreclinicalResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    assay_type: str = "biochemical_kinase"
    target_id: Optional[UUID] = None
    cell_line: Optional[str] = None
    ic50_nm: Optional[float] = None
    ec50_nm: Optional[float] = None
    tumor_growth_inhibition_pct: Optional[float] = None
    is_wt_sparing: Optional[bool] = None


# ==============================================================================
# 11. SafetyObservation & CNSObservation
# ==============================================================================

class SafetyObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    adverse_event_name: str
    grade_all_rate: Optional[float] = None
    grade_3_plus_rate: Optional[float] = None
    dose_limiting_toxicity: bool = False
    discontinuation_rate: Optional[float] = None
    therapeutic_index_rating: Optional[str] = "favorable"


class CNSObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    brain_to_plasma_ratio: Optional[float] = None
    csf_penetration_verified: bool = False
    intracranial_orr: Optional[float] = None
    intracranial_pfs_months: Optional[float] = None
    leptomeningeal_activity: bool = False
    cns_score: int = Field(default=50, ge=0, le=100)


# ==============================================================================
# 12. PatientPopulation, ResistanceMechanism, Combination
# ==============================================================================

class PatientPopulation(Population):
    """Subclass of Population for indication/biomarker disease-level patient cohorts."""
    pass


class ResistanceMechanism(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: Optional[UUID] = None
    target_id: Optional[UUID] = None
    gene_id: Optional[UUID] = None
    mutation_id: Optional[UUID] = None
    pathway_id: Optional[UUID] = None
    name: str  # e.g., 'ESR1 Y537S gatekeeper mutation', 'HER2 T798I gatekeeper', 'PI3K pathway activation', 'MET amplification'
    impact_level: str = "High"  # High, Moderate, Low
    is_predicted: bool = False
    mechanism_type: str = "on_target_mutation"  # on_target_mutation, bypass_pathway, histological_transformation, efflux_pump, target_loss
    mechanism_description: str
    counteracting_combination_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Combination(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    primary_asset_id: Optional[UUID] = None
    partner_name: str
    partner_asset_id: Optional[UUID] = None
    target_ids: List[UUID] = Field(default_factory=list)
    pathway_ids: List[UUID] = Field(default_factory=list)
    synergy_type: str  # e.g., 'Endocrine + CDK4/6 synergy', 'Dual HER2 block', 'Vertical pathway inhibition', 'Synthetic lethality'
    rationale: str
    clinical_status: str  # e.g., 'Phase 1b', 'Phase 3', 'Standard of Care', 'Preclinical'
    addressed_resistance_mechanism_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 13. Patent, LicenseEvent, Partnership, RegulatoryEvent
# ==============================================================================

class Patent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    patent_number: str
    title: str
    assignee_company_id: Optional[UUID] = None
    priority_date: Optional[date] = None
    filing_date: Optional[date] = None
    grant_date: Optional[date] = None
    expiration_date: Optional[date] = None
    status: str = "granted"


class LicenseEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    licensor_company_id: UUID
    licensee_company_id: UUID
    event_type: str = "exclusive_license"
    territory: str = "Global"
    effective_date: date
    disclosed_upfront_usd: Optional[int] = None
    disclosed_milestones_usd: Optional[int] = None


class Partnership(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    partner_company_id: UUID
    scope: str
    start_date: date
    status: str = "active"


class RegulatoryEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    authority: RegulatoryAuthority = RegulatoryAuthority.FDA
    event_type: RegulatoryEventType = RegulatoryEventType.FAST_TRACK
    indication_id: Optional[UUID] = None
    event_date: date
    dossier_notes: Optional[str] = None


# ==============================================================================
# 14. CommercialObservation & CompetitiveAsset
# ==============================================================================

class CommercialObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    estimated_peak_sales_usd: Optional[int] = None
    addressable_market_usd: Optional[int] = None
    target_patient_annual_count: Optional[int] = None
    pricing_strategy: Optional[str] = None
    market_exclusivity_expiry: Optional[date] = None


class CompetitiveAsset(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    target_asset_id: UUID
    competitor_asset_id: UUID
    competitive_relationship: str = "direct_benchmark"
    differentiating_advantage: str


# ==============================================================================
# 15. Decision, Recommendation, Score, ScoreComponent, Prediction
# ==============================================================================

class Decision(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    organization_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    action: StrategicAction = StrategicAction.PURSUE
    is_human_override: bool = False
    ai_suggested_action: StrategicAction = StrategicAction.PURSUE
    clinical_justification: str
    decision_timestamp: datetime = Field(default_factory=datetime.utcnow)
    checklist: Dict[str, bool] = Field(default_factory=dict)


class Recommendation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    action: StrategicAction = StrategicAction.PURSUE
    confidence: float = Field(ge=0.0, le=100.0)
    rationale: str
    badge_text: str
    model_version: str = "Model v0.1"


class ScoreComponent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    score_id: UUID
    component_name: str
    weight: float
    raw_value: float
    weighted_value: float


class Score(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    score_type: str = "development_potential"
    numeric_score: float = Field(ge=0.0, le=100.0)
    confidence_interval_low: Optional[float] = None
    confidence_interval_high: Optional[float] = None
    model_lineage: str = "Calibrated Multi-Attribute Engine"
    components: List[ScoreComponent] = Field(default_factory=list)


class Prediction(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    transition_stage: str
    predicted_probability: float = Field(ge=0.0, le=1.0)
    model_version: str = "Model v0.1"
    calibration_data: Optional[str] = None


# ==============================================================================
# 16. BacktestSnapshot & AuditEvent
# ==============================================================================

class BacktestSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    cutoff_date: date
    predicted_action: StrategicAction
    predicted_dps: float
    eligible_evidence_count: int
    suppressed_future_evidence_count: int
    ground_truth_outcome: str
    prediction_accuracy: str
    anti_leakage_audit_passed: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AuditEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    event_type: AuditEventType
    entity_id: UUID
    entity_type: str
    actor_id: Optional[UUID] = None
    actor_name: str
    summary: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 17. Core Asset Aggregate
# ==============================================================================

class Asset(BaseModel):
    """Core Canonical Asset aggregate maintaining complete multi-dimensional lifecycle data."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    preferred_name: str
    canonical_slug: str = ""

    # 17 Core Canonical Domain Properties
    development_code: str = ""
    generic_name: Optional[str] = None
    former_names: List[str] = Field(default_factory=list)
    aliases: List[AssetAlias] = Field(default_factory=list)
    company_codes: List[str] = Field(default_factory=list)
    target: str = ""
    modality: ModalityCode = ModalityCode.SMALL_MOLECULE
    mechanism: Optional[str] = None
    indication: Optional[str] = None
    disease: Optional[str] = None
    cancer_subtype: Optional[str] = None
    biomarker: Optional[str] = None
    stage: DevelopmentStage = DevelopmentStage.PHASE_II
    owner: Optional[str] = None
    developer: Optional[str] = None
    sponsor: Optional[str] = None
    originator: Optional[str] = None

    # Identity Set and Relationship Graph
    identity: Optional[AssetIdentity] = None
    relationships: List[AssetRelationship] = Field(default_factory=list)

    # Legacy & Relational Foreign Keys / Backwards Compatibility
    modality_id: Optional[UUID] = None
    modality_code: ModalityCode = ModalityCode.SMALL_MOLECULE
    primary_target_id: Optional[UUID] = None
    primary_target_symbol: str = ""
    primary_moa_id: Optional[UUID] = None
    primary_moa_name: Optional[str] = None

    owner_company_id: Optional[UUID] = None
    owner_company_name: str = ""
    developer_company_id: Optional[UUID] = None
    developer_company_name: Optional[str] = None
    sponsor_id: Optional[UUID] = None

    current_development_stage: DevelopmentStage = DevelopmentStage.PHASE_II
    status_label: str = "Investigational"
    primary_indication_id: Optional[UUID] = None
    primary_indication_name: str = ""

    is_deprecated: bool = False
    merged_into_asset_id: Optional[UUID] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relational sub-collections supported directly on Asset aggregate
    development_codes: List[AssetDevelopmentCode] = Field(default_factory=list)
    targets: List[Target] = Field(default_factory=list)
    indications: List[Indication] = Field(default_factory=list)
    trials: List[Trial] = Field(default_factory=list)
    publications: List[Publication] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    outcomes: List[ClinicalOutcome] = Field(default_factory=list)
    adverse_events: List[AdverseEvent] = Field(default_factory=list)
    patient_populations: List[Population] = Field(default_factory=list)
    patents: List[Patent] = Field(default_factory=list)
    partnerships: List[Partnership] = Field(default_factory=list)
    regulatory_events: List[RegulatoryEvent] = Field(default_factory=list)
    ownership_transfers: List[AssetOwnershipTransfer] = Field(default_factory=list)

    @field_validator("canonical_slug", mode="before")
    @classmethod
    def set_canonical_slug(cls, v: str, info: Any) -> str:
        if not v and "preferred_name" in info.data:
            return re.sub(r"[^a-z0-9]+", "-", info.data["preferred_name"].lower()).strip("-")
        return v or ""

    @model_validator(mode="before")
    @classmethod
    def sync_canonical_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Target synchronization
        if "target" in data and "primary_target_symbol" not in data:
            data["primary_target_symbol"] = data["target"]
        elif "primary_target_symbol" in data and "target" not in data:
            data["target"] = data["primary_target_symbol"]

        # Modality synchronization
        if "modality" in data and "modality_code" not in data:
            data["modality_code"] = data["modality"]
        elif "modality_code" in data and "modality" not in data:
            data["modality"] = data["modality_code"]

        # Stage synchronization
        if "stage" in data and "current_development_stage" not in data:
            data["current_development_stage"] = data["stage"]
        elif "current_development_stage" in data and "stage" not in data:
            data["stage"] = data["current_development_stage"]

        # Owner synchronization
        if "owner" in data and "owner_company_name" not in data:
            data["owner_company_name"] = data["owner"] or ""
        elif "owner_company_name" in data and "owner" not in data:
            data["owner"] = data["owner_company_name"]

        # Developer synchronization
        if "developer" in data and "developer_company_name" not in data:
            data["developer_company_name"] = data["developer"]
        elif "developer_company_name" in data and "developer" not in data:
            data["developer"] = data["developer_company_name"]

        # Indication synchronization
        if "indication" in data and "primary_indication_name" not in data:
            data["primary_indication_name"] = data["indication"] or ""
        elif "primary_indication_name" in data and "indication" not in data:
            data["indication"] = data["primary_indication_name"]

        # Mechanism synchronization
        if "mechanism" in data and "primary_moa_name" not in data:
            data["primary_moa_name"] = data["mechanism"]
        elif "primary_moa_name" in data and "mechanism" not in data:
            data["mechanism"] = data["primary_moa_name"]

        return data

    @model_validator(mode="after")
    def populate_identity_and_relationships(self) -> Asset:
        # 1. Sync development_code
        if self.development_code:
            existing_codes = {normalize_key(dc.code) for dc in self.development_codes}
            if normalize_key(self.development_code) not in existing_codes:
                self.development_codes.insert(
                    0,
                    AssetDevelopmentCode(
                        asset_id=self.id,
                        code=self.development_code,
                        is_primary=True,
                    ),
                )
        elif self.development_codes:
            self.development_code = self.development_codes[0].code

        # 2. Sync generic_name into aliases
        if self.generic_name:
            existing_aliases = {normalize_key(a.alias) for a in self.aliases}
            if normalize_key(self.generic_name) not in existing_aliases:
                self.aliases.append(
                    AssetAlias(
                        asset_id=self.id,
                        alias=self.generic_name,
                        alias_type=AliasType.GENERIC_NAME,
                        is_primary_for_type=True,
                    )
                )

        # 3. Sync former_names into aliases
        for fn in self.former_names:
            if fn:
                existing_aliases = {normalize_key(a.alias) for a in self.aliases}
                if normalize_key(fn) not in existing_aliases:
                    self.aliases.append(
                        AssetAlias(
                            asset_id=self.id,
                            alias=fn,
                            alias_type=AliasType.FORMER_NAME,
                        )
                    )

        # 4. Sync company_codes into aliases
        for cc in self.company_codes:
            if cc:
                existing_aliases = {normalize_key(a.alias) for a in self.aliases}
                if normalize_key(cc) not in existing_aliases:
                    self.aliases.append(
                        AssetAlias(
                            asset_id=self.id,
                            alias=cc,
                            alias_type=AliasType.COMPANY_CODE,
                            confidence=0.98,
                        )
                    )

        # 5. Build identity if not provided
        if self.identity is None:
            self.identity = AssetIdentity(
                asset_id=self.id,
                preferred_name=self.preferred_name,
                generic_name=self.generic_name,
                development_code=self.development_code,
                former_names=list(self.former_names),
                company_codes=list(self.company_codes),
                aliases=list(self.aliases),
            )

        # 6. Auto-construct default semantic relationships if empty
        if not self.relationships:
            self.build_default_relationships()

        return self

    def build_default_relationships(self) -> List[AssetRelationship]:
        """Constructs directional semantic relationship edges for the asset."""
        rels: List[AssetRelationship] = []

        if self.target:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.TARGETS,
                    object_entity_type="target",
                    object_entity_name=self.target,
                )
            )

        if self.modality:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.HAS_MODALITY,
                    object_entity_type="modality",
                    object_entity_name=str(self.modality.value),
                )
            )

        if self.mechanism:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.ACTS_VIA_MECHANISM,
                    object_entity_type="mechanism",
                    object_entity_name=self.mechanism,
                )
            )

        if self.indication:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.INDICATED_FOR,
                    object_entity_type="indication",
                    object_entity_name=self.indication,
                )
            )

        if self.disease:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.ASSOCIATED_WITH_DISEASE,
                    object_entity_type="disease",
                    object_entity_name=self.disease,
                )
            )

        if self.cancer_subtype:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.SUBTYPE_CLASSIFIED,
                    object_entity_type="cancer_subtype",
                    object_entity_name=self.cancer_subtype,
                )
            )

        if self.biomarker:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.STRATIFIED_BY_BIOMARKER,
                    object_entity_type="biomarker",
                    object_entity_name=self.biomarker,
                )
            )

        if self.stage:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.AT_DEVELOPMENT_STAGE,
                    object_entity_type="stage",
                    object_entity_name=str(self.stage.value),
                )
            )

        if self.owner:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.OWNED_BY,
                    object_entity_type="company",
                    object_entity_name=self.owner,
                )
            )

        if self.developer:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.DEVELOPED_BY,
                    object_entity_type="company",
                    object_entity_name=self.developer,
                )
            )

        if self.sponsor:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.SPONSORED_BY,
                    object_entity_type="company",
                    object_entity_name=self.sponsor,
                )
            )

        if self.originator:
            rels.append(
                AssetRelationship(
                    subject_asset_id=self.id,
                    predicate=AssetRelationshipPredicate.ORIGINATED_BY,
                    object_entity_type="company",
                    object_entity_name=self.originator,
                )
            )

        self.relationships = rels
        return rels

    def get_all_identifiers(self) -> List[str]:
        """Returns all recognized names, codes, former names, and aliases normalized for resolution."""
        identifiers = {normalize_key(self.preferred_name)}
        if self.generic_name:
            identifiers.add(normalize_key(self.generic_name))
        if self.development_code:
            identifiers.add(normalize_key(self.development_code))
        for dev in self.development_codes:
            if dev.code:
                identifiers.add(normalize_key(dev.code))
        for fn in self.former_names:
            if fn:
                identifiers.add(normalize_key(fn))
        for cc in self.company_codes:
            if cc:
                identifiers.add(normalize_key(cc))
        for alias in self.aliases:
            if alias.alias:
                identifiers.add(normalize_key(alias.alias))
        if self.identity:
            for token in self.identity.normalized_tokens:
                identifiers.add(token)
        return list(identifiers - {""})

    def has_code_or_alias(self, query: str) -> bool:
        """Check if asset matches a given raw string query under normalization."""
        norm_q = normalize_key(query)
        return bool(norm_q and norm_q in self.get_all_identifiers())
