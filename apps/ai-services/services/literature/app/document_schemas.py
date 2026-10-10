from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentSection(BaseModel):
    title: str = ""
    text: str = ""


class DocumentReference(BaseModel):
    citation: str | None = None
    href: str | None = None
    text: str | None = None


class DocumentTable(BaseModel):
    label: str | None = None
    caption: str | None = None


class DocumentFigure(BaseModel):
    label: str | None = None
    caption: str | None = None


class DocumentMetadata(BaseModel):
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    affiliations: list[str] = Field(default_factory=list)
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)
    sections: list[DocumentSection] = Field(default_factory=list)
    references: list[DocumentReference] = Field(default_factory=list)
    tables: list[DocumentTable] = Field(default_factory=list)
    figures: list[DocumentFigure] = Field(default_factory=list)
    supplementary: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
