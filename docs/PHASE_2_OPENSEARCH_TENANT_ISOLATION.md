# Phase 2 B08: OpenSearch Tenant Isolation

## Scope and Status

B08 hardens and tests the existing `services/search` OpenSearch owner. It does
not add a second search stack or implement the deferred projection/reindex
work. The repository-level implementation is **not complete until the live
OpenSearch test runs**; Docker was unavailable during the current validation.

## Discovered Model

- The main runtime uses one shared OpenSearch index, configured by
  `OPENSEARCH_INDEX` and defaulting to `ai-rxos-documents`.
- Documents use `tenant_id` for organization ownership and optional
  `workspace_id` for workspace-private records.
- Documents without `tenant_id` are public/global and visible to an
  authenticated tenant. Documents without `workspace_id` are organization
  shared. Workspace-private documents require both the organization and the
  matching workspace scope.
- The Go OpenSearch client owns index creation, mappings, keyword queries, and
  bulk indexing. No OpenSearch-native document-level security, field-level
  security, aliases, update/delete API, autocomplete API, aggregation API, or
  reindex API is enabled by this service.
- Semantic retrieval is the process-local tenant-aware QMD provider (with an
  optional remote fallback), not an OpenSearch `knn` query. The OpenSearch
  mapping contains a vector field, but the runtime does not use it for vector
  retrieval.

## Enforcement

`TenantScope` is immutable per operation. Normal reads require an authenticated
organization and fail closed when it is absent. Tenant queries include:

1. the authenticated organization or public documents; and
2. either the requested workspace or workspace-less documents.

The second clause is applied even for organization-only requests so a request
without a workspace cannot read workspace-private records. Index and bulk
writes derive ownership from the authenticated scope and reject mismatched
tenant/workspace fields. System writes are available only through the explicit
internal token path. Request-body organization/workspace fields are not used
to authorize a request.

The gateway derives authenticated scope from JWT claims and removes caller
supplied tenant headers. Compose no longer publishes the Search HTTP port to
the host, and Helm exposes Search as `ClusterIP`; normal users therefore reach
it through the authenticated gateway. Trusted service callers remain a
deployment boundary, and OpenSearch itself is not the application tenant
boundary. The shared OpenSearch client stores no mutable tenant state.

Hybrid, context, and streaming routes pass the same scope to their OpenSearch
and QMD retrieval legs. RRF and graph/citation enrichment operate only on
already scoped candidate hits; graph enrichment does not introduce new
document IDs.

## Capability Matrix

| Capability | Current status | B08 disposition |
| --- | --- | --- |
| Keyword search | Exists | Tenant and workspace filters enforced and tested. |
| Vector search | Exists internally through QMD | Tenant filtering occurs before candidate scoring and is tested. |
| Hybrid search | Exists | OpenSearch and QMD legs receive the same scope; fusion is tested. |
| Count/aggregation/facets | No dedicated API; keyword `total` only | No additional endpoint exists to bypass. Keyword totals are scoped. |
| Autocomplete/suggestions | Does not exist | Not applicable to the current search surface. |
| Direct document retrieval | Does not exist | Not applicable; no document-by-ID route or client method exists. |
| Index/create | Exists | Ownership is derived from authenticated scope; spoofing is rejected. |
| Update | Implicit overwrite through index-by-ID only | Covered by the same scoped index path; no partial-update API exists. |
| Delete | Does not exist | Not applicable to the current application surface. |
| Bulk indexing | Exists | Mixed/cross-tenant ownership is rejected before OpenSearch writes. |
| Reindex/aliases | Does not exist | Projection/replay remains a B09 boundary. |
| Streaming/SSE | Exists | Keyword and hybrid routes require scope before response success. |
| Graph/citation enrichment | Enrichment only | Operates on already scoped candidates and adds no document IDs. |

## Validation

Covered by the search service tests:

- public plus tenant-private keyword visibility and scoped hit totals;
- missing read scope failure;
- cross-tenant bulk indexing rejection;
- tenant/workspace query filter construction;
- organization-only exclusion of workspace-private records;
- tenant-aware local vector retrieval and hybrid ranking;
- missing-scope rejection on regular and streaming HTTP routes.

The live test is `TestLiveOpenSearchTenantIsolation` in
`services/search/internal/search/opensearch_tenant_isolation_test.go`. It
creates and removes a disposable index. It must be run with the repository's
OpenSearch service available and does not claim OpenSearch-native DLS/FLS.

## Not Implemented in This Runtime

There are no production application endpoints for direct document GET,
count-only, aggregations, autocomplete, OpenSearch-native vector queries,
update/delete, bulk update/delete, aliases, or reindex. Those operations
cannot be reported as validated B08 behavior until their owning APIs exist;
the current exposed keyword, hybrid, context, stream, and bulk-index paths
are the enforced surface.