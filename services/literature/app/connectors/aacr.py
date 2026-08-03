from __future__ import annotations

from app.connectors.adapter import UnsupportedSourceAdapter


class AACRConnector(UnsupportedSourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            "aacr", "requires gated access and no generic public REST API is available"
        )
