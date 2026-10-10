from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from app.opportunity_engine.intelligence import (
    EpistemicClass,
    IntelligenceEvidence,
    IntelligenceValue,
    IntelligenceValueStatus,
)

from .models import DecisionAction, DecisionPolicy, DecisionRequest, DecisionResult


class MasterDecisionEngine:
    """Configurable decision layer that combines intelligence inputs into an as-of recommendation."""

    def __init__(self, policy: DecisionPolicy | None = None) -> None:
        self.policy = policy or DecisionPolicy()

    def evaluate(
        self,
        asset_id: str,
        tenant_id: str | None = None,
        evaluation_cutoff: date | str | None = None,
        policy: DecisionPolicy | None = None,
        **inputs: Any,
    ) -> DecisionResult:
        request = DecisionRequest(
            asset_id=asset_id,
            tenant_id=tenant_id,
            evaluation_cutoff=evaluation_cutoff,
            policy=policy or self.policy,
            **{k: v for k, v in inputs.items() if k in DecisionRequest.model_fields},
        )
        return self.evaluate_request(request)

    def evaluate_request(self, request: DecisionRequest) -> DecisionResult:
        cutoff = self._coerce_date(request.evaluation_cutoff) if request.evaluation_cutoff else date.today()
        policy = request.policy or self.policy
        inputs = {
            "biology": request.biology,
            "clinical": request.clinical,
            "cns": request.cns,
            "patient": request.patient,
            "safety": request.safety,
            "resistance": request.resistance,
            "combination": request.combination,
            "competition": request.competition,
            "licensing": request.licensing,
            "commercial": request.commercial,
            "evidence_quality": request.evidence_quality,
            "ml_predictions": request.ml_predictions,
        }

        unknowns: list[str] = list(request.unknowns or [])
        positive_drivers: list[str] = []
        negative_drivers: list[str] = []
        supporting_evidence_strings: list[str] = []
        contradictory_evidence_strings: list[str] = []
        availability: dict[str, str] = {}
        evidence_quality_value = self._coerce_evidence_quality(request.evidence_quality)

        critical_missing = self._detect_critical_missing(inputs)
        if critical_missing:
            unknowns.extend(critical_missing)

        weighted_score = 50.0
        total_policy_weight = 0.0
        risk_penalty = 0.0
        confidence_inputs: list[float] = []
        metadata_versions: dict[str, str] = {}
        feature_versions: dict[str, str] = {}
        section_values: dict[str, float] = {}

        for section_name, payload in inputs.items():
            if payload is None:
                availability[section_name] = "UNKNOWN"
                continue

            normalized = self._normalize_signal(payload)
            availability[section_name] = normalized["status"]
            value = normalized["value"]
            confidence = normalized["confidence"]
            if confidence is not None:
                confidence_inputs.append(confidence)
            if normalized.get("model_version"):
                metadata_versions[section_name] = str(normalized["model_version"])
            if normalized.get("feature_version"):
                feature_versions[section_name] = str(normalized["feature_version"])

            if normalized["status"] in {IntelligenceValueStatus.UNKNOWN, IntelligenceValueStatus.UNAVAILABLE, IntelligenceValueStatus.INSUFFICIENT_EVIDENCE}:
                unknowns.append(f"{section_name}: {normalized.get('reason') or 'missing signal'}")
                weighted_score -= policy.unknown_penalty
                total_policy_weight += 1.0
                continue

            if normalized["status"] != IntelligenceValueStatus.AVAILABLE:
                continue

            if value is None:
                weighted_score -= policy.unknown_penalty
                unknowns.append(f"{section_name}: no numeric value available")
                continue

            category_weight = self._weight_for_section(section_name)
            total_policy_weight += category_weight
            numeric_value = self._coerce_numeric_value(value)
            if numeric_value is None:
                weighted_score -= policy.unknown_penalty
                continue

            section_values[section_name] = numeric_value
            contribution = self._apply_policy_contribution(section_name, numeric_value, policy)
            weighted_score += contribution

            if contribution > 0:
                positive_drivers.append(self._driver_label(section_name, numeric_value))
            elif contribution < 0:
                negative_drivers.append(self._driver_label(section_name, numeric_value, positive=False))

            evidence_refs = self._collect_evidence_refs(payload)
            if evidence_refs:
                supporting_evidence_strings.extend(evidence_refs)

            if self._has_contradictory_evidence(payload):
                contradictory_evidence_strings.extend(self._collect_contradictory_refs(payload))
                weighted_score -= policy.contradiction_penalty
                risk_penalty += policy.contradiction_penalty

        if evidence_quality_value is not None:
            weighted_score += max(0.0, (evidence_quality_value * 20.0) - 5.0)

        if section_values:
            safety_value = section_values.get("safety", 50.0)
            licensing_value = section_values.get("licensing", 50.0)
            commercial_value = section_values.get("commercial", 50.0)
            for key, value in {"safety": safety_value, "licensing": licensing_value, "commercial": commercial_value}.items():
                if value < 35.0:
                    weighted_score -= 12.0
                    negative_drivers.append(f"{key.replace('_', ' ').title()} material weakness ({value:.1f})")

        confidence = self._compute_confidence(confidence_inputs, evidence_quality_value, unknowns, critical_missing)
        weighted_score = max(0.0, min(100.0, weighted_score))

        decision = self._choose_decision(weighted_score, confidence, policy, critical_missing, availability, evidence_quality_value, section_values)
        priority = self._priority_for(decision, weighted_score)
        recommended_action = decision.value

        supporting_evidence_strings = list(dict.fromkeys(supporting_evidence_strings))
        contradictory_evidence_strings = list(dict.fromkeys(contradictory_evidence_strings))
        unknowns = list(dict.fromkeys(unknowns))

        return DecisionResult(
            asset_id=request.asset_id,
            tenant_id=request.tenant_id,
            evaluation_cutoff=cutoff,
            decision=decision,
            priority=priority,
            score=round(weighted_score, 2),
            confidence=round(confidence, 4),
            positive_drivers=positive_drivers[:8],
            negative_drivers=negative_drivers[:8],
            supporting_evidence=supporting_evidence_strings[:20],
            contradictory_evidence=contradictory_evidence_strings[:20],
            unknowns=unknowns[:25],
            recommended_action=recommended_action,
            policy_name=policy.name,
            policy_version=policy.version,
            evidence_quality=evidence_quality_value,
            upstream_signal_availability=availability,
            model_versions=metadata_versions,
            feature_versions=feature_versions,
        )

    def _coerce_date(self, value: date | str | None) -> date:
        if value is None:
            return date.today()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    def _coerce_evidence_quality(self, payload: Any) -> float | None:
        if payload is None:
            return None
        if isinstance(payload, (int, float)):
            return max(0.0, min(1.0, float(payload)))
        if isinstance(payload, dict):
            value = payload.get("value")
            if value is None:
                value = payload.get("score")
            if value is None:
                value = payload.get("quality_score")
            if value is None:
                value = payload.get("confidence")
            if value is None:
                return None
            return max(0.0, min(1.0, float(value)))
        if hasattr(payload, "value"):
            try:
                return max(0.0, min(1.0, float(payload.value)))
            except Exception:
                return None
        return None

    def _normalize_signal(self, payload: Any) -> dict[str, Any]:
        if payload is None:
            return {"status": IntelligenceValueStatus.UNKNOWN, "value": None, "confidence": None, "reason": "No upstream signal supplied."}
        if isinstance(payload, IntelligenceValue):
            source_status = payload.status
            return {
                "status": source_status,
                "value": payload.value,
                "confidence": payload.confidence,
                "reason": payload.reason,
                "model_version": None,
                "feature_version": None,
            }
        if isinstance(payload, dict):
            status = payload.get("status") or payload.get("state") or payload.get("availability") or IntelligenceValueStatus.AVAILABLE.value
            value = payload.get("value")
            if value is None and "score" in payload:
                value = payload.get("score")
            if value is None and "probability" in payload:
                value = payload.get("probability")
            if value is None and "predicted_value" in payload:
                value = payload.get("predicted_value")
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
            return self._normalize_signal({
                "status": getattr(payload, "status"),
                "value": getattr(payload, "value"),
                "confidence": getattr(payload, "confidence", None),
                "reason": getattr(payload, "reason", None),
                "model_version": getattr(payload, "model_version", None),
                "feature_version": getattr(payload, "feature_version", None),
            })
        if hasattr(payload, "model_dump"):
            return self._normalize_signal(payload.model_dump())
        return {"status": IntelligenceValueStatus.UNKNOWN, "value": None, "confidence": None, "reason": "Unsupported signal payload."}

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
            confidence = float(value)
            if math.isnan(confidence):
                return None
            return max(0.0, min(1.0, confidence))
        except Exception:
            return None

    def _coerce_numeric_value(self, value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            numeric = float(value)
            if math.isnan(numeric):
                return None
            return numeric

        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            if cleaned.endswith("%"):
                cleaned = cleaned[:-1]
            try:
                numeric = float(cleaned)
                if math.isnan(numeric):
                    return None
                return numeric
            except ValueError:
                return None

        if isinstance(value, dict):
            return self._coerce_numeric_value(value.get("value"))

        if hasattr(value, "value"):
            return self._coerce_numeric_value(getattr(value, "value"))

        return None

    def _weight_for_section(self, key: str) -> float:
        weights = {
            "biology": 18.0,
            "clinical": 17.0,
            "cns": 12.0,
            "patient": 12.0,
            "safety": 18.0,
            "resistance": 10.0,
            "combination": 8.0,
            "competition": 10.0,
            "licensing": 9.0,
            "commercial": 12.0,
            "evidence_quality": 12.0,
            "ml_predictions": 8.0,
        }
        return weights.get(key, 8.0)

    def _apply_policy_contribution(self, section_name: str, value: float, policy: DecisionPolicy) -> float:
        normalized = max(0.0, min(100.0, float(value)))
        if section_name in {"biology", "clinical", "patient", "commercial", "licensing", "competition"}:
            return normalized / 5.0 - 10.0
        if section_name == "safety":
            return (normalized - 50.0) / 3.0
        if section_name == "resistance":
            return (normalized - 50.0) / 4.0
        if section_name == "evidence_quality":
            return (normalized - 50.0) / 2.0
        if section_name == "ml_predictions":
            return normalized / 4.0 - 5.0
        return normalized / 6.0 - 6.0

    def _driver_label(self, section_name: str, value: float, positive: bool = True) -> str:
        label = section_name.replace("_", " ").title()
        if positive:
            return f"{label} signal strong ({value:.1f})"
        return f"{label} signal weak or adverse ({value:.1f})"

    def _collect_evidence_refs(self, payload: Any) -> list[str]:
        refs: list[str] = []
        if isinstance(payload, dict):
            for key in ("supporting_evidence", "evidence", "references", "evidence_references"):
                items = payload.get(key)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, str):
                            refs.append(item)
                        elif isinstance(item, dict):
                            if item.get("source_reference"):
                                refs.append(str(item["source_reference"]))
                            elif item.get("citation"):
                                refs.append(str(item["citation"]))
            if isinstance(payload.get("provenance"), dict):
                citation = payload["provenance"].get("source_reference") or payload["provenance"].get("citation")
                if citation:
                    refs.append(str(citation))
        if hasattr(payload, "supporting_evidence"):
            for item in list(getattr(payload, "supporting_evidence", []) or []):
                if isinstance(item, IntelligenceEvidence):
                    refs.append(item.source_reference)
                elif isinstance(item, dict):
                    refs.append(str(item.get("source_reference") or item.get("citation") or item))
        return list(dict.fromkeys(refs))

    def _has_contradictory_evidence(self, payload: Any) -> bool:
        if isinstance(payload, dict):
            for key in ("contradictory_evidence", "contradicting_evidence", "conflicts"):
                if payload.get(key):
                    return True
        if hasattr(payload, "contradictory_evidence"):
            return bool(getattr(payload, "contradictory_evidence"))
        return False

    def _collect_contradictory_refs(self, payload: Any) -> list[str]:
        refs: list[str] = []
        if isinstance(payload, dict):
            for key in ("contradictory_evidence", "contradicting_evidence", "conflicts"):
                for item in payload.get(key, []) or []:
                    if isinstance(item, str):
                        refs.append(item)
                    elif isinstance(item, dict):
                        if item.get("source_reference"):
                            refs.append(str(item["source_reference"]))
                        elif item.get("citation"):
                            refs.append(str(item["citation"]))
        return refs

    def _detect_critical_missing(self, inputs: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        for name in ["safety", "licensing", "commercial", "patient", "cns"]:
            value = inputs.get(name)
            if value is None:
                missing.append(f"Critical missing signal: {name}")
                continue
            normalized = self._normalize_signal(value)
            if normalized["status"] in {IntelligenceValueStatus.UNKNOWN, IntelligenceValueStatus.UNAVAILABLE, IntelligenceValueStatus.INSUFFICIENT_EVIDENCE}:
                missing.append(f"Critical missing signal: {name} ({normalized['status'].value})")
        return missing

    def _compute_confidence(self, confidence_values: list[float], evidence_quality: float | None, unknowns: list[str], critical_missing: list[str]) -> float:
        if not confidence_values:
            base = 0.25
        else:
            base = sum(confidence_values) / len(confidence_values)
        if evidence_quality is not None:
            base = (base + evidence_quality) / 2.0
        if critical_missing:
            base *= 0.8
        if unknowns:
            base *= max(0.35, 1.0 - (len(unknowns) * 0.04))
        return max(0.0, min(1.0, base))

    def _choose_decision(
        self,
        score: float,
        confidence: float,
        policy: DecisionPolicy,
        critical_missing: list[str],
        availability: dict[str, str],
        evidence_quality: float | None,
        section_values: dict[str, float] | None = None,
    ) -> DecisionAction:
        if critical_missing:
            return DecisionAction.INSUFFICIENT_EVIDENCE

        safety_value = (section_values or {}).get("safety", 50.0)
        licensing_value = (section_values or {}).get("licensing", 50.0)
        commercial_value = (section_values or {}).get("commercial", 50.0)

        if safety_value <= 20.0 or commercial_value <= 20.0:
            return DecisionAction.AVOID if score <= policy.avoid_score_floor or confidence < policy.min_confidence else DecisionAction.MONITOR
        if licensing_value >= 80.0 and score >= policy.license_score_floor and availability.get("licensing") == "AVAILABLE":
            return DecisionAction.LICENSE
        if score >= policy.pursue_score_floor and confidence >= policy.min_confidence:
            return DecisionAction.PURSUE
        if score >= policy.partner_score_floor and confidence >= policy.min_confidence:
            return DecisionAction.PARTNER
        if score >= policy.license_score_floor and availability.get("licensing") == "AVAILABLE" and confidence >= policy.min_confidence:
            return DecisionAction.LICENSE
        if score >= policy.monitor_score_floor:
            return DecisionAction.MONITOR
        if score <= policy.avoid_score_floor:
            return DecisionAction.AVOID
        if evidence_quality is not None and evidence_quality < policy.evidence_quality_floor:
            return DecisionAction.INSUFFICIENT_EVIDENCE
        return DecisionAction.MONITOR

    def _priority_for(self, decision: DecisionAction, score: float) -> str:
        if decision in {DecisionAction.PURSUE, DecisionAction.LICENSE}:
            return "P1" if score >= 75 else "P2"
        if decision == DecisionAction.PARTNER:
            return "P2" if score >= 65 else "P3"
        if decision == DecisionAction.MONITOR:
            return "P3" if score >= 45 else "P4"
        if decision == DecisionAction.AVOID:
            return "P4"
        return "P4"
