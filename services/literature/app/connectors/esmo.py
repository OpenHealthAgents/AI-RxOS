from __future__ import annotations

from app.connectors.adapter import UnsupportedSourceAdapter


class ESMOConnector(UnsupportedSourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            "esmo",
            "no public generic API; event access requires partnership agreements",
        )
