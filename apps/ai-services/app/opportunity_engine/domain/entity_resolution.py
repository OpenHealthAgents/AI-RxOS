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

from pydantic import BaseModel, Field

from app.opportunity_engine.domain.canonical_model import (
    Asset,
    AssetAlias,
    AssetDevelopmentCode,
    AuditEvent,
    AuditEventType,
    normalize_key,
)


class ResolutionMatch(BaseModel):
    asset_id: UUID
    canonical_name: str
    matched_term: str
    match_type: str  # 'DEVELOPMENT_CODE' | 'PRIMARY_NAME' | 'ALIAS' | 'REGISTRY_ID' | 'FUZZY'
    confidence: float
    is_canonical: bool = True


class ResolutionResult(BaseModel):
    query: str
    resolved: bool
    match: Optional[ResolutionMatch] = None
    candidates: List[ResolutionMatch] = Field(default_factory=list)
    disambiguation_notes: Optional[str] = None


class CanonicalAssetResolver:
    """In-memory and transactional repository index for canonical drug asset resolution."""

    def __init__(self) -> None:
        self._assets: Dict[UUID, Asset] = {}
        self._code_index: Dict[str, UUID] = {}  # normalized code -> asset_id
        self._alias_index: Dict[str, UUID] = {}  # normalized alias -> asset_id
        self._name_index: Dict[str, UUID] = {}  # normalized preferred name -> asset_id
        self._audit_events: List[AuditEvent] = []

    def register_asset(self, asset: Asset) -> Asset:
        """Register an asset into the resolver index."""
        self._assets[asset.id] = asset
        norm_name = normalize_key(asset.preferred_name)
        self._name_index[norm_name] = asset.id

        if asset.canonical_slug:
            self._name_index[normalize_key(asset.canonical_slug)] = asset.id

        for dev in asset.development_codes:
            norm_code = normalize_key(dev.code)
            self._code_index[norm_code] = asset.id

        for alias in asset.aliases:
            norm_alias = normalize_key(alias.alias)
            self._alias_index[norm_alias] = asset.id

        return asset

    def get_asset(self, asset_id: UUID) -> Optional[Asset]:
        """Retrieve an asset by ID, following merge pointers if deprecated."""
        asset = self._assets.get(asset_id)
        if asset and asset.is_deprecated and asset.merged_into_asset_id:
            return self._assets.get(asset.merged_into_asset_id)
        return asset

    def resolve(
        self,
        query: str,
        target_hint: Optional[str] = None,
        company_hint: Optional[str] = None,
        min_confidence: float = 0.75,
    ) -> ResolutionResult:
        """Resolve a drug query, development code, or synonym to a canonical asset."""
        norm_q = normalize_key(query)
        if not norm_q:
            return ResolutionResult(query=query, resolved=False)

        # 1. Exact match on Development Code
        if norm_q in self._code_index:
            asset_id = self._code_index[norm_q]
            asset = self.get_asset(asset_id)
            if asset:
                match = ResolutionMatch(
                    asset_id=asset.id,
                    canonical_name=asset.preferred_name,
                    matched_term=query,
                    match_type="DEVELOPMENT_CODE",
                    confidence=1.0,
                )
                return ResolutionResult(query=query, resolved=True, match=match)

        # 2. Exact match on Preferred Name
        if norm_q in self._name_index:
            asset_id = self._name_index[norm_q]
            asset = self.get_asset(asset_id)
            if asset:
                match = ResolutionMatch(
                    asset_id=asset.id,
                    canonical_name=asset.preferred_name,
                    matched_term=query,
                    match_type="PRIMARY_NAME",
                    confidence=1.0,
                )
                return ResolutionResult(query=query, resolved=True, match=match)

        # 3. Exact match on Synonyms / Aliases
        if norm_q in self._alias_index:
            asset_id = self._alias_index[norm_q]
            asset = self.get_asset(asset_id)
            if asset:
                match = ResolutionMatch(
                    asset_id=asset.id,
                    canonical_name=asset.preferred_name,
                    matched_term=query,
                    match_type="ALIAS",
                    confidence=0.98,
                )
                return ResolutionResult(query=query, resolved=True, match=match)

        # 4. Partial / Substring / Code Variations
        # e.g., "BI-0631" matches code "BI-1810631" or "BI0631"
        for code, asset_id in self._code_index.items():
            if norm_q in code or code in norm_q:
                asset = self.get_asset(asset_id)
                if asset:
                    # Check target or company hints if provided
                    score = 0.90
                    if target_hint and asset.primary_target_symbol.upper() == target_hint.upper():
                        score = 0.96
                    if company_hint and company_hint.upper() in asset.owner_company_name.upper():
                        score = 0.98
                    match = ResolutionMatch(
                        asset_id=asset.id,
                        canonical_name=asset.preferred_name,
                        matched_term=code,
                        match_type="DEVELOPMENT_CODE",
                        confidence=score,
                    )
                    return ResolutionResult(query=query, resolved=True, match=match)

        # 5. Fuzzy Match across all known terms
        all_terms = {**self._code_index, **self._name_index, **self._alias_index}
        close_matches = difflib.get_close_matches(norm_q, list(all_terms.keys()), n=3, cutoff=0.7)

        if close_matches:
            best_term = close_matches[0]
            similarity = difflib.SequenceMatcher(None, norm_q, best_term).ratio()
            if similarity >= min_confidence:
                asset_id = all_terms[best_term]
                asset = self.get_asset(asset_id)
                if asset:
                    match = ResolutionMatch(
                        asset_id=asset.id,
                        canonical_name=asset.preferred_name,
                        matched_term=best_term,
                        match_type="FUZZY",
                        confidence=round(similarity, 3),
                    )
                    candidates = [
                        ResolutionMatch(
                            asset_id=self._assets[all_terms[t]].id,
                            canonical_name=self._assets[all_terms[t]].preferred_name,
                            matched_term=t,
                            match_type="FUZZY",
                            confidence=round(difflib.SequenceMatcher(None, norm_q, t).ratio(), 3),
                        )
                        for t in close_matches
                        if all_terms[t] in self._assets
                    ]
                    return ResolutionResult(
                        query=query,
                        resolved=True,
                        match=match,
                        candidates=candidates,
                        disambiguation_notes=f"Fuzzy reconciled with {round(similarity * 100, 1)}% string similarity.",
                    )

        return ResolutionResult(query=query, resolved=False)

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
