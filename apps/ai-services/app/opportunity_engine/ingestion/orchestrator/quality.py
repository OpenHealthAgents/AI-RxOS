from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from .models import IngestionItem, QualityValidationStatus


class DataQualityIssue(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field: str
    message: str
    severity: str = "ERROR"  # "ERROR" or "WARNING"
    rule_name: str


class DataQualityReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: str
    source: str
    status: QualityValidationStatus
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    issues: List[DataQualityIssue] = Field(default_factory=list)
    validated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "ERROR" for issue in self.issues)


class IngestionDataQualityValidator:
    """
    Production-grade data quality validation gate for raw ingestion items.
    Prevents malformed, incomplete, corrupt, or temporally impossible records
    from entering downstream biomedical knowledge graphs and analytical models.
    """

    NCT_REGEX = re.compile(r"^NCT\d{8}$", re.IGNORECASE)
    PMID_REGEX = re.compile(r"^\d{1,10}$")

    @classmethod
    def validate_item(
        cls,
        item: IngestionItem,
        strict_mode: bool = True,
    ) -> DataQualityReport:
        issues: List[DataQualityIssue] = []
        payload = item.payload or {}

        # 1. Structural Identity Check
        if not item.item_id or not str(item.item_id).strip():
            issues.append(
                DataQualityIssue(
                    field="item_id",
                    message="Missing mandatory item identifier.",
                    severity="ERROR",
                    rule_name="REQUIRED_FIELD_CHECK",
                )
            )

        if not item.source or not str(item.source).strip():
            issues.append(
                DataQualityIssue(
                    field="source",
                    message="Missing source provenance identifier.",
                    severity="ERROR",
                    rule_name="REQUIRED_FIELD_CHECK",
                )
            )

        # 2. Source-Specific Identifier Syntax
        source_clean = item.source.strip().lower()
        if "pubmed" in source_clean:
            # Must have PMID or digits
            raw_id = payload.get("pmid") or item.item_id
            if raw_id and not cls.PMID_REGEX.match(str(raw_id).strip()):
                issues.append(
                    DataQualityIssue(
                        field="pmid",
                        message=f"PMID '{raw_id}' does not match expected numeric identifier pattern.",
                        severity="ERROR",
                        rule_name="IDENTIFIER_SYNTAX_CHECK",
                    )
                )

        if "clinicaltrials" in source_clean or "trial" in source_clean:
            raw_nct = payload.get("nct_id") or item.item_id
            if raw_nct and not cls.NCT_REGEX.match(str(raw_nct).strip()):
                issues.append(
                    DataQualityIssue(
                        field="nct_id",
                        message=f"Clinical trial ID '{raw_nct}' does not match standard NCT format (NCT########).",
                        severity="ERROR",
                        rule_name="IDENTIFIER_SYNTAX_CHECK",
                    )
                )

        # 3. Payload Content & Entropy Check
        title = payload.get("title") or payload.get("brief_title") or payload.get("summary")
        if title is not None:
            clean_title = str(title).strip()
            if not clean_title or clean_title.lower() in ("n/a", "none", "null", "[not available]", "test"):
                issues.append(
                    DataQualityIssue(
                        field="title",
                        message="Title/summary is empty or contains non-informative placeholder text.",
                        severity="ERROR",
                        rule_name="CONTENT_ENTROPY_CHECK",
                    )
                )
        else:
            issues.append(
                DataQualityIssue(
                    field="title",
                    message="Mandatory title or summary field is missing from payload.",
                    severity="ERROR",
                    rule_name="REQUIRED_CONTENT_CHECK",
                )
            )

        # 4. Temporal Sanity Check (No impossible future observation dates)
        now_utc = datetime.now(timezone.utc)
        record_date_val = item.timestamp or payload.get("publication_date") or payload.get("effective_date") or payload.get("filing_date")
        if record_date_val:
            try:
                parsed_dt: Optional[datetime] = None
                if isinstance(record_date_val, datetime):
                    parsed_dt = record_date_val
                elif isinstance(record_date_val, date):
                    parsed_dt = datetime(record_date_val.year, record_date_val.month, record_date_val.day, tzinfo=timezone.utc)
                elif isinstance(record_date_val, str):
                    # Simple ISO parsing
                    clean_str = record_date_val.strip()
                    if "T" in clean_str:
                        parsed_dt = datetime.fromisoformat(clean_str.replace("Z", "+00:00"))
                    else:
                        d_parts = [int(p) for p in clean_str.split("-")]
                        parsed_dt = datetime(d_parts[0], d_parts[1], d_parts[2], tzinfo=timezone.utc)

                if parsed_dt:
                    if parsed_dt.tzinfo is None:
                        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                    # Future date check: allow up to 30 days ahead for scheduled publication/registration
                    max_future_days = 30
                    delta_days = (parsed_dt - now_utc).total_seconds() / 86400.0
                    if delta_days > max_future_days:
                        issues.append(
                            DataQualityIssue(
                                field="timestamp",
                                message=f"Record date {parsed_dt.isoformat()} is in the distant future ({delta_days:.0f} days ahead).",
                                severity="ERROR",
                                rule_name="TEMPORAL_SANITY_CHECK",
                            )
                        )
                    # Year sanity check (e.g. before 1900 is suspect for modern pharma)
                    if parsed_dt.year < 1900:
                        issues.append(
                            DataQualityIssue(
                                field="timestamp",
                                message=f"Record year {parsed_dt.year} is earlier than baseline threshold (1900).",
                                severity="ERROR",
                                rule_name="TEMPORAL_SANITY_CHECK",
                            )
                        )
            except Exception as e:
                issues.append(
                    DataQualityIssue(
                        field="timestamp",
                        message=f"Date parsing failed: {e}",
                        severity="WARNING",
                        rule_name="DATE_PARSING_CHECK",
                    )
                )

        # 5. Determine Quality Status and Score
        error_count = sum(1 for issue in issues if issue.severity == "ERROR")
        warning_count = sum(1 for issue in issues if issue.severity == "WARNING")

        if error_count > 0:
            status = QualityValidationStatus.FAILED
            score = max(0.0, 1.0 - (error_count * 0.3 + warning_count * 0.1))
        elif warning_count > 0:
            status = QualityValidationStatus.WARNING
            score = max(0.5, 1.0 - (warning_count * 0.1))
        else:
            status = QualityValidationStatus.PASSED
            score = 1.0

        return DataQualityReport(
            item_id=str(item.item_id),
            source=item.source,
            status=status,
            score=round(score, 2),
            issues=issues,
        )
