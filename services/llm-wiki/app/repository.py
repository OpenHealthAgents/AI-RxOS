"""Persistence for LLM Wiki pages/versions.

Two implementations sharing the same method signatures and the same
tenant-isolation semantics (`WikiRepository` is a structural protocol, not
a formal ABC -- there are exactly two implementations and adding
boilerplate for a third that doesn't exist isn't worth it):

- `PostgresWikiRepository`: the production path, backed by the `llm_wiki`
  Postgres schema (migrations/001_wiki_schema.sql).
- `InMemoryWikiRepository`: a test double with no external dependencies,
  used by the fast unit test suite (tests/test_*.py) via
  `app.dependency_overrides`. tests/test_postgres_integration.py and
  tests/test_e2e_literature_roundtrip.py exercise the real Postgres path
  instead, skipped automatically when no database is reachable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import asyncpg

from app.db.pool import tenant_connection

# Must match services/literature/app/knowledge/models.py::_ENTITY_ID_NAMESPACE
# exactly -- this is what lets a wiki page's entity_id trace back to the
# same deterministic id services/kg would assign the matching graph node.
# Duplicated rather than imported: the two services deploy and run as
# separate processes/images, so there is no shared Python package boundary
# to import across.
_ENTITY_ID_NAMESPACE = uuid.UUID("6f6d0f2e-6e0a-4f0b-9a6b-2e6b7f9c9e10")

MAX_FIELD_LEN = 512


class ValidationError(ValueError):
    pass


def deterministic_entity_id(category: str, text: str) -> str:
    normalized = f"{category.strip().lower()}:{text.strip().lower()}"
    return str(uuid.uuid5(_ENTITY_ID_NAMESPACE, normalized))


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _check_len(name: str, value: str | None) -> None:
    if value and len(value) > MAX_FIELD_LEN:
        raise ValidationError(f"{name} exceeds {MAX_FIELD_LEN} characters")


@dataclass(frozen=True)
class TenantScope:
    organization_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TenantScope":
        data = data or {}
        scope = cls(
            organization_id=_clean(data.get("organization_id")),
            workspace_id=_clean(data.get("workspace_id")),
            project_id=_clean(data.get("project_id")),
        )
        _check_len("organization_id", scope.organization_id)
        _check_len("workspace_id", scope.workspace_id)
        _check_len("project_id", scope.project_id)
        return scope


def _entity_page_fields(
    entity: dict[str, Any], document: dict[str, Any], relationships: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> tuple[str, str, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], str] | None:
    text = entity.get("text")
    if not text or not isinstance(text, str):
        return None
    category = str(entity.get("category") or "concepts")
    slug = text.replace(" ", "_")
    _check_len("category", category)
    _check_len("slug", slug)
    entity_id = deterministic_entity_id(str(entity.get("type") or category), text)
    entity_relationships = [
        r for r in relationships if r.get("source_entity") == text or r.get("target_entity") == text
    ]
    entity_evidence = [e for e in evidence if e.get("entity") == text]
    provenance = {
        "source": document.get("source"),
        "url": document.get("url"),
        "doi": document.get("doi"),
    }
    title = str(document.get("title") or text)
    return category, slug, entity_id, entity_relationships, entity_evidence, provenance, title


class WikiRepository(Protocol):
    async def compile_pages(
        self,
        *,
        tenant: TenantScope,
        document: dict[str, Any],
        entities: list[dict[str, Any]],
        summary: dict[str, Any],
        relationships: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...

    async def get_page(self, tenant: TenantScope, page_id: str) -> dict[str, Any] | None: ...

    async def list_versions(self, tenant: TenantScope, page_id: str) -> list[dict[str, Any]] | None: ...

    async def get_version(self, tenant: TenantScope, page_id: str, version: int) -> dict[str, Any] | None: ...

    async def find_page(self, tenant: TenantScope, *, category: str, slug: str) -> dict[str, Any] | None: ...

    async def query_pages(self, tenant: TenantScope, limit: int) -> list[dict[str, Any]]: ...


class PostgresWikiRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def compile_pages(
        self,
        *,
        tenant: TenantScope,
        document: dict[str, Any],
        entities: list[dict[str, Any]],
        summary: dict[str, Any],
        relationships: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        async with tenant_connection(self._pool, tenant.organization_id) as conn:
            for entity in entities:
                fields = _entity_page_fields(entity, document, relationships, evidence)
                if fields is None:
                    continue
                category, slug, entity_id, entity_relationships, entity_evidence, provenance, title = fields

                existing = await conn.fetchrow(
                    """
                    SELECT id, current_version FROM llm_wiki.wiki_pages
                    WHERE organization_id IS NOT DISTINCT FROM $1
                      AND workspace_id IS NOT DISTINCT FROM $2
                      AND category = $3 AND slug = $4
                    """,
                    tenant.organization_id,
                    tenant.workspace_id,
                    category,
                    slug,
                )
                now = datetime.now(timezone.utc)
                if existing is None:
                    page_id = await conn.fetchval(
                        """
                        INSERT INTO llm_wiki.wiki_pages
                            (organization_id, workspace_id, project_id, category, slug,
                             entity_id, title, current_version, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,1,$8,$8)
                        RETURNING id
                        """,
                        tenant.organization_id,
                        tenant.workspace_id,
                        tenant.project_id,
                        category,
                        slug,
                        entity_id,
                        title,
                        now,
                    )
                    version = 1
                else:
                    page_id = existing["id"]
                    version = existing["current_version"] + 1
                    await conn.execute(
                        """
                        UPDATE llm_wiki.wiki_pages
                        SET current_version = $2, title = $3, entity_id = $4, updated_at = $5
                        WHERE id = $1
                        """,
                        page_id,
                        version,
                        title,
                        entity_id,
                        now,
                    )

                await conn.execute(
                    """
                    INSERT INTO llm_wiki.wiki_page_versions
                        (page_id, version, document, entity, summary, relationships, evidence, chunks, provenance, created_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                    """,
                    page_id,
                    version,
                    document,
                    entity,
                    summary,
                    entity_relationships,
                    entity_evidence,
                    chunks,
                    provenance,
                    now,
                )
                results.append(
                    {
                        "id": str(page_id),
                        "category": category,
                        "slug": slug,
                        "entity_id": entity_id,
                        "version": version,
                    }
                )
        return results

    async def get_page(self, tenant: TenantScope, page_id: str) -> dict[str, Any] | None:
        async with tenant_connection(self._pool, tenant.organization_id) as conn:
            page = await conn.fetchrow(
                """
                SELECT * FROM llm_wiki.wiki_pages
                WHERE id = $1 AND (organization_id IS NULL OR organization_id = $2)
                """,
                page_id,
                tenant.organization_id,
            )
            if page is None:
                return None
            version = await conn.fetchrow(
                "SELECT * FROM llm_wiki.wiki_page_versions WHERE page_id = $1 AND version = $2",
                page_id,
                page["current_version"],
            )
            return {"page": dict(page), "version": dict(version) if version else None}

    async def list_versions(self, tenant: TenantScope, page_id: str) -> list[dict[str, Any]] | None:
        async with tenant_connection(self._pool, tenant.organization_id) as conn:
            page = await conn.fetchrow(
                """
                SELECT id FROM llm_wiki.wiki_pages
                WHERE id = $1 AND (organization_id IS NULL OR organization_id = $2)
                """,
                page_id,
                tenant.organization_id,
            )
            if page is None:
                return None
            rows = await conn.fetch(
                "SELECT version, created_at FROM llm_wiki.wiki_page_versions WHERE page_id = $1 ORDER BY version DESC",
                page_id,
            )
            return [dict(r) for r in rows]

    async def get_version(self, tenant: TenantScope, page_id: str, version: int) -> dict[str, Any] | None:
        async with tenant_connection(self._pool, tenant.organization_id) as conn:
            page = await conn.fetchrow(
                """
                SELECT id FROM llm_wiki.wiki_pages
                WHERE id = $1 AND (organization_id IS NULL OR organization_id = $2)
                """,
                page_id,
                tenant.organization_id,
            )
            if page is None:
                return None
            row = await conn.fetchrow(
                "SELECT * FROM llm_wiki.wiki_page_versions WHERE page_id = $1 AND version = $2",
                page_id,
                version,
            )
            return dict(row) if row else None

    async def find_page(self, tenant: TenantScope, *, category: str, slug: str) -> dict[str, Any] | None:
        async with tenant_connection(self._pool, tenant.organization_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM llm_wiki.wiki_pages
                WHERE category = $1 AND slug = $2
                  AND organization_id IS NOT DISTINCT FROM $3
                  AND workspace_id IS NOT DISTINCT FROM $4
                """,
                category,
                slug,
                tenant.organization_id,
                tenant.workspace_id,
            )
            return dict(row) if row else None

    async def query_pages(self, tenant: TenantScope, limit: int) -> list[dict[str, Any]]:
        async with tenant_connection(self._pool, tenant.organization_id) as conn:
            rows = await conn.fetch(
                """
                WITH scoped AS (
                    SELECT p.id, p.title, p.category, p.slug, p.updated_at, v.summary, v.document
                    FROM llm_wiki.wiki_pages p
                    JOIN llm_wiki.wiki_page_versions v
                      ON v.page_id = p.id AND v.version = p.current_version
                    WHERE (p.organization_id IS NULL OR p.organization_id = $1)
                      AND ($2::text IS NULL OR p.workspace_id IS NULL OR p.workspace_id = $2)
                )
                SELECT * FROM scoped ORDER BY updated_at DESC LIMIT $3
                """,
                tenant.organization_id,
                tenant.workspace_id,
                limit,
            )
            return [dict(r) for r in rows]


class InMemoryWikiRepository:
    """Test double. Reimplements the same tenant-visibility rule as the
    Postgres RLS policy in Python (untenanted OR own-org) so unit tests can
    assert isolation behavior without a running database."""

    def __init__(self) -> None:
        self._pages: dict[str, dict[str, Any]] = {}
        self._versions: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def _visible(tenant: TenantScope, page: dict[str, Any]) -> bool:
        return page["organization_id"] is None or page["organization_id"] == tenant.organization_id

    async def compile_pages(
        self,
        *,
        tenant: TenantScope,
        document: dict[str, Any],
        entities: list[dict[str, Any]],
        summary: dict[str, Any],
        relationships: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for entity in entities:
            fields = _entity_page_fields(entity, document, relationships, evidence)
            if fields is None:
                continue
            category, slug, entity_id, entity_relationships, entity_evidence, provenance, title = fields

            key = (tenant.organization_id or "", tenant.workspace_id or "", category, slug)
            now = datetime.now(timezone.utc)

            existing_id = next(
                (
                    pid
                    for pid, p in self._pages.items()
                    if (p["organization_id"] or "", p["workspace_id"] or "", p["category"], p["slug"]) == key
                ),
                None,
            )
            if existing_id is None:
                page_id = str(uuid.uuid4())
                self._pages[page_id] = {
                    "id": page_id,
                    "organization_id": tenant.organization_id,
                    "workspace_id": tenant.workspace_id,
                    "project_id": tenant.project_id,
                    "category": category,
                    "slug": slug,
                    "entity_id": entity_id,
                    "title": title,
                    "current_version": 1,
                    "created_at": now,
                    "updated_at": now,
                }
                self._versions[page_id] = []
                version = 1
            else:
                page_id = existing_id
                version = self._pages[page_id]["current_version"] + 1
                self._pages[page_id].update(
                    current_version=version, title=title, entity_id=entity_id, updated_at=now
                )

            self._versions[page_id].append(
                {
                    "page_id": page_id,
                    "version": version,
                    "document": document,
                    "entity": entity,
                    "summary": summary,
                    "relationships": entity_relationships,
                    "evidence": entity_evidence,
                    "chunks": chunks,
                    "provenance": provenance,
                    "created_at": now,
                }
            )
            results.append(
                {"id": page_id, "category": category, "slug": slug, "entity_id": entity_id, "version": version}
            )
        return results

    async def get_page(self, tenant: TenantScope, page_id: str) -> dict[str, Any] | None:
        page = self._pages.get(page_id)
        if page is None or not self._visible(tenant, page):
            return None
        versions = self._versions.get(page_id, [])
        latest = next((v for v in versions if v["version"] == page["current_version"]), None)
        return {"page": dict(page), "version": dict(latest) if latest else None}

    async def list_versions(self, tenant: TenantScope, page_id: str) -> list[dict[str, Any]] | None:
        page = self._pages.get(page_id)
        if page is None or not self._visible(tenant, page):
            return None
        return [
            {"version": v["version"], "created_at": v["created_at"]}
            for v in sorted(self._versions.get(page_id, []), key=lambda v: -v["version"])
        ]

    async def get_version(self, tenant: TenantScope, page_id: str, version: int) -> dict[str, Any] | None:
        page = self._pages.get(page_id)
        if page is None or not self._visible(tenant, page):
            return None
        return next((dict(v) for v in self._versions.get(page_id, []) if v["version"] == version), None)

    async def find_page(self, tenant: TenantScope, *, category: str, slug: str) -> dict[str, Any] | None:
        key = (tenant.organization_id or "", tenant.workspace_id or "", category, slug)
        for page in self._pages.values():
            if (page["organization_id"] or "", page["workspace_id"] or "", page["category"], page["slug"]) == key:
                return dict(page)
        return None

    async def query_pages(self, tenant: TenantScope, limit: int) -> list[dict[str, Any]]:
        visible = [p for p in self._pages.values() if self._visible(tenant, p)]
        if tenant.workspace_id:
            visible = [p for p in visible if p["workspace_id"] is None or p["workspace_id"] == tenant.workspace_id]
        visible.sort(key=lambda p: p["updated_at"], reverse=True)
        out = []
        for p in visible[:limit]:
            latest = next(
                (v for v in self._versions.get(p["id"], []) if v["version"] == p["current_version"]), None
            )
            out.append(
                {
                    "id": p["id"],
                    "title": p["title"],
                    "category": p["category"],
                    "slug": p["slug"],
                    "updated_at": p["updated_at"],
                    "summary": latest["summary"] if latest else {},
                    "document": latest["document"] if latest else {},
                }
            )
        return out
