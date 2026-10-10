from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.connectors.base import PageResult, SourceConnector


class AdapterSourceConnector(SourceConnector, ABC):
    @abstractmethod
    async def fetch_records(
        self,
        query: str | None = None,
        page_token: str | None = None,
        since: datetime | None = None,
        page_size: int = 50,
    ) -> PageResult:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        raise NotImplementedError


class UnsupportedSourceAdapter(AdapterSourceConnector):
    def __init__(self, source_name: str, reason: str):
        super().__init__(source_name)
        self.reason = reason

    async def health_check(self) -> bool:
        return False

    async def fetch_records(
        self,
        query: str | None = None,
        page_token: str | None = None,
        since: datetime | None = None,
        page_size: int = 50,
    ) -> PageResult:
        raise NotImplementedError(
            f"Source {self.source_name} is not supported: {self.reason}"
        )
