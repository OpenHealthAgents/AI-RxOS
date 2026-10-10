from __future__ import annotations

from app.connectors.adapter import UnsupportedSourceAdapter


class SABCSConnector(UnsupportedSourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            "sabcs", "requires event-specific partner integration and paid access"
        )
