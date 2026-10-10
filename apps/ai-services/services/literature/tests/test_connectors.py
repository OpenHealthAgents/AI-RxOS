import pytest

from app.connectors.base import SourceRecord
from app.connectors.registry import get_connector


@pytest.mark.parametrize(
    "source_name,expected_class",
    [
        ("pubmed", "PubMedConnector"),
        ("pmc", "PubMedCentralConnector"),
        ("clinicaltrials", "ClinicalTrialsConnector"),
        ("biorxiv", "BioRxivConnector"),
        ("medrxiv", "MedRxivConnector"),
        ("aacr", "AACRConnector"),
        ("asco", "ASCOConnector"),
        ("esmo", "ESMOConnector"),
        ("sabcs", "SABCSConnector"),
        ("patents", "PatentConnector"),
        ("company_website", "CompanyWebsiteConnector"),
    ],
)
def test_connector_registry(source_name, expected_class):
    connector = get_connector(source_name)
    assert connector.__class__.__name__ == expected_class


def test_source_record_model():
    record = SourceRecord(
        source="pubmed",
        source_id="123",
        title="A Sample Title",
        abstract="Abstract text",
        authors=["Author One", "Author Two"],
    )
    assert record.source == "pubmed"
    assert record.source_id == "123"
    assert record.title == "A Sample Title"
