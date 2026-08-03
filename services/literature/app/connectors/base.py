from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class ConnectorError(Exception):
    pass


class SourceRecord(BaseModel):
    source: str
    source_id: str
    title: str
    abstract: str | None = None
    authors: list[str] = []
    published_date: datetime | None = None
    doi: str | None = None
    url: str | None = None
    source_updated_at: datetime | None = None
    extra: dict[str, object] = {}


class PageResult(BaseModel):
    items: list[SourceRecord]
    next_page_token: str | None = None


class SourceConnector(ABC):
    source_name: str

    def __init__(self, source_name: str):
        self.source_name = source_name

    @abstractmethod
    async def health_check(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def fetch_records(
        self,
        query: str | None = None,
        page_token: str | None = None,
        since: datetime | None = None,
        page_size: int = 50,
    ) -> PageResult:
        raise NotImplementedError
