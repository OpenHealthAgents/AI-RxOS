from __future__ import annotations

from app.connectors.adapter import UnsupportedSourceAdapter


class PatentConnector(UnsupportedSourceAdapter):
    def __init__(self) -> None:
        super().__init__(
            "patents", "patent data requires specialized paid or partner APIs"
        )
