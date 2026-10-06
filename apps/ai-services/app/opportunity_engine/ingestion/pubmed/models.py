from __future__ import annotations

import hashlib
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.opportunity_engine.domain.canonical_model import ScientificEvidenceState


class ExtractionCategory(str, Enum):
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
    CNS_EXPOSURE = "cns_exposure"
    CNS_EFFICACY = "cns_efficacy"
    RESISTANCE = "resistance"
    COMBINATION = "combination"
    CLINICAL_OUTCOME = "clinical_outcome"


class IngestionStatus(str, Enum):
    INGESTED = "INGESTED"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"
    RETRIED_AND_SUCCEEDED = "RETRIED_AND_SUCCEEDED"
    FAILED = "FAILED"


# ==============================================================================
# 1. Extracted Scientific Observation
# ==============================================================================

class ExtractedObservation(BaseModel):
    """
    Extracted scientific claim or parameter anchored to PubMed text.
    Strictly flags AI extraction as NOT ground truth (is_ground_truth=False,
    epistemic_status='ai_inference') and retains provenance.
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
    source_citation: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 2. Raw PubMed Article Record
# ==============================================================================

class PubMedArticleRecord(BaseModel):
    """
    Comprehensive PubMed record capturing all 11 core bibliographical and scientific fields:
    PMID, title, abstract, authors, journal, publication date, study type,
    keywords, mesh terms, entities, references where available.
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
    entities: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)
    raw_source: Dict[str, Any] = Field(default_factory=dict)
    source_citation: str = ""
    content_hash: str = ""
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
        if not self.source_citation:
            first_author = self.authors[0] if self.authors else "Unknown"
            year = self.publication_date.year
            self.source_citation = f"{first_author} et al., {self.journal} ({year}). PMID:{self.pmid}"


# ==============================================================================
# 3. Ingestion Result & Audit
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
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
