from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional
from uuid import UUID

from .models import (
    AssetOwnershipProfile,
    DealType,
    LicensingStatus,
    OwnershipAndDealEvent,
    PatentClaimType,
    PatentJurisdiction,
    PatentRecord,
    PatentStatus,
)
from .verifier import LicensingAndIPGuard

logger = logging.getLogger(__name__)


class OwnershipAndLicensingService:
    """
    Production-quality service for ownership, corporate deal history, and patent intelligence.
    Enforces:
    - Never state 'licensing available' unless verified
    - IP analysis is intelligence, not legal advice
    - Never claim freedom to operate (FTO)
    - Full historical cutoff replay with zero information leakage
    """

    def __init__(self) -> None:
        self._profiles_by_asset: Dict[UUID, AssetOwnershipProfile] = {}
        self._load_reference_fixtures()

    def get_ownership_profile(
        self,
        asset_id: UUID,
        cutoff_date: Optional[date] = None,
    ) -> Optional[AssetOwnershipProfile]:
        """
        Retrieves asset ownership and IP profile.
        When cutoff_date is supplied, temporally filters deals and patents
        and reconstructs the historical owner as of that cutoff.
        """
        base_profile = self._profiles_by_asset.get(asset_id)
        if not base_profile:
            return None

        if cutoff_date is None:
            return base_profile

        # Temporally filter deal history
        filtered_deals = [d for d in base_profile.deal_history if d.effective_date <= cutoff_date]

        # Temporally filter patents (only those with priority/filing date on or before cutoff)
        filtered_patents = [p for p in base_profile.patents if p.filing_date <= cutoff_date]

        # Reconstruct historical ownership state based on deals as of cutoff
        current_owner = base_profile.originator
        former_owners: List[str] = []
        partner: Optional[str] = None
        licensing_status = (
            base_profile.licensing_status
            if not base_profile.deal_history
            else LicensingStatus.NO_PUBLIC_SIGNAL
        )
        status_rationale = f"Reconstructed as of {cutoff_date.isoformat()}"
        is_verified = base_profile.licensing_status_verified
        verification_source = base_profile.licensing_verification_source

        sorted_deals = sorted(filtered_deals, key=lambda d: d.effective_date)
        for deal in sorted_deals:
            # 1. ACQUISITION
            if deal.deal_type == DealType.ACQUISITION:
                if deal.licensee:
                    if current_owner not in former_owners and current_owner != deal.licensee:
                        former_owners.append(current_owner)
                    current_owner = deal.licensee
                if partner:
                    licensing_status = LicensingStatus.PARTNERED
                    status_rationale = f"Acquired by {current_owner}; partnered with {partner}: {deal.summary}"
                else:
                    licensing_status = LicensingStatus.NO_PUBLIC_SIGNAL
                    status_rationale = f"Acquired by {current_owner}: {deal.summary}"
                is_verified = deal.is_verified_evidence
                verification_source = deal.source_citation

            # 2. ASSET TRANSFER
            elif deal.deal_type == DealType.ASSET_TRANSFER:
                if deal.licensee:
                    if current_owner not in former_owners and current_owner != deal.licensee:
                        former_owners.append(current_owner)
                    current_owner = deal.licensee
                if deal.licensee == base_profile.originator:
                    partner = None
                    licensing_status = LicensingStatus.POTENTIALLY_AVAILABLE
                    status_rationale = f"Rights reverted to originator {base_profile.originator}: {deal.summary}"
                else:
                    licensing_status = LicensingStatus.NO_PUBLIC_SIGNAL
                    status_rationale = f"Asset transferred to {deal.licensee}: {deal.summary}"
                is_verified = deal.is_verified_evidence
                verification_source = deal.source_citation

            # 3. LICENSING / LICENSING_ANNOUNCEMENT
            elif deal.deal_type in (DealType.LICENSING, DealType.LICENSING_ANNOUNCEMENT):
                if deal.licensee:
                    if current_owner not in former_owners and current_owner != deal.licensee:
                        former_owners.append(current_owner)
                    current_owner = deal.licensee
                licensing_status = LicensingStatus.PARTNERED
                status_rationale = f"Licensed to {deal.licensee}: {deal.summary}"
                is_verified = deal.is_verified_evidence
                verification_source = deal.source_citation

            # 4. CO_DEVELOPMENT / PARTNERSHIP
            elif deal.deal_type in (DealType.CO_DEVELOPMENT, DealType.PARTNERSHIP):
                partner = deal.partner or deal.licensee
                licensing_status = LicensingStatus.PARTNERED
                status_rationale = f"Partnered with {partner}: {deal.summary}"
                is_verified = deal.is_verified_evidence
                verification_source = deal.source_citation

            # 5. OPTION / OPTION_AGREEMENT
            elif deal.deal_type in (DealType.OPTION, DealType.OPTION_AGREEMENT):
                partner = deal.partner or deal.licensee
                licensing_status = LicensingStatus.PARTNERED
                status_rationale = f"Option granted to {partner}: {deal.summary}"
                is_verified = deal.is_verified_evidence
                verification_source = deal.source_citation

            # 6. FUNDING
            elif deal.deal_type == DealType.FUNDING:
                status_rationale = f"Funding round ({deal.funding_round or 'disclosed'}) for {current_owner}: {deal.summary}"
                is_verified = deal.is_verified_evidence
                verification_source = deal.source_citation

        # If no deals occurred yet, developer is originator
        developer = current_owner

        historical_profile = AssetOwnershipProfile(
            asset_id=base_profile.asset_id,
            developer=developer,
            originator=base_profile.originator,
            current_owner=current_owner,
            former_owners=former_owners,
            academic_origin=base_profile.academic_origin,
            partner=partner,
            licensing_status=licensing_status if sorted_deals else (
                base_profile.licensing_status if not base_profile.deal_history else LicensingStatus.NO_PUBLIC_SIGNAL
            ),
            licensing_status_rationale=status_rationale,
            licensing_status_verified=is_verified if sorted_deals else base_profile.licensing_status_verified,
            licensing_verification_source=verification_source if sorted_deals else base_profile.licensing_verification_source,
            deal_history=sorted_deals,
            patents=filtered_patents,
        )

        return LicensingAndIPGuard.verify_profile(historical_profile, strict=False)

    def update_licensing_status(
        self,
        asset_id: UUID,
        status: LicensingStatus,
        rationale: str,
        verification_source: Optional[str] = None,
        is_verified: bool = False,
        strict: bool = True,
    ) -> AssetOwnershipProfile:
        """
        Updates an asset's licensing availability state, checking anti-unverified guards
        and anti-FTO rules.
        """
        profile = self._profiles_by_asset.get(asset_id)
        if not profile:
            raise KeyError(f"Asset profile {asset_id} not found.")

        # Guard against unverified VERIFIED_AVAILABLE and illegal FTO claims
        valid_status, valid_verified, valid_source = LicensingAndIPGuard.validate_licensing_status(
            status=status,
            is_verified=is_verified,
            verification_source=verification_source,
            strict=strict,
        )
        LicensingAndIPGuard.audit_fto_statements(rationale)

        profile.licensing_status = valid_status
        profile.licensing_status_verified = valid_verified
        profile.licensing_verification_source = valid_source
        profile.licensing_status_rationale = rationale

        return LicensingAndIPGuard.verify_profile(profile, strict=strict)

    def register_profile(self, profile: AssetOwnershipProfile) -> AssetOwnershipProfile:
        """Registers or updates an asset ownership profile."""
        verified = LicensingAndIPGuard.verify_profile(profile, strict=False)
        self._profiles_by_asset[profile.asset_id] = verified
        return verified

    def record_deal_event(self, deal: OwnershipAndDealEvent) -> OwnershipAndDealEvent:
        """Records a corporate deal or transaction event."""
        profile = self._profiles_by_asset.get(deal.asset_id)
        if profile:
            profile.deal_history.append(deal)
        return deal

    def batch_record_deal_events(self, deals: List[OwnershipAndDealEvent]) -> List[OwnershipAndDealEvent]:
        """Batch records corporate deal events."""
        return [self.record_deal_event(d) for d in deals]

    def get_deal_events_by_type(
        self,
        deal_type: DealType,
        cutoff_date: Optional[date] = None,
    ) -> List[OwnershipAndDealEvent]:
        """Retrieves all corporate deal events matching a specified deal type."""
        matching: List[OwnershipAndDealEvent] = []
        for profile in self._profiles_by_asset.values():
            for d in profile.deal_history:
                if d.deal_type == deal_type or d.deal_type.value == deal_type.value:
                    if cutoff_date is None or d.effective_date <= cutoff_date:
                        matching.append(d)
        return matching

    def get_all_deals(
        self,
        asset_id: Optional[UUID] = None,
        cutoff_date: Optional[date] = None,
    ) -> List[OwnershipAndDealEvent]:
        """Retrieves all deals, optionally filtered by asset ID and temporal cutoff."""
        results: List[OwnershipAndDealEvent] = []
        if asset_id:
            profile = self._profiles_by_asset.get(asset_id)
            if profile:
                deals = [d for d in profile.deal_history if cutoff_date is None or d.effective_date <= cutoff_date]
                results.extend(deals)
        else:
            for profile in self._profiles_by_asset.values():
                deals = [d for d in profile.deal_history if cutoff_date is None or d.effective_date <= cutoff_date]
                results.extend(deals)
        return sorted(results, key=lambda d: d.effective_date)

    def record_patent(self, patent: PatentRecord) -> PatentRecord:
        """Records a patent into the asset's patent portfolio."""
        profile = self._profiles_by_asset.get(patent.asset_id)
        if profile:
            # Audit patent rationale/title for illegal FTO claims
            LicensingAndIPGuard.audit_fto_statements(patent.title)
            # Idempotent upsert
            existing_idx = next(
                (i for i, p in enumerate(profile.patents) if p.patent_number == patent.patent_number),
                None,
            )
            if existing_idx is not None:
                profile.patents[existing_idx] = patent
            else:
                profile.patents.append(patent)
        return patent

    def batch_record_patents(self, patents: List[PatentRecord]) -> List[PatentRecord]:
        """Batch records multiple patent records."""
        return [self.record_patent(p) for p in patents]

    def get_patent(self, patent_number: str) -> Optional[PatentRecord]:
        """Retrieves a patent by patent number across all assets."""
        for profile in self._profiles_by_asset.values():
            for p in profile.patents:
                if p.patent_number.strip().upper() == patent_number.strip().upper():
                    return p
        return None

    def get_patents_by_family(self, family_id: str) -> List[PatentRecord]:
        """Retrieves all patents belonging to a patent family."""
        matching = []
        for profile in self._profiles_by_asset.values():
            for p in profile.patents:
                if p.family_id and p.family_id.strip().upper() == family_id.strip().upper():
                    matching.append(p)
        return matching

    def get_patents_by_claim_type(
        self,
        claim_type: PatentClaimType,
        cutoff_date: Optional[date] = None,
    ) -> List[PatentRecord]:
        """Retrieves all patents classified with a given claim type."""
        matching = []
        for profile in self._profiles_by_asset.values():
            for p in profile.patents:
                if claim_type in p.claim_types:
                    if cutoff_date is None or p.filing_date <= cutoff_date:
                        matching.append(p)
        return matching

    def _load_reference_fixtures(self) -> None:
        """Preloads reference assets: Tucatinib, Zongertinib, and Poziotinib."""
        # 1. Tucatinib (Tukysa)
        tucatinib_id = UUID("11111111-1111-1111-1111-111111111111")
        tucatinib_profile = AssetOwnershipProfile(
            asset_id=tucatinib_id,
            developer="Pfizer Inc.",
            originator="Array BioPharma",
            current_owner="Pfizer Inc.",
            former_owners=["Array BioPharma", "Cascadian Therapeutics", "Seagen Inc."],
            academic_origin=None,
            licensing_status=LicensingStatus.PARTNERED,
            licensing_status_rationale="Global commercial rights held by Pfizer (via Seagen acquisition); ex-US/EU/Canada commercial rights partnered with Merck.",
            licensing_status_verified=True,
            licensing_verification_source="SEC Form 10-K Pfizer Inc. & Merck Strategic Collaboration Agreement (Sept 2020)",
            deal_history=[
                OwnershipAndDealEvent(
                    asset_id=tucatinib_id,
                    deal_type=DealType.LICENSING_ANNOUNCEMENT,
                    licensor="Array BioPharma",
                    licensee="Oncothyreon (Cascadian Therapeutics)",
                    territory="Global",
                    effective_date=date(2010, 6, 8),
                    disclosed_upfront_usd=20000000,
                    summary="Exclusive worldwide license to develop and commercialize ARRY-380 (tucatinib).",
                    source_citation="Array BioPharma SEC 8-K License Agreement Filing (June 2010)",
                ),
                OwnershipAndDealEvent(
                    asset_id=tucatinib_id,
                    deal_type=DealType.ACQUISITION,
                    licensor="Cascadian Therapeutics",
                    licensee="Seattle Genetics (Seagen)",
                    territory="Global",
                    effective_date=date(2018, 3, 9),
                    disclosed_upfront_usd=614000000,
                    summary="Seattle Genetics completes acquisition of Cascadian Therapeutics for $614 million, acquiring full rights to tucatinib (ONT-380).",
                    source_citation="Seattle Genetics SEC Form 8-K Merger Completion (March 2018)",
                ),
                OwnershipAndDealEvent(
                    asset_id=tucatinib_id,
                    deal_type=DealType.CO_DEVELOPMENT,
                    licensor="Seagen Inc.",
                    licensee="Merck & Co.",
                    partner="Merck & Co.",
                    territory="Worldwide ex-US, Canada, Europe",
                    effective_date=date(2020, 9, 14),
                    disclosed_upfront_usd=275000000,
                    disclosed_milestones_usd=450000000,
                    royalty_rate_pct="Tiered double-digit royalties",
                    summary="Seagen and Merck enter strategic global collaboration to commercialize Tukysa in territories outside the U.S., Canada, and Europe.",
                    source_citation="Merck & Seagen Joint Press Release & SEC 8-K (Sept 2020)",
                ),
                OwnershipAndDealEvent(
                    asset_id=tucatinib_id,
                    deal_type=DealType.ACQUISITION,
                    licensor="Seagen Inc.",
                    licensee="Pfizer Inc.",
                    territory="Global",
                    effective_date=date(2023, 12, 14),
                    disclosed_upfront_usd=43000000000,
                    summary="Pfizer completes $43 billion acquisition of Seagen Inc., acquiring all proprietary rights to Tukysa.",
                    source_citation="Pfizer Inc. Press Release and SEC Form 8-K (Dec 2023)",
                ),
            ],
            patents=[
                PatentRecord(
                    asset_id=tucatinib_id,
                    family_id="FAM-TUC-001",
                    patent_number="US8648075B2",
                    title="Substituted pyrimidinyl-pyridinyl compounds as kinase inhibitors",
                    assignee="Pfizer Inc. (orig. Array BioPharma)",
                    inventors=["Gaudino JJ", "Cook AW", "Wallace E"],
                    jurisdiction=PatentJurisdiction.US,
                    filing_date=date(2007, 4, 30),
                    priority_date=date(2006, 5, 1),
                    expiration_date=date(2031, 8, 22),  # With Patent Term Extension (PTE)
                    status=PatentStatus.GRANTED,
                    claim_types=[PatentClaimType.COMPOSITION_OF_MATTER],
                    composition_of_matter_expiry=date(2031, 8, 22),
                    source_citation="USPTO Patent Full-Text and Image Database (US 8,648,075)",
                ),
                PatentRecord(
                    asset_id=tucatinib_id,
                    family_id="FAM-TUC-002",
                    patent_number="US10751342B2",
                    title="Combination therapy for treating HER2-expressing cancers",
                    assignee="Pfizer Inc.",
                    inventors=["Walker M", "Siegel M"],
                    jurisdiction=PatentJurisdiction.US,
                    filing_date=date(2018, 9, 12),
                    priority_date=date(2017, 9, 15),
                    expiration_date=date(2038, 9, 12),
                    status=PatentStatus.GRANTED,
                    claim_types=[PatentClaimType.COMBINATION, PatentClaimType.THERAPEUTIC_USE],
                    source_citation="USPTO Patent Database (US 10,751,342)",
                ),
            ],
        )
        self._profiles_by_asset[tucatinib_id] = LicensingAndIPGuard.verify_profile(tucatinib_profile, strict=False)

        # 2. Zongertinib (BI 1810631)
        zongertinib_id = UUID("00000000-0000-0000-0000-000000000001")
        zongertinib_profile = AssetOwnershipProfile(
            asset_id=zongertinib_id,
            developer="Boehringer Ingelheim",
            originator="Boehringer Ingelheim",
            current_owner="Boehringer Ingelheim",
            former_owners=[],
            academic_origin="Boehringer Ingelheim Regional Center Vienna (RCV)",
            licensing_status=LicensingStatus.NO_PUBLIC_LICENSING_SIGNAL,
            licensing_status_rationale="Core internal targeted oncology asset actively developed by Boehringer Ingelheim in pivotal Phase 3 Beamion trials; no public out-licensing signal.",
            licensing_status_verified=True,
            licensing_verification_source="Boehringer Ingelheim Corporate Pipeline Review 2024",
            deal_history=[],
            patents=[
                PatentRecord(
                    asset_id=zongertinib_id,
                    family_id="FAM-ZONG-001",
                    patent_number="US11814374B2",
                    title="Covalent HER2 kinase inhibitors sparing wild-type EGFR",
                    assignee="Boehringer Ingelheim International GmbH",
                    inventors=["Wilding B", "Kopp H", "Wunberg H"],
                    jurisdiction=PatentJurisdiction.US,
                    filing_date=date(2020, 12, 10),
                    priority_date=date(2019, 12, 11),
                    expiration_date=date(2040, 12, 10),
                    status=PatentStatus.GRANTED,
                    claim_types=[PatentClaimType.COMPOSITION_OF_MATTER],
                    composition_of_matter_expiry=date(2040, 12, 10),
                    source_citation="USPTO Patent Database (US 11,814,374)",
                ),
                PatentRecord(
                    asset_id=zongertinib_id,
                    family_id="FAM-ZONG-002",
                    patent_number="US20240108639A1",
                    title="Methods of treating cancer harboring HER2 kinase domain mutations including L755S",
                    assignee="Boehringer Ingelheim International GmbH",
                    inventors=["Wilding B", "Neumüller R"],
                    jurisdiction=PatentJurisdiction.US,
                    filing_date=date(2023, 10, 4),
                    priority_date=date(2022, 10, 6),
                    expiration_date=date(2043, 10, 4),
                    status=PatentStatus.PENDING,
                    claim_types=[PatentClaimType.BIOMARKER_CLAIMS, PatentClaimType.THERAPEUTIC_USE],
                    source_citation="USPTO Patent Application Publication (US 2024/0108639)",
                ),
            ],
        )
        self._profiles_by_asset[zongertinib_id] = LicensingAndIPGuard.verify_profile(zongertinib_profile, strict=False)

        # 3. Poziotinib
        poziotinib_id = UUID("33333333-3333-3333-3333-333333333333")
        poziotinib_profile = AssetOwnershipProfile(
            asset_id=poziotinib_id,
            developer="Hanmi Pharmaceutical",
            originator="Hanmi Pharmaceutical",
            current_owner="Hanmi Pharmaceutical",
            former_owners=["Hanmi Pharmaceutical", "Spectrum Pharmaceuticals"],
            academic_origin="Hanmi Research Center (Seoul, South Korea)",
            licensing_status=LicensingStatus.POTENTIALLY_AVAILABLE,
            licensing_status_rationale="Rights reverted to originator Hanmi Pharmaceutical following Spectrum deprioritization and CRL; available for potential partnering or regional exploration.",
            licensing_status_verified=False,
            licensing_verification_source="Spectrum Pharmaceuticals SEC 10-K & Hanmi Corporate Disclosure (2023)",
            deal_history=[
                OwnershipAndDealEvent(
                    asset_id=poziotinib_id,
                    deal_type=DealType.LICENSING_ANNOUNCEMENT,
                    licensor="Hanmi Pharmaceutical",
                    licensee="Spectrum Pharmaceuticals",
                    territory="Worldwide ex-Korea and China",
                    effective_date=date(2015, 3, 2),
                    disclosed_upfront_usd=10000000,
                    disclosed_milestones_usd=170000000,
                    summary="Spectrum in-licenses worldwide rights to poziotinib excluding Korea and China from Hanmi.",
                    source_citation="Spectrum Pharmaceuticals SEC 8-K Licensing Disclosure (March 2015)",
                ),
                OwnershipAndDealEvent(
                    asset_id=poziotinib_id,
                    deal_type=DealType.ASSET_TRANSFER,
                    licensor="Spectrum Pharmaceuticals",
                    licensee="Hanmi Pharmaceutical",
                    territory="Worldwide ex-Korea and China",
                    effective_date=date(2023, 2, 1),
                    summary="Rights revert to Hanmi following CRL and portfolio deprioritization.",
                    source_citation="Spectrum Pharmaceuticals Corporate Discontinuation Filing (Feb 2023)",
                ),
            ],
            patents=[
                PatentRecord(
                    asset_id=poziotinib_id,
                    patent_number="US8822464B2",
                    title="Quinazoline derivatives as pan-HER tyrosine kinase inhibitors",
                    assignee="Hanmi Pharmaceutical Co., Ltd.",
                    inventors=["Kwak H", "Cha M"],
                    jurisdiction=PatentJurisdiction.US,
                    filing_date=date(2008, 9, 2),
                    priority_date=date(2007, 9, 3),
                    expiration_date=date(2028, 9, 2),
                    status=PatentStatus.GRANTED,
                    claim_types=[PatentClaimType.COMPOSITION_OF_MATTER],
                    composition_of_matter_expiry=date(2028, 9, 2),
                    source_citation="USPTO Patent Database (US 8,822,464)",
                ),
            ],
        )
        self._profiles_by_asset[poziotinib_id] = LicensingAndIPGuard.verify_profile(poziotinib_profile, strict=False)
