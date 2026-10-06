from __future__ import annotations

import hashlib
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from app.opportunity_engine.domain.schemas import StrategicAction
from .models import (
    DerivedFeature,
    EvidenceExtraction,
    EvidenceLineageGraph,
    EvidenceObservation,
    EvidenceRelationship,
    EvidenceSource,
    LineageStep,
    ModelOutput,
    RecommendationLineage,
    RelationshipType,
)


class OrphanedScoreError(ValueError):
    """
    Raised when a derived feature, model score, or recommendation
    lacks provenance lineage linking back to verified evidence observations.
    """
    pass


class EvidenceLineageEngine:
    """
    Guarantees that every scientifically meaningful statement, feature, score,
    and recommendation has unbroken lineage:
    Source -> Extraction -> Normalized Observation -> Derived Feature -> Model Output -> Recommendation.
    Strictly forbids orphaned scientific scores.
    """

    def __init__(self) -> None:
        self.sources: Dict[UUID, EvidenceSource] = {}
        self.extractions: Dict[UUID, EvidenceExtraction] = {}
        self.observations: Dict[UUID, EvidenceObservation] = {}
        self.derived_features: Dict[UUID, DerivedFeature] = {}
        self.model_outputs: Dict[UUID, ModelOutput] = {}
        self.recommendation_lineages: Dict[UUID, RecommendationLineage] = {}
        self.relationships: List[EvidenceRelationship] = []

    def register_source(self, source: EvidenceSource) -> EvidenceSource:
        """Registers a verified evidence source."""
        self.sources[source.id] = source
        return source

    def add_extraction(self, extraction: EvidenceExtraction) -> EvidenceExtraction:
        """Registers an extracted passage and connects it to its parent source."""
        if extraction.source_id not in self.sources:
            raise OrphanedScoreError(f"Extraction {extraction.id} references non-existent source {extraction.source_id}")
        
        self.extractions[extraction.id] = extraction
        self.relationships.append(
            EvidenceRelationship(
                source_entity_id=extraction.source_id,
                source_entity_type="evidence_source",
                target_entity_id=extraction.id,
                target_entity_type="evidence_extraction",
                relationship_type=RelationshipType.SUPPORTS,
                lineage_step=LineageStep.SOURCE_TO_EXTRACTION,
            )
        )
        return extraction

    def add_observation(self, observation: EvidenceObservation) -> EvidenceObservation:
        """
        Registers a normalized scientific observation and connects it to its source extraction.
        """
        if observation.source_id not in self.sources:
            raise OrphanedScoreError(f"Observation {observation.id} references non-existent source {observation.source_id}")
        
        if observation.extraction_id and observation.extraction_id not in self.extractions:
            raise OrphanedScoreError(f"Observation {observation.id} references non-existent extraction {observation.extraction_id}")

        self.observations[observation.id] = observation

        source_id_to_link = observation.extraction_id or observation.source_id
        step = LineageStep.EXTRACTION_TO_OBSERVATION if observation.extraction_id else LineageStep.SOURCE_TO_EXTRACTION
        self.relationships.append(
            EvidenceRelationship(
                source_entity_id=source_id_to_link,
                source_entity_type="evidence_extraction" if observation.extraction_id else "evidence_source",
                target_entity_id=observation.id,
                target_entity_type="evidence_observation",
                relationship_type=RelationshipType.SUPPORTS,
                lineage_step=step,
            )
        )
        return observation

    def derive_feature(
        self,
        asset_id: UUID,
        feature_name: str,
        computed_value: float,
        calculation_formula: str,
        source_observation_ids: List[UUID],
        formula_version: str = "v1.0",
        confidence: float = 0.90,
    ) -> DerivedFeature:
        """
        Calculates a derived feature from normalized observations.
        Strictly rejects feature creation without source observations.
        """
        if not source_observation_ids:
            raise OrphanedScoreError(
                f"Orphaned score rejected: Derived feature '{feature_name}' for asset {asset_id} "
                "must be backed by at least one evidence observation."
            )

        for obs_id in source_observation_ids:
            if obs_id not in self.observations:
                raise OrphanedScoreError(
                    f"Derived feature '{feature_name}' references non-existent observation {obs_id}."
                )

        feature = DerivedFeature(
            asset_id=asset_id,
            feature_name=feature_name,
            computed_value=computed_value,
            calculation_formula=calculation_formula,
            formula_version=formula_version,
            confidence=confidence,
            source_observation_ids=source_observation_ids,
        )
        self.derived_features[feature.id] = feature

        for obs_id in source_observation_ids:
            self.relationships.append(
                EvidenceRelationship(
                    source_entity_id=obs_id,
                    source_entity_type="evidence_observation",
                    target_entity_id=feature.id,
                    target_entity_type="derived_feature",
                    relationship_type=RelationshipType.DERIVES_INTO,
                    lineage_step=LineageStep.OBSERVATION_TO_FEATURE,
                )
            )

        return feature

    def record_model_output(
        self,
        asset_id: UUID,
        model_name: str,
        output_metric: str,
        output_value: float,
        derived_feature_ids: List[UUID],
        model_version: str = "v0.1",
        confidence: float = 0.90,
    ) -> ModelOutput:
        """
        Records a model score or prediction output.
        Strictly rejects model outputs that have no supporting derived features.
        """
        if not derived_feature_ids:
            raise OrphanedScoreError(
                f"Orphaned score rejected: Model output '{output_metric}' ({model_name}) "
                "must be backed by derived features."
            )

        for feat_id in derived_feature_ids:
            if feat_id not in self.derived_features:
                raise OrphanedScoreError(
                    f"Model output '{output_metric}' references non-existent derived feature {feat_id}."
                )

        output = ModelOutput(
            asset_id=asset_id,
            model_name=model_name,
            model_version=model_version,
            output_metric=output_metric,
            output_value=output_value,
            confidence=confidence,
            derived_feature_ids=derived_feature_ids,
        )
        self.model_outputs[output.id] = output

        for feat_id in derived_feature_ids:
            self.relationships.append(
                EvidenceRelationship(
                    source_entity_id=feat_id,
                    source_entity_type="derived_feature",
                    target_entity_id=output.id,
                    target_entity_type="model_output",
                    relationship_type=RelationshipType.DERIVES_INTO,
                    lineage_step=LineageStep.FEATURE_TO_MODEL_OUTPUT,
                )
            )

        return output

    def link_recommendation(
        self,
        recommendation_id: UUID,
        asset_id: UUID,
        action: StrategicAction,
        model_output_ids: List[UUID],
    ) -> RecommendationLineage:
        """
        Connects a final strategic recommendation to its underlying model outputs.
        Computes an immutable cryptographic lineage hash.
        """
        if not model_output_ids:
            raise OrphanedScoreError(
                f"Orphaned decision rejected: Recommendation {recommendation_id} "
                "must be backed by at least one model output."
            )

        for out_id in model_output_ids:
            if out_id not in self.model_outputs:
                raise OrphanedScoreError(
                    f"Recommendation {recommendation_id} references non-existent model output {out_id}."
                )

        # Generate cryptographic lineage hash
        hasher = hashlib.sha256()
        hasher.update(str(recommendation_id).encode("utf-8"))
        for out_id in sorted(model_output_ids, key=lambda x: str(x)):
            hasher.update(str(out_id).encode("utf-8"))
        lineage_hash = hasher.hexdigest()

        rec_lineage = RecommendationLineage(
            recommendation_id=recommendation_id,
            model_output_id=model_output_ids[0],
            asset_id=asset_id,
            action=action,
            lineage_hash=lineage_hash,
        )
        self.recommendation_lineages[recommendation_id] = rec_lineage

        for out_id in model_output_ids:
            self.relationships.append(
                EvidenceRelationship(
                    source_entity_id=out_id,
                    source_entity_type="model_output",
                    target_entity_id=recommendation_id,
                    target_entity_type="recommendation",
                    relationship_type=RelationshipType.DERIVES_INTO,
                    lineage_step=LineageStep.MODEL_OUTPUT_TO_RECOMMENDATION,
                )
            )

        return rec_lineage

    def verify_lineage_integrity(self, recommendation_id: UUID) -> Tuple[bool, List[str]]:
        """
        Validates that a recommendation has a complete, unbroken graph traversal
        all the way back to root evidence sources. Returns (is_valid, missing_or_orphaned_items).
        """
        if recommendation_id not in self.recommendation_lineages:
            return False, ["Recommendation lineage record not found"]

        orphans: List[str] = []
        rec_lineage = self.recommendation_lineages[recommendation_id]
        
        # Traverse model outputs
        connected_outputs = [
            out for out in self.model_outputs.values()
            if any(
                r.source_entity_id == out.id and r.target_entity_id == recommendation_id
                for r in self.relationships
            )
        ]

        if not connected_outputs:
            orphans.append(f"No model outputs connected to recommendation {recommendation_id}")

        for output in connected_outputs:
            if not output.derived_feature_ids:
                orphans.append(f"Model output {output.output_metric} has no derived features")
                continue

            for feat_id in output.derived_feature_ids:
                feat = self.derived_features.get(feat_id)
                if not feat:
                    orphans.append(f"Derived feature {feat_id} missing in registry")
                    continue
                if not feat.source_observation_ids:
                    orphans.append(f"Derived feature {feat.feature_name} has no source observations")
                    continue

                for obs_id in feat.source_observation_ids:
                    obs = self.observations.get(obs_id)
                    if not obs:
                        orphans.append(f"Observation {obs_id} missing in registry")
                        continue
                    if obs.source_id not in self.sources:
                        orphans.append(f"Observation {obs.id} points to non-existent source {obs.source_id}")

        is_complete = len(orphans) == 0
        return is_complete, orphans

    def get_lineage_graph(self, recommendation_id: UUID, asset_id: UUID) -> EvidenceLineageGraph:
        """
        Extracts the sub-graph for a given recommendation, returning all connected
        sources, extractions, observations, features, model outputs, and relationships.
        """
        is_complete, orphans = self.verify_lineage_integrity(recommendation_id)

        # Collect relevant IDs
        relevant_outputs = [
            out for out in self.model_outputs.values()
            if any(
                r.source_entity_id == out.id and r.target_entity_id == recommendation_id
                for r in self.relationships
            )
        ]

        feature_ids: Set[UUID] = set()
        for out in relevant_outputs:
            feature_ids.update(out.derived_feature_ids)

        relevant_features = [self.derived_features[fid] for fid in feature_ids if fid in self.derived_features]

        obs_ids: Set[UUID] = set()
        for feat in relevant_features:
            obs_ids.update(feat.source_observation_ids)

        relevant_obs = [self.observations[oid] for oid in obs_ids if oid in self.observations]

        extraction_ids: Set[UUID] = set()
        source_ids: Set[UUID] = set()
        for obs in relevant_obs:
            if obs.extraction_id:
                extraction_ids.add(obs.extraction_id)
            source_ids.add(obs.source_id)

        relevant_extractions = [self.extractions[eid] for eid in extraction_ids if eid in self.extractions]
        relevant_sources = [self.sources[sid] for sid in source_ids if sid in self.sources]

        relevant_entity_ids = (
            {recommendation_id}
            | {out.id for out in relevant_outputs}
            | feature_ids
            | obs_ids
            | extraction_ids
            | source_ids
        )

        subgraph_relationships = [
            r for r in self.relationships
            if r.source_entity_id in relevant_entity_ids and r.target_entity_id in relevant_entity_ids
        ]

        return EvidenceLineageGraph(
            recommendation_id=recommendation_id,
            asset_id=asset_id,
            sources=relevant_sources,
            extractions=relevant_extractions,
            observations=relevant_obs,
            derived_features=relevant_features,
            model_outputs=relevant_outputs,
            relationships=subgraph_relationships,
            is_lineage_complete=is_complete,
            orphaned_components=orphans,
        )
