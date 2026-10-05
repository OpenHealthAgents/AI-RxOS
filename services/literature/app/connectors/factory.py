from __future__ import annotations

from typing import Any, ClassVar

from app.connectors.base import BaseConnector
from app.connectors.sources import (
    AACRConnector,
    ASCOConnector,
    BioRxivConnector,
    ClinicalTrialsConnector,
    CompanyWebsiteConnector,
    ESMOConnector,
    FDARegulatoryConnector,
    MedRxivConnector,
    PatentsConnector,
    PMCConnector,
    PubMedConnector,
    SABCSConnector,
)


class ConnectorFactory:
    """Factory to select the right connector for a literature source."""

    registry: ClassVar[dict[str, type[BaseConnector]]] = {
        "pubmed": PubMedConnector,
        "pmc": PMCConnector,
        "clinicaltrials": ClinicalTrialsConnector,
        "regulatory": FDARegulatoryConnector,
        "aacr": AACRConnector,
        "asco": ASCOConnector,
        "sabcs": SABCSConnector,
        "esmo": ESMOConnector,
        "biorxiv": BioRxivConnector,
        "medrxiv": MedRxivConnector,
        "patents": PatentsConnector,
        "company_websites": CompanyWebsiteConnector,
    }

    @classmethod
    def create(cls, source: str, config: dict[str, Any] | None = None) -> BaseConnector:
        connector_name = source.lower().strip()
        try:
            connector_class = cls.registry[connector_name]
        except KeyError as exc:
            supported = ", ".join(sorted(cls.registry))
            raise ValueError(f"Unsupported literature source '{source}'. Supported: {supported}") from exc
        return connector_class(config or {})
