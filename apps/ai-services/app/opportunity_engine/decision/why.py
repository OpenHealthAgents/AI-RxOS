from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.opportunity_engine.decision.models import DecisionAction, DecisionResult
from app.opportunity_engine.intelligence import IntelligenceValueStatus


class WhyTraceContribution(BaseModel):
    section: str
    category: str
    value: float | None = None
    confidence: float | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    model_version: str | None = None
    feature_version: str | None = None
    rationale: str
    source: str | None = None


class WhyResult(BaseModel):
    asset_id: str
    tenant_id: str | None = None
    evaluation_cutoff: date
    decision: DecisionAction
    score: float
    confidence: float
    supporting_evidence: list[str] = Field(default_factory=list)
    contradictory_evidence: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    ml_contributors: list[WhyTraceContribution] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    what_would_change_recommendation: list[str] = Field(default_factory=list)
    explanation: str
    trace: list[WhyTraceContribution] = Field(default_factory=list)


class WhyEngine:
    """Explain the master decision using only traceable evidence and explicit unknowns."""

    def explain(self, decision_result: DecisionResult, *, inputs: dict[str, Any] | None = None) -> WhyResult:
        input_payload = inputs or {}
        supporting_evidence: list[str] = []
        contradictory_evidence: list[str] = []
        unknowns: list[str] = []
        ml_contributors: list[WhyTraceContribution] = []
        assumptions: list[str] = []
        evidence_gaps: list[str] = []
        trace: list[WhyTraceContribution] = []

        for section_name, payload in input_payload.items():
            normalized = self._normalize_signal(payload)
            category = self._classify_section(section_name, normalized)
            evidence_refs = self._collect_evidence_refs(payload)
            if evidence_refs:
                supporting_evidence.extend(evidence_refs)

            contrad = self._collect_contradictory_refs(payload)
            if contrad:
                contradictory_evidence.extend(contrad)

            if normalized["status"] in {
                IntelligenceValueStatus.UNKNOWN,
                IntelligenceValueStatus.UNAVAILABLE,
                IntelligenceValueStatus.INSUFFICIENT_EVIDENCE,
            }:
                unknowns.append(f"{section_name}: {normalized.get('reason') or 'no observable value'}")
                evidence_gaps.append(f"{section_name}: {normalized.get('reason') or 'missing signal'}")

            if normalized.get("model_version") or normalized.get("feature_version"):
                ml_contributors.append(
                    WhyTraceContribution(
                        section=section_name,
                        category=category,
                        value=self._coerce_numeric_value(normalized.get("value")),
                        confidence=normalized.get("confidence"),
                        evidence_refs=evidence_refs,
                        model_version=str(normalized["model_version"]) if normalized.get("model_version") else None,
                        feature_version=str(normalized["feature_version"]) if normalized.get("feature_version") else None,
                        rationale=normalized.get("reason") or f"{section_name} contributed via model lineage.",
                        source="ml_prediction" if normalized.get("model_version") else "feature",
                    )
                )

            if normalized["status"] == IntelligenceValueStatus.AVAILABLE:
                value = self._coerce_numeric_value(normalized.get("value"))
                trace.append(
                    WhyTraceContribution(
                        section=section_name,
                        category=category,
                        value=value,
                        confidence=normalized.get("confidence"),
                        evidence_refs=evidence_refs,
                        model_version=str(normalized["model_version"]) if normalized.get("model_version") else None,
                        feature_version=str(normalized["feature_version"]) if normalized.get("feature_version") else None,
                        rationale=normalized.get("reason") or f"{section_name} was evaluated as available evidence.",
                        source="evidence" if not normalized.get("model_version") else "ml_prediction",
                    )
                )

        if decision_result.unknowns:
            unknowns.extend(decision_result.unknowns)
        if decision_result.contradictory_evidence:
            contradictory_evidence.extend(decision_result.contradictory_evidence)
        if decision_result.supporting_evidence:
            supporting_evidence.extend(decision_result.supporting_evidence)

        if not supporting_evidence:
            assumptions.append("No supporting evidence references were provided for this decision.")
        if contradictory_evidence:
            assumptions.append("Contradictory evidence was retained and not overwritten by favorable assumptions.")
        if not input_payload:
            assumptions.append("No upstream input payload was supplied; the explanation is limited to the final decision output.")

        critical_gap_message = self._critical_gap_message(decision_result.decision)
        if critical_gap_message:
            evidence_gaps.append(critical_gap_message)
            assumptions.append(critical_gap_message)

        what_would_change = self._what_would_change(decision_result.decision, evidence_gaps, unknowns)
        supporting_evidence = list(dict.fromkeys(supporting_evidence))
        contradictory_evidence = list(dict.fromkeys(contradictory_evidence))
        unknowns = list(dict.fromkeys(unknowns))
        evidence_gaps = list(dict.fromkeys(evidence_gaps))
        ml_contributors = [
            contributor for contributor in ml_contributors if contributor.model_version or contributor.feature_version
        ][:10]

        explanation = self._build_explanation(decision_result, supporting_evidence, contradictory_evidence, unknowns, evidence_gaps)
        return WhyResult(
            asset_id=decision_result.asset_id,
            tenant_id=decision_result.tenant_id,
            evaluation_cutoff=decision_result.evaluation_cutoff,
            decision=decision_result.decision,
            score=decision_result.score,
            confidence=decision_result.confidence,
            supporting_evidence=supporting_evidence[:25],
            contradictory_evidence=contradictory_evidence[:25],
            unknowns=unknowns[:25],
            ml_contributors=ml_contributors,
            assumptions=assumptions[:15],
            evidence_gaps=evidence_gaps[:15],
            what_would_change_recommendation=what_would_change[:10],
            explanation=explanation,
            trace=trace[:25],
        )

    def _normalize_signal(self, payload: Any) -> dict[str, Any]:
        if payload is None:
            return {"status": IntelligenceValueStatus.UNKNOWN, "value": None, "confidence": None, "reason": "No signal available."}
        if isinstance(payload, dict):
            status = payload.get("status") or payload.get("state") or payload.get("availability") or IntelligenceValueStatus.AVAILABLE.value
            value = payload.get("value")
            if value is None:
                value = payload.get("score")
            if value is None:
                value = payload.get("probability")
            if value is None and isinstance(payload.get("result"), dict):
                value = payload["result"].get("value")
            confidence = payload.get("confidence")
            if confidence is None and isinstance(payload.get("provenance"), dict):
                confidence = payload["provenance"].get("confidence")
            return {
                "status": self._status_from_value(status),
                "value": value,
                "confidence": self._coerce_confidence(confidence),
                "reason": payload.get("reason") or payload.get("summary") or payload.get("message"),
                "model_version": payload.get("model_version") or payload.get("modelVersion"),
                "feature_version": payload.get("feature_version") or payload.get("featureVersion"),
            }
        if hasattr(payload, "status") and hasattr(payload, "value"):
            return self._normalize_signal(
                {
                    "status": getattr(payload, "status"),
                    "value": getattr(payload, "value"),
                    "confidence": getattr(payload, "confidence", None),
                    "reason": getattr(payload, "reason", None),
                    "model_version": getattr(payload, "model_version", None),
                    "feature_version": getattr(payload, "feature_version", None),
                }
            )
        if hasattr(payload, "model_dump"):
            return self._normalize_signal(payload.model_dump())
        return {"status": IntelligenceValueStatus.UNKNOWN, "value": None, "confidence": None, "reason": "Unsupported payload."}

    def _status_from_value(self, status: Any) -> IntelligenceValueStatus:
        if status is None:
            return IntelligenceValueStatus.UNKNOWN
        if isinstance(status, IntelligenceValueStatus):
            return status
        text = str(status).upper()
        if text in {"AVAILABLE", "OK", "POSITIVE", "SUCCESS"}:
            return IntelligenceValueStatus.AVAILABLE
        if text in {"UNKNOWN", "UNSPECIFIED"}:
            return IntelligenceValueStatus.UNKNOWN
        if text in {"UNAVAILABLE", "MISSING", "ABSENT", "NOT_AVAILABLE"}:
            return IntelligenceValueStatus.UNAVAILABLE
        if text in {"INSUFFICIENT_EVIDENCE", "INSUFFICIENT", "LOW_CONFIDENCE"}:
            return IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
        return IntelligenceValueStatus.AVAILABLE

    def _coerce_confidence(self, value: Any) -> float | None:
        try:
            if value is None:
                return None
            conf = float(value)
            if conf != conf:
                return None
            return max(0.0, min(1.0, conf))
        except Exception:
            return None

    def _coerce_numeric_value(self, value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            if cleaned.endswith("%"):
                cleaned = cleaned[:-1]
            try:
                return float(cleaned)
            except ValueError:
                return None
        if isinstance(value, dict):
            return self._coerce_numeric_value(value.get("value"))
        if hasattr(value, "value"):
            return self._coerce_numeric_value(getattr(value, "value"))
        return None

    def _classify_section(self, section_name: str, normalized: dict[str, Any]) -> str:
        if normalized.get("model_version") or normalized.get("feature_version"):
            if section_name in {"clinical", "biology", "cns", "patient", "ml_predictions"}:
                return "ML_PREDICTION"
            return "DERIVED_FEATURE"
        if normalized["status"] == IntelligenceValueStatus.AVAILABLE:
            return "FACT"
        if normalized["status"] in {IntelligenceValueStatus.UNKNOWN, IntelligenceValueStatus.UNAVAILABLE}:
            return "UNKNOWN"
        return "AI_INFERENCE"

    def _collect_evidence_refs(self, payload: Any) -> list[str]:
        refs: list[str] = []
        if isinstance(payload, dict):
            for key in ("supporting_evidence", "evidence", "references", "evidence_references"):
                items = payload.get(key) or []
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, str):
                            refs.append(item)
                        elif isinstance(item, dict):
                            source = item.get("source_reference") or item.get("citation")
                            if source:
                                refs.append(str(source))
            provenance = payload.get("provenance")
            if isinstance(provenance, dict):
                source = provenance.get("source_reference") or provenance.get("citation")
                if source:
                    refs.append(str(source))
        if hasattr(payload, "supporting_evidence"):
            for item in getattr(payload, "supporting_evidence") or []:
                if isinstance(item, str):
                    refs.append(item)
                elif hasattr(item, "source_reference"):
                    refs.append(str(item.source_reference))
        return list(dict.fromkeys(refs))

    def _collect_contradictory_refs(self, payload: Any) -> list[str]:
        refs: list[str] = []
        if isinstance(payload, dict):
            for key in ("contradictory_evidence", "contradicting_evidence", "conflicts"):
                for item in payload.get(key, []) or []:
                    if isinstance(item, str):
                        refs.append(item)
                    elif isinstance(item, dict):
                        source = item.get("source_reference") or item.get("citation")
                        if source:
                            refs.append(str(source))
        return list(dict.fromkeys(refs))

    def _critical_gap_message(self, decision: DecisionAction) -> str | None:
        if decision == DecisionAction.INSUFFICIENT_EVIDENCE:
            return "Insufficient critical evidence is blocking a reliable recommendation."
        return None

    def _what_would_change(self, decision: DecisionAction, evidence_gaps: list[str], unknowns: list[str]) -> list[str]:
        if decision == DecisionAction.PURSUE:
            return [
                "A materially worse safety or licensing signal, or new contradictory clinical evidence, could reduce this recommendation.",
                "Additional patient, CNS, or commercial evidence would increase confidence and reduce uncertainty.",
            ]
        if decision == DecisionAction.PARTNER:
            return [
                "Strong licensing or commercial evidence could shift the recommendation toward LICENSE or PURSUE.",
                "A negative safety or clinical trend would reduce the partnership recommendation.",
            ]
        if decision == DecisionAction.LICENSE:
            return [
                "A licensing evidence gap or adverse safety finding could materially change this recommendation.",
                "Stronger internal commercial or competitive evidence could modify the recommended license path.",
            ]
        if decision == DecisionAction.MONITOR:
            return [
                "Additional patient, CNS, or biomarker evidence could upgrade this to PURSUE or PARTNER.",
                "New negative safety, competition, or licensing findings could push this to AVOID.",
            ]
        if decision == DecisionAction.AVOID:
            return [
                "A strong safety recovery, improved patient match, or materially better evidence quality could change the recommendation.",
                "New evidence that resolves key gaps could reduce the negative position.",
            ]
        return [
            "Additional safety, licensing, commercial, patient, or CNS evidence could resolve the current insufficiency.",
            "A cleared evidence gap or stronger positive evidence could change the recommendation.",
        ]

    def _build_explanation(
        self,
        decision_result: DecisionResult,
        supporting_evidence: list[str],
        contradictory_evidence: list[str],
        unknowns: list[str],
        evidence_gaps: list[str],
    ) -> str:
        positive = ", ".join(decision_result.positive_drivers[:3]) if decision_result.positive_drivers else "no explicit positive driver"
        negative = ", ".join(decision_result.negative_drivers[:3]) if decision_result.negative_drivers else "no explicit negative driver"
        if decision_result.decision == DecisionAction.INSUFFICIENT_EVIDENCE:
            return (
                f"{decision_result.decision.value} because critical evidence is missing or materially uncertain: "
                f"{'; '.join(evidence_gaps) if evidence_gaps else 'insufficient evidence'}; "
                f"supporting evidence={len(supporting_evidence)}, contradictory evidence={len(contradictory_evidence)}, "
                f"unknowns={len(unknowns)}."
            )
        return (
            f"{decision_result.decision.value} driven by {positive} and tempered by {negative}. "
            f"Supporting evidence references={len(supporting_evidence)}, contradictory evidence references={len(contradictory_evidence)}, "
            f"unknowns={len(unknowns)}, evidence gaps={len(evidence_gaps)}."
        )


__all__ = ["WhyEngine", "WhyResult", "WhyTraceContribution"]
