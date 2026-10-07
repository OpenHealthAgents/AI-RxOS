from __future__ import annotations

import hashlib
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.opportunity_engine.domain.canonical_model import ScientificEvidenceState


class ExtractionCategory(str, Enum):
    ASSET = "asset"
    DRUG = "drug"
    TARGET = "target"
    GENE = "gene"
    MUTATION = "mutation"
    DISEASE = "disease"
    BIOMARKER = "biomarker"
    MODEL = "model"
    CELL_LINE = "cell_line"
    ANIMAL_MODEL = "animal_model"
    EFFICACY = "efficacy"
    TOXICITY = "toxicity"
    CNS = "cns"
    CNS_EXPOSURE = "cns_exposure"
    CNS_EFFICACY = "cns_efficacy"
    RESISTANCE = "resistance"
    COMBINATION = "combination"
    CLINICAL_RESULT = "clinical_result"
    CLINICAL_OUTCOME = "clinical_outcome"


class IngestionStatus(str, Enum):
    INGESTED = "INGESTED"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"
    RETRIED_AND_SUCCEEDED = "RETRIED_AND_SUCCEEDED"
    FAILED = "FAILED"


# ==============================================================================
# 1. Extraction Lineage
# ==============================================================================

class ExtractionLineage(BaseModel):
    """
    Complete immutable provenance lineage tracking how an observation
    was extracted from raw scientific text.
    """
    model_config = ConfigDict(from_attributes=True)
    lineage_id: UUID = Field(default_factory=uuid4)
    pmid: str
    article_title: str
    journal: str
    publication_date: date
    extractor_model: str = "BioExtractor-Ensemble-v2.1"
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_location: str
    raw_verbatim_quote: str
    provenance_hash: str
    evidence_source_id: Optional[UUID] = None


# ==============================================================================
# 2. Quality Checks & Verification
# ==============================================================================

class QualityCheckRule(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rule_name: str
    passed: bool
    score: float = Field(ge=0.0, le=100.0)
    details: str
    is_blocking: bool = False


class PubMedQualityReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pmid: str
    overall_quality_score: float = Field(ge=0.0, le=100.0)
    quality_tier: str = "HIGH"  # HIGH, MEDIUM, LOW, REJECTED
    quality_passed: bool = True
    hallucination_check_passed: bool = True
    rules: List[QualityCheckRule] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 3. Extracted Scientific Observation
# ==============================================================================

class ExtractedObservation(BaseModel):
    """
    Extracted scientific claim or parameter anchored to PubMed text.
    Strictly flags AI extraction as NOT ground truth (is_ground_truth=False,
    epistemic_status='ai_inference') and retains full extraction lineage.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    pmid: str
    extraction_category: ExtractionCategory
    entity_text: str
    extracted_text: str
    source_location: str
    normalized_value: Optional[float] = None
    normalized_unit: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.88)
    is_ground_truth: bool = False
    epistemic_status: ScientificEvidenceState = ScientificEvidenceState.AI_INFERENCE
    extraction_model_version: str = "BioExtractor-Ensemble-v2.1"
    resolved_canonical_id: Optional[UUID] = None
    resolved_canonical_name: Optional[str] = None
    entity_resolution_confidence: Optional[float] = None
    resolution_method: Optional[str] = None
    source_citation: str
    lineage: Optional[ExtractionLineage] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 4. Raw PubMed Article Record
# ==============================================================================

class PubMedArticleRecord(BaseModel):
    """
    Comprehensive PubMed record capturing all required fields:
    PMID, title, abstract, authors, journal, publication date, study type,
    MeSH, keywords, entities, references.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    pmid: str
    doi: Optional[str] = None
    title: str
    abstract: str
    authors: List[str] = Field(default_factory=list)
    journal: str
    publication_date: date
    study_type: str = "literature"
    keywords: List[str] = Field(default_factory=list)
    mesh_terms: List[str] = Field(default_factory=list)
    mesh: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)
    raw_source: Dict[str, Any] = Field(default_factory=dict)
    source_citation: str = ""
    content_hash: str = ""
    evidence_source_id: Optional[UUID] = None
    retrieval_date: date = Field(default_factory=date.today)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def compute_content_hash(self) -> str:
        """Computes deterministic SHA-256 hash of article title and abstract for deduplication."""
        hasher = hashlib.sha256()
        hasher.update(self.pmid.strip().encode("utf-8"))
        hasher.update(self.title.strip().encode("utf-8"))
        hasher.update(self.abstract.strip().encode("utf-8"))
        return hasher.hexdigest()

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            self.content_hash = self.compute_content_hash()
        if not self.mesh and self.mesh_terms:
            self.mesh = list(self.mesh_terms)
        elif not self.mesh_terms and self.mesh:
            self.mesh_terms = list(self.mesh)
        if not self.source_citation:
            first_author = self.authors[0] if self.authors else "Unknown"
            year = self.publication_date.year
            self.source_citation = f"{first_author} et al., {self.journal} ({year}). PMID:{self.pmid}"


# ==============================================================================
# 5. Ingestion Result & Audit
# ==============================================================================

class IngestionResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pmid: str
    status: IngestionStatus
    is_duplicate: bool = False
    retry_count: int = 0
    observations_count: int = 0
    resolved_entities_count: int = 0
    content_hash: str
    execution_duration_ms: float = 0.0
    audit_id: UUID = Field(default_factory=uuid4)
    observations: List[ExtractedObservation] = Field(default_factory=list)
    quality_report: Optional[PubMedQualityReport] = None
    evidence_source_id: Optional[UUID] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

