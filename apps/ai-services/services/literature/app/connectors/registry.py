from __future__ import annotations

from collections.abc import Callable

from app.connectors import (
    AACRConnector,
    ASCOConnector,
    BioRxivConnector,
    ClinicalTrialsConnector,
    CompanyWebsiteConnector,
    ESMOConnector,
    MedRxivConnector,
    PatentConnector,
    PubMedCentralConnector,
    PubMedConnector,
    SABCSConnector,
)
from app.connectors.base import SourceConnector

CONNECTOR_FACTORIES: dict[str, Callable[[], SourceConnector]] = {
    "pubmed": PubMedConnector,
    "pmc": PubMedCentralConnector,
    "clinicaltrials": ClinicalTrialsConnector,
    "biorxiv": BioRxivConnector,
    "medrxiv": MedRxivConnector,
    "aacr": AACRConnector,
    "asco": ASCOConnector,
    "esmo": ESMOConnector,
    "sabcs": SABCSConnector,
    "patents": PatentConnector,
    "company_website": CompanyWebsiteConnector,
}


def get_connector(source_name: str) -> SourceConnector:
    connector_factory = CONNECTOR_FACTORIES.get(source_name)
    if connector_factory is None:
        raise ValueError(f"Unknown connector source: {source_name}")
    return connector_factory()
