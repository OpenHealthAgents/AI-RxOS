"""Entity Resolution Engine for Canonical Biomedical Asset Reconciliation.

Guarantees that a physical drug asset with multiple historical development codes,
company codes, generic names, and brand synonyms resolves to a single canonical entity.
Prevents duplicate asset creation when incoming literature, trials, or patents cite
divergent developmental aliases.
"""

from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from enum import StrEnum
from pydantic import BaseModel, Field

from app.opportunity_engine.domain.canonical_model import (
    Asset,
    AssetAlias,
    AssetDevelopmentCode,
    AssetIdentity,
    AssetRelationship,
    AuditEvent,
    AuditEventType,
    normalize_key,
)


class ResolutionMatchType(StrEnum):
    PRIMARY_NAME = "PRIMARY_NAME"
    GENERIC_NAME = "GENERIC_NAME"
    DEVELOPMENT_CODE = "DEVELOPMENT_CODE"
    COMPANY_CODE = "COMPANY_CODE"
    FORMER_NAME = "FORMER_NAME"
    ALIAS = "ALIAS"
    REGISTRY_ID = "REGISTRY_ID"
    NORMALIZED_TOKEN = "NORMALIZED_TOKEN"
    CONTEXTUAL_MATCH = "CONTEXTUAL_MATCH"
    FUZZY = "FUZZY"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class ResolutionMatch(BaseModel):
    asset_id: UUID
    canonical_name: str
    matched_term: str
    match_type: str  # ResolutionMatchType value
    confidence: float
    is_canonical: bool = True
    target: str = ""
    modality: str = ""
    owner: Optional[str] = None
    stage: Optional[str] = None


class ResolutionResult(BaseModel):
    query: str
    resolved: bool
    confidence: float = 0.0
    match_type: str = ResolutionMatchType.UNRESOLVED
    match: Optional[ResolutionMatch] = None
    candidates: List[ResolutionMatch] = Field(default_factory=list)
    disambiguation_notes: Optional[str] = None


class CanonicalAssetResolver:
    """In-memory and transactional repository index for canonical drug asset resolution."""

    def __init__(self) -> None:
        self._assets: Dict[UUID, Asset] = {}
        self._code_index: Dict[str, UUID] = {}  # normalized development code -> asset_id
        self._generic_name_index: Dict[str, UUID] = {}  # normalized generic name -> asset_id
        self._former_name_index: Dict[str, UUID] = {}  # normalized former name -> asset_id
        self._company_code_index: Dict[str, UUID] = {}  # normalized company code -> asset_id
        self._alias_index: Dict[str, UUID] = {}  # normalized alias -> asset_id
        self._name_index: Dict[str, UUID] = {}  # normalized preferred name -> asset_id
        self._token_index: Dict[str, Set[UUID]] = {}  # all normalized identity tokens -> set of asset_ids
        self._registry_index: Dict[str, UUID] = {}  # external registry IDs (ChEMBL, CAS, etc.) -> asset_id
        self._audit_events: List[AuditEvent] = []

    def register_asset(self, asset: Asset) -> Asset:
        """Register an asset into the resolver index across all multi-dimensional identity tokens."""
        self._assets[asset.id] = asset

        # 1. Preferred Name & Canonical Slug
        norm_name = normalize_key(asset.preferred_name)
        if norm_name:
            self._name_index[norm_name] = asset.id
            self._add_token(norm_name, asset.id)

        if asset.canonical_slug:
            norm_slug = normalize_key(asset.canonical_slug)
            if norm_slug:
                self._name_index[norm_slug] = asset.id
                self._add_token(norm_slug, asset.id)

        # 2. Generic Name
        if asset.generic_name:
            norm_gen = normalize_key(asset.generic_name)
            if norm_gen:
                self._generic_name_index[norm_gen] = asset.id
                self._add_token(norm_gen, asset.id)

        # 3. Development Codes
        if asset.development_code:
            norm_dc = normalize_key(asset.development_code)
            if norm_dc:
                self._code_index[norm_dc] = asset.id
                self._add_token(norm_dc, asset.id)

        for dev in asset.development_codes:
            norm_code = normalize_key(dev.code)
            if norm_code:
                self._code_index[norm_code] = asset.id
                self._add_token(norm_code, asset.id)

        # 4. Former Names
        for fn in asset.former_names:
            norm_fn = normalize_key(fn)
            if norm_fn:
                self._former_name_index[norm_fn] = asset.id
                self._add_token(norm_fn, asset.id)

        # 5. Company Codes
        for cc in asset.company_codes:
            norm_cc = normalize_key(cc)
            if norm_cc:
                self._company_code_index[norm_cc] = asset.id
                self._add_token(norm_cc, asset.id)

        # 6. Aliases & Synonyms
        for alias in asset.aliases:
            norm_alias = normalize_key(alias.alias)
            if norm_alias:
                self._alias_index[norm_alias] = asset.id
                self._add_token(norm_alias, asset.id)

        # 7. Identity Registry Identifiers
        if asset.identity:
            for reg_val in asset.identity.registry_identifiers.values():
                norm_reg = normalize_key(reg_val)
                if norm_reg:
                    self._registry_index[norm_reg] = asset.id
                    self._add_token(norm_reg, asset.id)

        return asset

    def _add_token(self, token: str, asset_id: UUID) -> None:
        if token not in self._token_index:
            self._token_index[token] = set()
        self._token_index[token].add(asset_id)

    def get_asset(self, asset_id: UUID) -> Optional[Asset]:
        """Retrieve an asset by ID, following merge pointers if deprecated."""
        asset = self._assets.get(asset_id)
        if asset and asset.is_deprecated and asset.merged_into_asset_id:
            return self._assets.get(asset.merged_into_asset_id)
        return asset

    def _build_match(self, asset: Asset, matched_term: str, match_type: str, confidence: float) -> ResolutionMatch:
        return ResolutionMatch(
            asset_id=asset.id,
            canonical_name=asset.preferred_name,
            matched_term=matched_term,
            match_type=match_type,
            confidence=round(confidence, 3),
            target=asset.target or asset.primary_target_symbol,
            modality=str(asset.modality.value) if asset.modality else "",
            owner=asset.owner or asset.owner_company_name,
            stage=str(asset.stage.value) if asset.stage else "",
        )

    def resolve(
        self,
        query: str,
        target_hint: Optional[str] = None,
        company_hint: Optional[str] = None,
        min_confidence: float = 0.75,
    ) -> ResolutionResult:
        """Resolve a drug query, developmental code, or synonym to a canonical asset with calibrated confidence."""
        norm_q = normalize_key(query)
        if not norm_q:
            return ResolutionResult(query=query, resolved=False, match_type=ResolutionMatchType.UNRESOLVED)

        # 1. Exact match on Primary Name (Confidence: 1.0)
        if norm_q in self._name_index:
            asset = self.get_asset(self._name_index[norm_q])
            if asset:
                match = self._build_match(asset, query, ResolutionMatchType.PRIMARY_NAME, 1.0)
                return ResolutionResult(
                    query=query,
                    resolved=True,
                    confidence=1.0,
                    match_type=ResolutionMatchType.PRIMARY_NAME,
                    match=match,
                )

        # 2. Exact match on Generic Name (Confidence: 1.0)
        if norm_q in self._generic_name_index:
            asset = self.get_asset(self._generic_name_index[norm_q])
            if asset:
                match = self._build_match(asset, query, ResolutionMatchType.GENERIC_NAME, 1.0)
                return ResolutionResult(
                    query=query,
                    resolved=True,
                    confidence=1.0,
                    match_type=ResolutionMatchType.GENERIC_NAME,
                    match=match,
                )

        # 3. Exact match on Development Code (Confidence: 1.0)
        if norm_q in self._code_index:
            asset = self.get_asset(self._code_index[norm_q])
            if asset:
                match = self._build_match(asset, query, ResolutionMatchType.DEVELOPMENT_CODE, 1.0)
                return ResolutionResult(
                    query=query,
                    resolved=True,
                    confidence=1.0,
                    match_type=ResolutionMatchType.DEVELOPMENT_CODE,
                    match=match,
                )

        # 4. Exact match on Registry ID (Confidence: 1.0)
        if norm_q in self._registry_index:
            asset = self.get_asset(self._registry_index[norm_q])
            if asset:
                match = self._build_match(asset, query, ResolutionMatchType.REGISTRY_ID, 1.0)
                return ResolutionResult(
                    query=query,
                    resolved=True,
                    confidence=1.0,
                    match_type=ResolutionMatchType.REGISTRY_ID,
                    match=match,
                )

        # 5. Exact match on Company Code (Confidence: 0.98)
        if norm_q in self._company_code_index:
            asset = self.get_asset(self._company_code_index[norm_q])
            if asset:
                match = self._build_match(asset, query, ResolutionMatchType.COMPANY_CODE, 0.98)
                return ResolutionResult(
                    query=query,
                    resolved=True,
                    confidence=0.98,
                    match_type=ResolutionMatchType.COMPANY_CODE,
                    match=match,
                )

        # 6. Exact match on Former Name (Confidence: 0.95)
        if norm_q in self._former_name_index:
            asset = self.get_asset(self._former_name_index[norm_q])
            if asset:
                match = self._build_match(asset, query, ResolutionMatchType.FORMER_NAME, 0.95)
                return ResolutionResult(
                    query=query,
                    resolved=True,
                    confidence=0.95,
                    match_type=ResolutionMatchType.FORMER_NAME,
                    match=match,
                )

        # 7. Exact match on Synonyms / Aliases (Confidence: 0.95)
        if norm_q in self._alias_index:
            asset = self.get_asset(self._alias_index[norm_q])
            if asset:
                match = self._build_match(asset, query, ResolutionMatchType.ALIAS, 0.95)
                return ResolutionResult(
                    query=query,
                    resolved=True,
                    confidence=0.95,
                    match_type=ResolutionMatchType.ALIAS,
                    match=match,
                )

        # 8. Normalized Token Set Match (e.g. "ZW-25" vs "ZW25", "PB-272" vs "PB272")
        if norm_q in self._token_index:
            matching_ids = self._token_index[norm_q]
            if len(matching_ids) == 1:
                asset_id = next(iter(matching_ids))
                asset = self.get_asset(asset_id)
                if asset:
                    match = self._build_match(asset, query, ResolutionMatchType.NORMALIZED_TOKEN, 0.98)
                    return ResolutionResult(
                        query=query,
                        resolved=True,
                        confidence=0.98,
                        match_type=ResolutionMatchType.NORMALIZED_TOKEN,
                        match=match,
                    )
            elif len(matching_ids) > 1:
                # Ambiguous collision
                candidates = [
                    self._build_match(self.get_asset(aid), query, ResolutionMatchType.NORMALIZED_TOKEN, 0.85)
                    for aid in matching_ids
                    if self.get_asset(aid)
                ]
                return ResolutionResult(
                    query=query,
                    resolved=False,
                    confidence=0.85,
                    match_type=ResolutionMatchType.AMBIGUOUS,
                    candidates=candidates,
                    disambiguation_notes=f"Multiple assets ({len(candidates)}) match normalized token '{norm_q}'.",
                )

        # 9. Partial / Code Substring with Contextual Agreement
        # e.g., "BI-0631" matches code "BI-1810631"
        for code, asset_id in self._code_index.items():
            if norm_q in code or code in norm_q:
                asset = self.get_asset(asset_id)
                if asset:
                    score = 0.90
                    target_match = bool(target_hint and asset.target.upper() == target_hint.upper())
                    company_match = bool(company_hint and (asset.owner and company_hint.upper() in asset.owner.upper()))

                    if target_match and company_match:
                        score = 0.98
                    elif target_match or company_match:
                        score = 0.96

                    match = self._build_match(asset, code, ResolutionMatchType.CONTEXTUAL_MATCH, score)
                    return ResolutionResult(
                        query=query,
                        resolved=True,
                        confidence=score,
                        match_type=ResolutionMatchType.CONTEXTUAL_MATCH,
                        match=match,
                        disambiguation_notes="Resolved via substring pattern and contextual corroboration.",
                    )

        # 10. Fuzzy Match across all known terms with Contextual Boosts
        all_terms = {**self._code_index, **self._name_index, **self._alias_index, **self._generic_name_index}
        close_matches = difflib.get_close_matches(norm_q, list(all_terms.keys()), n=5, cutoff=0.7)

        if close_matches:
            candidate_matches: List[ResolutionMatch] = []
            for t in close_matches:
                asset_id = all_terms[t]
                asset = self.get_asset(asset_id)
                if not asset:
                    continue

                raw_sim = difflib.SequenceMatcher(None, norm_q, t).ratio()
                boosted_sim = raw_sim

                # Boost for target agreement
                if target_hint and asset.target and asset.target.upper() == target_hint.upper():
                    boosted_sim = min(boosted_sim + 0.05, 0.95)
                # Boost for company agreement
                if company_hint and asset.owner and company_hint.upper() in asset.owner.upper():
                    boosted_sim = min(boosted_sim + 0.05, 0.95)

                candidate_matches.append(
                    self._build_match(asset, t, ResolutionMatchType.FUZZY, boosted_sim)
                )

            # Sort by confidence descending
            candidate_matches.sort(key=lambda m: m.confidence, reverse=True)

            if candidate_matches and candidate_matches[0].confidence >= min_confidence:
                best_match = candidate_matches[0]

                # Check for ambiguity: if second candidate is within 0.03 margin and belongs to different asset
                if len(candidate_matches) > 1:
                    second_match = candidate_matches[1]
                    if (
                        second_match.asset_id != best_match.asset_id
                        and (best_match.confidence - second_match.confidence) < 0.03
                    ):
                        return ResolutionResult(
                            query=query,
                            resolved=False,
                            confidence=best_match.confidence,
                            match_type=ResolutionMatchType.AMBIGUOUS,
                            candidates=candidate_matches[:3],
                            disambiguation_notes=f"Ambiguous fuzzy match between '{best_match.canonical_name}' ({best_match.confidence}) and '{second_match.canonical_name}' ({second_match.confidence}).",
                        )

                return ResolutionResult(
                    query=query,
                    resolved=True,
                    confidence=best_match.confidence,
                    match_type=ResolutionMatchType.FUZZY,
                    match=best_match,
                    candidates=candidate_matches,
                    disambiguation_notes=f"Fuzzy reconciled with {round(best_match.confidence * 100, 1)}% confidence.",
                )

        return ResolutionResult(query=query, resolved=False, match_type=ResolutionMatchType.UNRESOLVED)

    def resolve_multiple(
        self,
        queries: List[str],
        target_hint: Optional[str] = None,
        company_hint: Optional[str] = None,
    ) -> Dict[str, ResolutionResult]:
        """Resolves a list of query names or codes in batch mode."""
        return {q: self.resolve(q, target_hint=target_hint, company_hint=company_hint) for q in queries}

    def consolidate_names(
        self,
        names: List[str],
        target_hint: Optional[str] = None,
        company_hint: Optional[str] = None,
    ) -> Tuple[Optional[Asset], float, Dict[str, ResolutionResult]]:
        """Resolves multiple names and confirms whether they all consolidate into a single canonical asset.

        Returns (canonical_asset, joint_confidence, per_query_results).
        """
        results = self.resolve_multiple(names, target_hint=target_hint, company_hint=company_hint)
        resolved_asset_ids: Set[UUID] = set()
        confidences: List[float] = []

        for q, res in results.items():
            if res.resolved and res.match:
                resolved_asset_ids.add(res.match.asset_id)
                confidences.append(res.confidence)

        if len(resolved_asset_ids) == 1:
            canonical_asset = self.get_asset(next(iter(resolved_asset_ids)))
            joint_conf = round(sum(confidences) / len(confidences), 3) if confidences else 1.0
            return canonical_asset, joint_conf, results

        return None, 0.0, results

    def ingest_or_resolve(
        self,
        raw_name: str,
        development_codes: Optional[List[str]] = None,
        aliases: Optional[List[str]] = None,
        target: Optional[str] = None,
        owner_company: Optional[str] = None,
        source_ref: Optional[str] = None,
        actor_name: str = "Automated Ingestion Pipeline",
    ) -> Tuple[Asset, bool, AuditEvent]:
        """Ingests a record, resolving against existing assets to prevent duplicate creation.

        If a match is found, links any new codes/aliases to the existing asset and returns (asset, False, audit_event).
        If no match exists, registers a new canonical asset and returns (asset, True, audit_event).
        """
        development_codes = development_codes or []
        aliases = aliases or []

        # Check raw_name and all candidate codes
        resolved_asset: Optional[Asset] = None
        for candidate in [raw_name, *development_codes, *aliases]:
            res = self.resolve(candidate, target_hint=target, company_hint=owner_company)
            if res.resolved and res.match and res.match.confidence >= 0.85:
                resolved_asset = self.get_asset(res.match.asset_id)
                if resolved_asset:
                    break

        if resolved_asset is not None:
            # Asset already exists! NEVER duplicate. Attach any novel codes or aliases.
            attached_codes = []
            for code in development_codes:
                norm_c = normalize_key(code)
                if norm_c and norm_c not in self._code_index:
                    dev_obj = AssetDevelopmentCode(
                        asset_id=resolved_asset.id,
                        code=code,
                        notes=f"Discovered via {source_ref or 'literature ingestion'}",
                    )
                    resolved_asset.development_codes.append(dev_obj)
                    self._code_index[norm_c] = resolved_asset.id
                    attached_codes.append(code)

            attached_aliases = []
            for alias in [raw_name, *aliases]:
                norm_a = normalize_key(alias)
                if norm_a and norm_a not in self._alias_index and norm_a != normalize_key(resolved_asset.preferred_name):
                    alias_obj = AssetAlias(
                        asset_id=resolved_asset.id,
                        alias=alias,
                    )
                    resolved_asset.aliases.append(alias_obj)
                    self._alias_index[norm_a] = resolved_asset.id
                    attached_aliases.append(alias)

            audit_event = AuditEvent(
                event_type=AuditEventType.ALIAS_ATTACHED if attached_aliases else AuditEventType.DEV_CODE_ATTACHED,
                entity_id=resolved_asset.id,
                entity_type="Asset",
                actor_name=actor_name,
                summary=f"Linked aliases/codes to canonical asset '{resolved_asset.preferred_name}' without duplication.",
                metadata={
                    "query_term": raw_name,
                    "attached_codes": attached_codes,
                    "attached_aliases": attached_aliases,
                    "source_ref": source_ref,
                },
            )
            self._audit_events.append(audit_event)
            return resolved_asset, False, audit_event

        # No match found: Create new canonical asset
        new_asset = Asset(
            preferred_name=raw_name,
            primary_target_symbol=target or "HER2",
            owner_company_name=owner_company or "Unknown Originator",
        )

        for code in development_codes:
            dev_obj = AssetDevelopmentCode(
                asset_id=new_asset.id,
                code=code,
                is_primary=True,
            )
            new_asset.development_codes.append(dev_obj)

        for alias in aliases:
            alias_obj = AssetAlias(
                asset_id=new_asset.id,
                alias=alias,
            )
            new_asset.aliases.append(alias_obj)

        self.register_asset(new_asset)

        audit_event = AuditEvent(
            event_type=AuditEventType.ASSET_CREATED,
            entity_id=new_asset.id,
            entity_type="Asset",
            actor_name=actor_name,
            summary=f"Created canonical asset '{new_asset.preferred_name}' with {len(development_codes)} development codes.",
            metadata={
                "preferred_name": new_asset.preferred_name,
                "development_codes": development_codes,
                "source_ref": source_ref,
            },
        )
        self._audit_events.append(audit_event)
        return new_asset, True, audit_event

    def merge_assets(
        self,
        source_asset_id: UUID,
        target_asset_id: UUID,
        rationale: str,
        actor_name: str = "Translational Committee",
    ) -> Tuple[Asset, AuditEvent]:
        """Merge a duplicate or newly reconciled asset into a canonical target asset.

        All aliases, development codes, evidence, and outcomes are re-linked, and
        the source asset is flagged as deprecated.
        """
        source = self._assets.get(source_asset_id)
        target = self._assets.get(target_asset_id)

        if not source or not target:
            raise ValueError("Both source and target assets must exist for merging.")

        # Re-link development codes
        for code in source.development_codes:
            code.asset_id = target.id
            target.development_codes.append(code)
            self._code_index[normalize_key(code.code)] = target.id

        # Re-link aliases
        source_name_alias = AssetAlias(
            asset_id=target.id,
            alias=source.preferred_name,
        )
        target.aliases.append(source_name_alias)
        self._alias_index[normalize_key(source.preferred_name)] = target.id

        for alias in source.aliases:
            alias.asset_id = target.id
            target.aliases.append(alias)
            self._alias_index[normalize_key(alias.alias)] = target.id

        # Re-link evidence & outcomes
        for ev in source.evidence:
            ev.asset_id = target.id
            target.evidence.append(ev)

        for out in source.outcomes:
            out.asset_id = target.id
            target.outcomes.append(out)

        # Deprecate source
        source.is_deprecated = True
        source.merged_into_asset_id = target.id

        audit_event = AuditEvent(
            event_type=AuditEventType.ASSET_MERGED,
            entity_id=target.id,
            entity_type="Asset",
            actor_name=actor_name,
            summary=f"Merged asset '{source.preferred_name}' into canonical asset '{target.preferred_name}'.",
            metadata={
                "source_asset_id": str(source.id),
                "source_asset_name": source.preferred_name,
                "target_asset_id": str(target.id),
                "target_asset_name": target.preferred_name,
                "rationale": rationale,
            },
        )
        self._audit_events.append(audit_event)
        return target, audit_event

    def get_audit_trail(self, asset_id: Optional[UUID] = None) -> List[AuditEvent]:
        """Retrieve complete audit trail or events filtered by asset."""
        if asset_id is None:
            return list(self._audit_events)
        return [e for e in self._audit_events if e.entity_id == asset_id]
