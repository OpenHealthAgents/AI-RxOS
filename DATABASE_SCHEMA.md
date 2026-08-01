# Literature Intelligence Database Schema v2

## Version 2 Summary
This update resolves tenant isolation and scalability blockers with explicit chunked storage, complete tenant fields, and operational schema requirements.

## Principles
- Use Postgres for ingestion metadata, document state, and extraction artifacts.
- Reuse existing auth tables from `services/auth`; do not duplicate user/org/workspace data.
- Reuse `services/search.document_embeddings` for vector storage instead of creating a separate vector table.
- Keep literature data tenant-scoped via `organization_id`, `workspace_id`, and `project_id`.
- Avoid Neo4j schema ownership in this service.
- Support large documents and chunked storage for searchable content.

## Shared Naming and Tenant Rules
- All tables include `organization_id`, `workspace_id`, and `project_id` unless otherwise noted.
- Tenant values are derived from auth claims and enforced by application and RLS.
- Use composite indexes that include tenant columns for filtering and uniqueness.

## Tables Owned by Literature Intelligence

### `ingestion_sources`
Tracks configured ingestion sources and source-level metadata.

- `id UUID PRIMARY KEY`
- `source_type TEXT NOT NULL` -- `pubmed`, `biorxiv`, `medrxiv`, `patent`, `conference`, `custom`
- `name TEXT NOT NULL`
- `config JSONB`
- `enabled BOOLEAN NOT NULL DEFAULT TRUE`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `organization_id UUID NOT NULL`
- `workspace_id UUID NULL`
- `project_id UUID NULL`

Indexes:
- `idx_ingestion_sources_org_workspace`
- `idx_ingestion_sources_source_type`

### `ingestion_jobs`
Tracks ingestion jobs and lifecycle state.

- `id UUID PRIMARY KEY`
- `source_id UUID REFERENCES ingestion_sources(id)`
- `source_type TEXT NOT NULL`
- `query TEXT NOT NULL`
- `source_document_id TEXT NULL`
- `source_url TEXT NULL`
- `status TEXT NOT NULL` -- `queued`, `running`, `completed`, `failed`, `cancelled`
- `document_count INTEGER DEFAULT 0`
- `processed_count INTEGER DEFAULT 0`
- `failed_count INTEGER DEFAULT 0`
- `pending_count INTEGER DEFAULT 0`
- `error_message TEXT NULL`
- `last_error TEXT NULL`
- `backoff_until TIMESTAMPTZ NULL`
- `dead_letter_count INTEGER DEFAULT 0`
- `started_at TIMESTAMPTZ NULL`
- `completed_at TIMESTAMPTZ NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `organization_id UUID NOT NULL`
- `workspace_id UUID NULL`
- `project_id UUID NULL`

Indexes:
- `idx_ingestion_jobs_org_workspace`
- `idx_ingestion_jobs_status`
- `idx_ingestion_jobs_source_type`

### `documents`
Stores ingested documents, canonicalization, and processing state.

- `id UUID PRIMARY KEY`
- `source_type TEXT NOT NULL`
- `source_document_id TEXT NOT NULL`
- `source_url TEXT NULL`
- `title TEXT NOT NULL`
- `abstract TEXT NULL`
- `doi TEXT NULL`
- `publication_date DATE NULL`
- `authors TEXT[] NULL`
- `summary TEXT NULL`
- `citation_count INTEGER DEFAULT 0`
- `status TEXT NOT NULL` -- `new`, `processing`, `processed`, `failed`
- `canonical_document_id UUID NULL`
- `duplicate_group TEXT NULL`
- `ingestion_job_id UUID REFERENCES ingestion_jobs(id)`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `organization_id UUID NOT NULL`
- `workspace_id UUID NULL`
- `project_id UUID NULL`

Unique constraints:
- `(source_type, source_document_id, organization_id, workspace_id)`

Indexes:
- `idx_documents_org_workspace`
- `idx_documents_source_document_id`
- `idx_documents_doi`
- `idx_documents_status`
- `idx_documents_canonical_document_id`

### `document_text_chunks`
Stores document text in chunked form for large content.

- `id UUID PRIMARY KEY`
- `document_id UUID REFERENCES documents(id) ON DELETE CASCADE`
- `chunk_index INTEGER NOT NULL`
- `content TEXT NOT NULL`
- `chunk_hash TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `organization_id UUID NOT NULL`
- `workspace_id UUID NULL`
- `project_id UUID NULL`

Indexes:
- `idx_document_text_chunks_doc`
- `idx_document_text_chunks_org_workspace`

### `document_metadata`
Stores extracted enrichment details and structured metadata.

- `document_id UUID PRIMARY KEY REFERENCES documents(id)`
- `metadata JSONB NOT NULL`
- `paragraphs JSONB NULL`
- `figures JSONB NULL`
- `tables JSONB NULL`
- `references JSONB NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `organization_id UUID NOT NULL`
- `workspace_id UUID NULL`
- `project_id UUID NULL`

Indexes:
- `idx_document_metadata_org_workspace`

### `extracted_entities`
Stores extracted entities for documents.

- `id UUID PRIMARY KEY`
- `document_id UUID REFERENCES documents(id) ON DELETE CASCADE`
- `type TEXT NOT NULL`
- `text TEXT NOT NULL`
- `canonical_id TEXT NULL`
- `confidence REAL NOT NULL`
- `span JSONB NULL`
- `source TEXT NOT NULL`
- `schema TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `organization_id UUID NOT NULL`
- `workspace_id UUID NULL`
- `project_id UUID NULL`

Indexes:
- `idx_extracted_entities_document_id`
- `idx_extracted_entities_type`
- `idx_extracted_entities_canonical_id`
- `idx_extracted_entities_org_workspace`

### `extracted_relationships`
Stores relationship candidates extracted from literature.

- `id UUID PRIMARY KEY`
- `document_id UUID REFERENCES documents(id) ON DELETE CASCADE`
- `from_entity_id UUID REFERENCES extracted_entities(id)`
- `to_entity_id UUID REFERENCES extracted_entities(id)`
- `type TEXT NOT NULL`
- `confidence REAL NOT NULL`
- `evidence TEXT NULL`
- `metadata JSONB NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `organization_id UUID NOT NULL`
- `workspace_id UUID NULL`
- `project_id UUID NULL`

Indexes:
- `idx_extracted_relationships_document_id`
- `idx_extracted_relationships_type`
- `idx_extracted_relationships_org_workspace`

### `citation_edges`
Stores extracted citation relationships from one document to another.

- `id UUID PRIMARY KEY`
- `document_id UUID REFERENCES documents(id) ON DELETE CASCADE`
- `cited_source TEXT NOT NULL`
- `cited_doi TEXT NULL`
- `confidence REAL NOT NULL`
- `metadata JSONB NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `organization_id UUID NOT NULL`
- `workspace_id UUID NULL`
- `project_id UUID NULL`

Indexes:
- `idx_citation_edges_document_id`
- `idx_citation_edges_org_workspace`

### `document_processing_status`
Tracks ingestion/extraction/indexing progress for documents.

- `document_id UUID PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE`
- `stage TEXT NOT NULL` -- `ingestion`, `deduplication`, `extraction`, `indexing`
- `status TEXT NOT NULL` -- `pending`, `running`, `completed`, `failed`
- `error_message TEXT NULL`
- `retry_count INTEGER DEFAULT 0`
- `dead_letter BOOLEAN NOT NULL DEFAULT FALSE`
- `last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `organization_id UUID NOT NULL`
- `workspace_id UUID NULL`
- `project_id UUID NULL`

Indexes:
- `idx_document_processing_status_org_workspace`

### `audit_events`
Tracks important actions for governance and audit.

- `id UUID PRIMARY KEY`
- `event_type TEXT NOT NULL`
- `entity_type TEXT NOT NULL`
- `entity_id UUID NULL`
- `tenant JSONB NOT NULL`
- `actor_id UUID NULL`
- `payload JSONB NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Indexes:
- `idx_audit_events_entity`
- `idx_audit_events_created_at`

## Reuse Existing Tables
- `services/auth` tables for users, organizations, workspaces, roles, sessions.
- `services/search.document_embeddings` for vector search and embedding storage.

If literature generates embeddings, it must upsert through the search service or publish metadata events rather than creating a parallel vector store.

## Row Level Security Strategy
- Use `organization_id`, `workspace_id`, and `project_id` on every owned table.
- Adopt RLS policies where supported and enforce tenant filters in service queries.
- Use a session-level tenant context variable if repository patterns support it.
- Add explicit tenant constraints for duplicates and ingestion jobs.

## Scalability Notes
- Use `document_text_chunks` for large papers and long-form content.
- Avoid storing monolithic `body_text` on `documents` for large articles.
- Use bulk insert patterns for chunk storage and metadata writes.
- Index tenant-filtered fields for high-cardinality query performance.

## Notes
- No Neo4j tables are owned by this service.
- The service keeps document and extraction artifacts separate from search storage.
- This design assumes a shared Postgres instance with separate schema and appropriate resource quotas.
