from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class EntityType(StrEnum):
    THERAPEUTIC_ASSET = "therapeutic_asset"
    TARGET = "target"
    DISEASE = "disease"
    INDICATION = "indication"
    BIOMARKER = "biomarker"
    COMPANY = "company"
    CLINICAL_TRIAL = "clinical_trial"
    PUBLICATION = "publication"
    PATENT = "patent"
    PATENT_FAMILY = "patent_family"
    LICENSING_EVENT = "licensing_event"
    REGULATORY_EVENT = "regulatory_event"
    MECHANISM = "mechanism"
    COMBINATION = "combination"
    RESISTANCE_MECHANISM = "resistance_mechanism"


class Modality(StrEnum):
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


class Visibility(StrEnum):
    GLOBAL = "global"
    TENANT = "tenant"


class SourceType(StrEnum):
    PUBLICATION = "publication"
    TRIAL_REGISTRY = "trial_registry"
    PATENT_REGISTRY = "patent_registry"
    REGULATORY_AUTHORITY = "regulatory_authority"
    COMPANY = "company"
    DATABASE = "database"
    MANUAL = "manual"
    DEMO = "demo"


class VerificationState(StrEnum):
    UNREVIEWED = "unreviewed"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ObservationKind(StrEnum):
    SOURCE_FACT = "source_fact"
    NORMALIZED_OBSERVATION = "normalized_observation"
    HYPOTHESIS = "hypothesis"


class ClaimType(StrEnum):
    SOURCE_FACT = "source_fact"
    DERIVED_CLAIM = "derived_claim"
    INFERENCE = "inference"
    PREDICTION = "prediction"


class EvidenceRelationType(StrEnum):
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    CONTEXT = "context"
    DERIVED = "derived"


class RegulatoryEventType(StrEnum):
    APPROVAL = "approval"
    TENTATIVE_APPROVAL = "tentative_approval"
    COMPLETE_RESPONSE = "complete_response"
    REGULATORY_SUBMISSION = "regulatory_submission"


class LicensingEventType(StrEnum):
    LICENSE_GRANTED = "license_granted"
    LICENSE_AMENDED = "license_amended"
    LICENSE_TERMINATED = "license_terminated"
    OPTION_GRANTED = "option_granted"
    OPTION_EXERCISED = "option_exercised"
    COLLABORATION = "collaboration"
    ASSIGNMENT = "assignment"
    OTHER = "other"


class ExclusivityState(StrEnum):
    EXCLUSIVE = "exclusive"
    NON_EXCLUSIVE = "non_exclusive"
    UNKNOWN = "unknown"


class IPReferenceRole(StrEnum):
    LICENSOR = "licensor"
    LICENSEE = "licensee"
    ASSIGNOR = "assignor"
    ASSIGNEE = "assignee"
    ASSET = "asset"
    PATENT = "patent"


class BiomarkerType(StrEnum):
    GENOMIC = "genomic"
    PROTEIN = "protein"
    EXPRESSION = "expression"
    CLINICAL = "clinical"
    IMAGING = "imaging"
    OTHER = "other"


class BiomarkerAlteration(StrEnum):
    MUTATION = "mutation"
    EXPRESSION = "expression"
    AMPLIFICATION = "amplification"
    DELETION = "deletion"
    FUSION = "fusion"
    METHYLATION = "methylation"
    PROTEIN_ABUNDANCE = "protein_abundance"
    CLINICAL = "clinical"
    OTHER = "other"


class ExtensibleAttributes(BaseModel):
    model_config = ConfigDict(extra="allow")


class AssetAttributes(ExtensibleAttributes):
    development_names: list[str] = Field(default_factory=list)
    mechanism_of_action: str | None = None
    development_status: str | None = None


class TargetAttributes(ExtensibleAttributes):
    gene_symbol: str | None = None
    protein_name: str | None = None
    target_class: str | None = None
    biological_role: str | None = None


class DiseaseAttributes(ExtensibleAttributes):
    ontology_ids: list[str] = Field(default_factory=list)
    cancer_subtype: str | None = None
    disease_context: str | None = None


class IndicationAttributes(ExtensibleAttributes):
    disease_entity_id: UUID | None = None
    disease_context: str | None = None


class BiomarkerAttributes(ExtensibleAttributes):
    biomarker_type: BiomarkerType = BiomarkerType.OTHER
    alteration_types: list[BiomarkerAlteration] = Field(default_factory=list)
    target_entity_id: UUID | None = None
    disease_context: str | None = None


class CompanyAttributes(ExtensibleAttributes):
    legal_name: str | None = None
    company_type: str | None = None


class TrialAttributes(ExtensibleAttributes):
    title: str | None = None
    phase: str | None = None
    study_type: str | None = None
    status: str | None = None
    sponsor: str | None = None
    collaborators: list[str] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    patient_population: str | None = None
    enrollment: int | None = Field(default=None, ge=0)
    start_date: date | None = None
    completion_date: date | None = None
    last_updated: datetime | None = None


class PublicationAttributes(ExtensibleAttributes):
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    journal: str | None = None
    publication_date: date | None = None
    article_type: str | None = None


class PatentAttributes(ExtensibleAttributes):
    jurisdiction: str | None = None
    filing_date: date | None = None
    publication_date: date | None = None
    applicant: str | None = None
    inventors: list[str] = Field(default_factory=list)
    status: str | None = None


class PatentFamilyAttributes(ExtensibleAttributes):
    family_identifier: str | None = None
    jurisdictions: list[str] = Field(default_factory=list)
    member_count: int | None = Field(default=None, ge=0)


class LicensingEventAttributes(ExtensibleAttributes):
    event_type: LicensingEventType
    event_date_source: str | None = None
    effective_date_source: str | None = None
    expiration_date_source: str | None = None
    licensor_names: list[str] = Field(default_factory=list)
    licensee_names: list[str] = Field(default_factory=list)
    asset_names: list[str] = Field(default_factory=list)
    patent_identifiers: list[str] = Field(default_factory=list)
    territory: list[str] = Field(default_factory=list)
    exclusivity: ExclusivityState = ExclusivityState.UNKNOWN
    field_of_use: str | None = None
    rights_scope: str | None = None


class RegulatoryEventAttributes(ExtensibleAttributes):
    authority: str | None = None
    submission: str | None = None
    decision: str | None = None
    jurisdiction: str | None = None
    event_date: date | None = None


class MechanismAttributes(ExtensibleAttributes):
    mechanism_type: str | None = None
    description: str | None = None
    pathways: list[str] = Field(default_factory=list)


class CombinationAttributes(ExtensibleAttributes):
    disease_context: str | None = None
    indication_context: str | None = None
    study_context: str | None = None


class ResistanceAttributes(ExtensibleAttributes):
    resistance_status: str | None = None
    mechanism_type: str | None = None
    description: str | None = None


ENTITY_ATTRIBUTE_MODELS: dict[EntityType, type[ExtensibleAttributes]] = {
    EntityType.THERAPEUTIC_ASSET: AssetAttributes,
    EntityType.TARGET: TargetAttributes,
    EntityType.DISEASE: DiseaseAttributes,
    EntityType.INDICATION: IndicationAttributes,
    EntityType.BIOMARKER: BiomarkerAttributes,
    EntityType.COMPANY: CompanyAttributes,
    EntityType.CLINICAL_TRIAL: TrialAttributes,
    EntityType.PUBLICATION: PublicationAttributes,
    EntityType.PATENT: PatentAttributes,
    EntityType.PATENT_FAMILY: PatentFamilyAttributes,
    EntityType.LICENSING_EVENT: LicensingEventAttributes,
    EntityType.REGULATORY_EVENT: RegulatoryEventAttributes,
    EntityType.MECHANISM: MechanismAttributes,
    EntityType.COMBINATION: CombinationAttributes,
    EntityType.RESISTANCE_MECHANISM: ResistanceAttributes,
}


class SourceRecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str = Field(min_length=1, max_length=120)
    external_id: str = Field(min_length=1, max_length=500)
    source_type: SourceType | str
    source_url: str | HttpUrl | None = None
    published_at: AwareDatetime | None = None
    source_updated_at: AwareDatetime | None = None
    observed_at: AwareDatetime | None = None
    raw_payload_ref: str | None = Field(default=None, max_length=2000)
    content_hash: str | None = Field(default=None, max_length=256)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_type", mode="before")
    @classmethod
    def coerce_source_type(cls, value: SourceType | str) -> SourceType:
        if isinstance(value, SourceType):
            return value
        try:
            return SourceType(value)
        except ValueError as exc:
            raise ValueError(f"unsupported source_type: {value!r}") from exc

    @field_validator("source_url", mode="before")
    @classmethod
    def coerce_source_url(cls, value: str | HttpUrl | None) -> HttpUrl | None:
        if value is None or value == "":
            return None
        return HttpUrl(value)


class PubMedArticleIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pmid: str = Field(pattern=r"^\d+$", min_length=1, max_length=32)
    pmcid: str | None = Field(default=None, max_length=40)
    doi: str | None = Field(default=None, max_length=256)
    title: str = Field(min_length=1, max_length=5000)
    abstract: str | None = None
    authors: list[dict[str, Any]] = Field(default_factory=list)
    journal: str | None = Field(default=None, max_length=1000)
    publication_date_source: str | None = Field(default=None, max_length=200)
    retrieved_at: AwareDatetime
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    extracted_entities: list[dict[str, Any]] = Field(default_factory=list)
    extracted_relationships: list[dict[str, Any]] = Field(default_factory=list)
    query: str = Field(min_length=1, max_length=2000)


class ClinicalTrialIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nct_id: str = Field(min_length=11, max_length=11)
    title: str = Field(min_length=1, max_length=5000)
    abstract: str | None = None
    study_data: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: AwareDatetime
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    query: str = Field(min_length=1, max_length=2000)

    @field_validator("nct_id")
    @classmethod
    def normalize_nct_id(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"NCT\d{8}", normalized):
            raise ValueError("nct_id must match NCT followed by eight digits")
        return normalized


class RegulatoryEventIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=500)
    regulator: str = Field(min_length=1, max_length=200)
    jurisdiction: str = Field(min_length=2, max_length=80)
    event_type: RegulatoryEventType
    event_status: str | None = Field(default=None, max_length=120)
    application_number: str = Field(min_length=1, max_length=120)
    application_type: str | None = Field(default=None, max_length=80)
    submission_number: str = Field(min_length=1, max_length=80)
    submission_type: str | None = Field(default=None, max_length=120)
    submission_class_code: str | None = Field(default=None, max_length=120)
    event_date_source: str | None = Field(default=None, max_length=80)
    product_names: list[str] = Field(default_factory=list)
    product_identifiers: list[dict[str, Any]] = Field(default_factory=list)
    active_ingredients: list[dict[str, Any]] = Field(default_factory=list)
    sponsor_name: str | None = Field(default=None, max_length=1000)
    title: str = Field(min_length=1, max_length=5000)
    retrieved_at: AwareDatetime
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    source_url: HttpUrl
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    raw_payload_ref: str = Field(min_length=1, max_length=2000)
    query: str = Field(min_length=1, max_length=2000)


class PatentRecordIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(default="Google Patents", min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=400)
    jurisdiction: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=1, max_length=5000)
    abstract: str | None = None
    application_number: str | None = Field(default=None, max_length=200)
    publication_number: str | None = Field(default=None, max_length=200)
    grant_number: str | None = Field(default=None, max_length=200)
    family_identifier: str | None = Field(default=None, max_length=200)
    filing_date_source: str | None = Field(default=None, max_length=80)
    publication_date_source: str | None = Field(default=None, max_length=80)
    grant_date_source: str | None = Field(default=None, max_length=80)
    status: str | None = Field(default=None, max_length=200)
    patent_type: str | None = Field(default=None, max_length=200)
    applicants: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    inventors: list[str] = Field(default_factory=list)
    classifications: list[str] = Field(default_factory=list)
    priority_numbers: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    source_url: HttpUrl
    retrieved_at: AwareDatetime
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    raw_payload_ref: str = Field(min_length=1, max_length=2000)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    query: str = Field(min_length=1, max_length=2000)

    @field_validator("jurisdiction")
    @classmethod
    def normalize_jurisdiction(cls, value: str) -> str:
        return value.strip().upper()


class IPEntityIdentifierRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: IPReferenceRole
    entity_type: EntityType
    namespace: str = Field(min_length=1, max_length=120)
    identifier_type: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=500)


class LicensingEventIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=500)
    event_type: LicensingEventType
    title: str = Field(min_length=1, max_length=5000)
    source_name: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    event_date_source: str | None = Field(default=None, max_length=80)
    effective_date_source: str | None = Field(default=None, max_length=80)
    expiration_date_source: str | None = Field(default=None, max_length=80)
    licensor_names: list[str] = Field(default_factory=list)
    licensee_names: list[str] = Field(default_factory=list)
    asset_names: list[str] = Field(default_factory=list)
    patent_identifiers: list[str] = Field(default_factory=list)
    territory: list[str] = Field(default_factory=list)
    exclusivity: ExclusivityState = ExclusivityState.UNKNOWN
    field_of_use: str | None = Field(default=None, max_length=2000)
    rights_scope: str | None = Field(default=None, max_length=2000)
    entity_references: list[IPEntityIdentifierRef] = Field(default_factory=list, max_length=100)
    retrieved_at: AwareDatetime
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    raw_payload_ref: str = Field(min_length=1, max_length=2000)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    query: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_reference_types(self) -> LicensingEventIngest:
        expected = {
            IPReferenceRole.LICENSOR: EntityType.COMPANY,
            IPReferenceRole.LICENSEE: EntityType.COMPANY,
            IPReferenceRole.ASSIGNOR: EntityType.COMPANY,
            IPReferenceRole.ASSIGNEE: EntityType.COMPANY,
            IPReferenceRole.ASSET: EntityType.THERAPEUTIC_ASSET,
            IPReferenceRole.PATENT: EntityType.PATENT,
        }
        for reference in self.entity_references:
            if reference.entity_type != expected[reference.role]:
                raise ValueError(
                    f"{reference.role.value} references must identify "
                    f"{expected[reference.role].value} entities"
                )
        return self


class IdentifierInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str = Field(min_length=1, max_length=120)
    identifier_type: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=500)
    source_record: SourceRecordInput


class AliasInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=500)
    alias_type: str = "alias"
    verification_state: VerificationState = VerificationState.UNREVIEWED
    source_record: SourceRecordInput


class CanonicalEntityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: EntityType
    preferred_name: str = Field(min_length=1, max_length=500)
    description: str | None = None
    modality: Modality | None = None
    lifecycle_status: str | None = Field(default=None, max_length=120)
    visibility: Visibility = Visibility.GLOBAL
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_record: SourceRecordInput
    identifiers: list[IdentifierInput] = Field(default_factory=list, max_length=100)
    aliases: list[AliasInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_entity_fields(self) -> CanonicalEntityCreate:
        if self.entity_type == EntityType.THERAPEUTIC_ASSET and self.modality is None:
            raise ValueError("therapeutic assets require a modality")
        if self.entity_type != EntityType.THERAPEUTIC_ASSET and self.modality is not None:
            raise ValueError("modality is only valid for therapeutic assets")
        attributes_model = ENTITY_ATTRIBUTE_MODELS[self.entity_type].model_validate(self.attributes)
        self.attributes = attributes_model.model_dump(mode="json", exclude_none=True)
        return self


class CanonicalEntityResponse(BaseModel):
    id: UUID
    entity_type: EntityType
    preferred_name: str
    normalized_name: str
    description: str | None = None
    modality: Modality | None = None
    lifecycle_status: str | None = None
    visibility: Visibility
    organization_id: UUID | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_source_record_id: UUID | None = None
    identifiers: list[dict[str, Any]] = Field(default_factory=list)
    aliases: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CanonicalEntityPage(BaseModel):
    items: list[CanonicalEntityResponse]
    total: int
    page: int
    page_size: int


class CanonicalRelationshipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_entity_id: UUID
    predicate: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    object_entity_id: UUID
    visibility: Visibility = Visibility.GLOBAL
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_record: SourceRecordInput
    property_name: str = Field(default="relationship_observed", min_length=1, max_length=160)
    observation_value: Any
    observation_kind: ObservationKind = ObservationKind.NORMALIZED_OBSERVATION
    verification_state: VerificationState = VerificationState.UNREVIEWED
    confidence: float | None = Field(default=None, ge=0, le=1)
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_temporal_range(self) -> CanonicalRelationshipCreate:
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must not be later than valid_to")
        if self.subject_entity_id == self.object_entity_id:
            raise ValueError("relationship endpoints must be different")
        return self


class ObservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: UUID
    relationship_id: UUID | None = None
    visibility: Visibility = Visibility.GLOBAL
    property_name: str = Field(min_length=1, max_length=160)
    observation_kind: ObservationKind
    value: Any
    verification_state: VerificationState = VerificationState.UNREVIEWED
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_record: SourceRecordInput
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None
    normalizer_version: str | None = Field(default=None, max_length=120)
    supersedes_observation_id: UUID | None = None

    @model_validator(mode="after")
    def validate_temporal_range(self) -> ObservationCreate:
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must not be later than valid_to")
        if self.observation_kind == ObservationKind.HYPOTHESIS and self.verification_state != VerificationState.UNREVIEWED:
            raise ValueError("hypotheses must remain unreviewed")
        return self


class ClaimCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: UUID
    claim_type: ClaimType = ClaimType.DERIVED_CLAIM
    statement: str = Field(min_length=1, max_length=5000)
    visibility: Visibility = Visibility.GLOBAL
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_record: SourceRecordInput
    observation_id: UUID | None = None
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_temporal_range(self) -> ClaimCreate:
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must not be later than valid_to")
        return self


class EvidenceLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: UUID | None = None
    source_record_id: UUID | None = None
    relation_type: EvidenceRelationType = EvidenceRelationType.SUPPORTING
    metadata: dict[str, Any] = Field(default_factory=dict)
    visibility: Visibility = Visibility.GLOBAL
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_link(self) -> EvidenceLinkCreate:
        if self.observation_id is None and self.source_record_id is None:
            raise ValueError("evidence must reference either an observation or a source_record")
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must not be later than valid_to")
        return self


class IdentityResolution(BaseModel):
    status: str
    entity: CanonicalEntityResponse | None = None
    candidates: list[CanonicalEntityResponse] = Field(default_factory=list)
