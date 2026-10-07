import pytest
from datetime import date
from uuid import UUID, uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.evidence.models import (
    EvidenceSource,
    EvidenceTemporalScope,
    ProspectiveOrRetrospective,
    SourceType,
)
from app.opportunity_engine.evidence.service import EvidenceService
from app.opportunity_engine.temporal.models import (
    EvidenceTemporalMetadata,
    TemporalDateField,
    TemporalQueryFilter,
)


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


def test_track_all_eight_temporal_coordinates():
    """Verify that all 8 distinct temporal coordinates are properly tracked and accessible."""
    meta = EvidenceTemporalMetadata(
        publication_date=date(2024, 5, 8),
        observation_date=date(2024, 4, 15),
        trial_date=date(2021, 6, 1),
        outcome_date=date(2024, 3, 30),
        regulatory_date=date(2023, 7, 24),
        licensing_date=date(2022, 12, 1),
        prediction_cutoff=date(2024, 5, 10),
        public_availability_date=date(2024, 5, 8),
    )

    assert meta.publication_date == date(2024, 5, 8)
    assert meta.observation_date == date(2024, 4, 15)
    assert meta.trial_date == date(2021, 6, 1)
    assert meta.outcome_date == date(2024, 3, 30)
    assert meta.regulatory_date == date(2023, 7, 24)
    assert meta.licensing_date == date(2022, 12, 1)
    assert meta.prediction_cutoff == date(2024, 5, 10)
    assert meta.public_availability_date == date(2024, 5, 8)

    # Effective public date calculates public disclosure
    assert meta.effective_public_date() == date(2024, 5, 8)

    # Anti-leakage visibility checks
    assert meta.is_visible_at(date(2024, 5, 8)) is True
    assert meta.is_visible_at(date(2024, 5, 7)) is False


def test_temporal_query_filter_matching():
    """Verify TemporalQueryFilter correctly slices evidence across date coordinates."""
    meta = EvidenceTemporalMetadata(
        publication_date=date(2023, 10, 15),
        observation_date=date(2023, 9, 1),
        trial_date=date(2021, 5, 15),
        outcome_date=date(2023, 10, 15),
        regulatory_date=date(2023, 7, 24),
        licensing_date=date(2022, 12, 1),
        prediction_cutoff=date(2023, 11, 1),
        public_availability_date=date(2023, 10, 15),
    )

    # 1. As-of date cutoff: on or after publication
    f_after = TemporalQueryFilter(as_of_date=date(2023, 11, 1))
    assert f_after.matches(meta) is True

    # 2. As-of date cutoff: before publication
    f_before = TemporalQueryFilter(as_of_date=date(2022, 1, 1))
    assert f_before.matches(meta) is False

    # 3. Query specific field: licensing_date
    f_licensing = TemporalQueryFilter(
        date_field=TemporalDateField.LICENSING_DATE,
        start_date=date(2022, 1, 1),
        end_date=date(2022, 12, 31),
    )
    assert f_licensing.matches(meta) is True

    # 4. Query specific field: trial_date outside range
    f_trial_miss = TemporalQueryFilter(
        date_field=TemporalDateField.TRIAL_DATE,
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
    )
    assert f_trial_miss.matches(meta) is False


def test_evidence_service_temporal_querying():
    """Verify EvidenceService allows querying all evidence by time with anti-leakage boundaries."""
    service = EvidenceService()
    zong_id = UUID("33333333-3333-3333-3333-333333333333")

    # 1. Query with strict historical cutoff in 2022
    # At end of 2022: Patent (Sep 2022) and Licensing deal (Dec 2022) exist, but 2023+ trials do not
    ev_2022 = service.query_evidence_by_time(
        asset_id=zong_id,
        as_of_date=date(2022, 12, 31),
    )
    assert len(ev_2022) >= 1
    for ev in ev_2022:
        assert ev.temporal_metadata.effective_public_date() <= date(2022, 12, 31)

    # 2. Query specific date coordinate: regulatory_date
    ev_reg = service.query_evidence_by_time(
        asset_id=zong_id,
        date_field=TemporalDateField.REGULATORY_DATE,
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
    )
    assert len(ev_reg) >= 1
    assert any("Breakthrough Therapy" in ev.title for ev in ev_reg)
    assert ev_reg[0].temporal_metadata.regulatory_date == date(2023, 7, 24)

    # 3. Query specific date coordinate: licensing_date
    ev_lic = service.query_evidence_by_time(
        asset_id=zong_id,
        date_field=TemporalDateField.LICENSING_DATE,
    )
    assert len(ev_lic) >= 1
    assert ev_lic[0].temporal_metadata.licensing_date == date(2022, 12, 1)

    # 4. Query specific date coordinate: trial_date
    ev_trial = service.query_evidence_by_time(
        asset_id=zong_id,
        date_field=TemporalDateField.TRIAL_DATE,
    )
    assert len(ev_trial) >= 1
    assert any(ev.temporal_metadata.trial_date is not None for ev in ev_trial)

    # 5. Query 2024 range: must include Nature Cancer publication and Lancet Oncology CNS cohort
    ev_2024 = service.query_evidence_by_time(
        asset_id=zong_id,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        date_field=TemporalDateField.PUBLICATION_DATE,
    )
    assert len(ev_2024) >= 1
    pub_titles = [ev.title for ev in ev_2024]
    assert any("Nature Cancer" in ev.organization or "Discovery of Zongertinib" in ev.title or "PMID:38718468" in ev.source_id for ev in ev_2024)


def test_api_evidence_temporal_query(test_client):
    """Verify REST API endpoint GET /api/v1/decision/assets/{asset_id}/evidence/temporal-query."""
    # 1. Unfiltered query returns all evidence with full temporal metadata
    resp = test_client.get("/api/v1/decision/assets/zongertinib/evidence/temporal-query")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == "zongertinib"
    assert data["count"] > 0
    assert "evidence" in data

    first_item = data["evidence"][0]
    assert "temporal_metadata" in first_item
    meta = first_item["temporal_metadata"]
    assert "publication_date" in meta
    assert "observation_date" in meta
    assert "trial_date" in meta
    assert "outcome_date" in meta
    assert "regulatory_date" in meta
    assert "licensing_date" in meta
    assert "prediction_cutoff" in meta
    assert "public_availability_date" in meta

    # 2. Query with as_of_date filtering
    resp_asof = test_client.get(
        "/api/v1/decision/assets/zongertinib/evidence/temporal-query?as_of_date=2023-01-01"
    )
    assert resp_asof.status_code == 200
    data_asof = resp_asof.json()
    # Should only return records known before 2023
    for ev in data_asof["evidence"]:
        eff_date = ev["temporal_metadata"]["public_availability_date"] or ev["temporal_metadata"]["publication_date"]
        assert eff_date <= "2023-01-01"

    # 3. Query specific date coordinate: regulatory_date
    resp_reg = test_client.get(
        "/api/v1/decision/assets/zongertinib/evidence/temporal-query?date_field=regulatory_date"
    )
    assert resp_reg.status_code == 200
    data_reg = resp_reg.json()
    assert data_reg["count"] >= 1
    assert data_reg["evidence"][0]["temporal_metadata"]["regulatory_date"] == "2023-07-24"
