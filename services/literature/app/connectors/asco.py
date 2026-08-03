from __future__ import annotations

from app.connectors.adapter import UnsupportedSourceAdapter


class ASCOConnector(UnsupportedSourceAdapter):
    def __init__(self) -> None:
        super().__init__("asco", "requires membership and non-public event API access")
