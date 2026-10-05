package search

import (
	"context"
	"testing"
)

// These tests prove the Prompt 8 organization/workspace isolation
// guarantee for the LLM Wiki / QMD retrieval layer: a query scoped to one
// organization must never see another organization's documents, and a
// query scoped to one workspace must never see another workspace's
// private (workspace-scoped) documents within the same organization.

func TestTenantScope_CrossOrganizationIsolation(t *testing.T) {
	engine := NewQMDEngine()
	ctx := context.Background()
	embed := []float32{1.0, 0.0, 0.0}

	engine.IndexDocumentForTenant("doc-a", "Org A Secret", "confidential org A content", "okf_concept", embed, 0, TenantScope{OrgID: "org-a"})
	engine.IndexDocumentForTenant("doc-b", "Org B Secret", "confidential org B content", "okf_concept", embed, 0, TenantScope{OrgID: "org-b"})

	hitsA, err := engine.SearchVectorForTenant(ctx, embed, 10, TenantScope{OrgID: "org-a"})
	if err != nil {
		t.Fatalf("SearchVectorForTenant failed: %v", err)
	}
	for _, h := range hitsA {
		if h.ID == "doc-b" {
			t.Fatalf("organization A query must never see organization B's document, got %+v", hitsA)
		}
	}
	found := false
	for _, h := range hitsA {
		if h.ID == "doc-a" {
			found = true
		}
	}
	if !found {
		t.Fatalf("organization A query should see its own document, got %+v", hitsA)
	}

	bm25HitsB, err := engine.SearchBM25ForTenant(ctx, "confidential", 10, TenantScope{OrgID: "org-b"})
	if err != nil {
		t.Fatalf("SearchBM25ForTenant failed: %v", err)
	}
	for _, h := range bm25HitsB {
		if h.ID == "doc-a" {
			t.Fatalf("organization B query must never see organization A's document, got %+v", bm25HitsB)
		}
	}
}

func TestTenantScope_CrossWorkspaceIsolationWithinSameOrganization(t *testing.T) {
	engine := NewQMDEngine()
	ctx := context.Background()
	embed := []float32{0.0, 1.0, 0.0}

	engine.IndexDocumentForTenant("doc-ws1", "Workspace 1 private", "private workspace 1 content", "okf_concept", embed, 0, TenantScope{OrgID: "org-a", WorkspaceID: "ws-1"})
	engine.IndexDocumentForTenant("doc-ws2", "Workspace 2 private", "private workspace 2 content", "okf_concept", embed, 0, TenantScope{OrgID: "org-a", WorkspaceID: "ws-2"})
	// Org-shared (no workspace) content should be visible to every workspace in the org.
	engine.IndexDocumentForTenant("doc-shared", "Org shared", "shared org content", "okf_concept", embed, 0, TenantScope{OrgID: "org-a"})

	hitsWS1, err := engine.SearchVectorForTenant(ctx, embed, 10, TenantScope{OrgID: "org-a", WorkspaceID: "ws-1"})
	if err != nil {
		t.Fatalf("SearchVectorForTenant failed: %v", err)
	}
	seen := map[string]bool{}
	for _, h := range hitsWS1 {
		seen[h.ID] = true
	}
	if seen["doc-ws2"] {
		t.Fatalf("workspace 1 query must never see workspace 2's private document, got %+v", hitsWS1)
	}
	if !seen["doc-ws1"] {
		t.Fatalf("workspace 1 query should see its own document, got %+v", hitsWS1)
	}
	if !seen["doc-shared"] {
		t.Fatalf("workspace 1 query should see org-shared documents, got %+v", hitsWS1)
	}
}

func TestTenantScope_UnscopedQuerySeesEverything_BackwardCompat(t *testing.T) {
	engine := NewQMDEngine()
	ctx := context.Background()
	embed := []float32{1.0, 1.0, 0.0}

	engine.IndexDocumentForTenant("legacy-doc", "Legacy", "legacy untenanted content", "benchmark", embed, 0, TenantScope{System: true})
	engine.IndexDocumentForTenant("tenant-doc", "Tenant", "tenant scoped content", "okf_concept", embed, 0, TenantScope{OrgID: "org-a"})

	if _, err := engine.SearchVector(ctx, embed, 10); err == nil {
		t.Fatal("unscoped vector query must fail closed")
	}
}

func TestTenantScope_UntenantedDocumentsAreSharedAcrossOrganizations(t *testing.T) {
	engine := NewQMDEngine()
	ctx := context.Background()
	embed := []float32{0.5, 0.5, 0.5}

	// Content indexed before tenant scoping existed (no TenantScope) should
	// remain visible to every tenant, rather than becoming orphaned.
	engine.IndexDocumentForTenant("pre-existing", "Pre-existing", "shared legacy content", "okf_concept", embed, 0, TenantScope{System: true})

	hits, err := engine.SearchVectorForTenant(ctx, embed, 10, TenantScope{OrgID: "org-a"})
	if err != nil {
		t.Fatalf("SearchVectorForTenant failed: %v", err)
	}
	if len(hits) != 1 || hits[0].ID != "pre-existing" {
		t.Fatalf("expected untenanted legacy document to remain visible, got %+v", hits)
	}
}

func TestLLMWikiProvider_UpsertForTenant_IsolatesSimilaritySearch(t *testing.T) {
	ctx := context.Background()
	provider, err := NewLLMWikiProvider(ProviderConfig{})
	if err != nil {
		t.Fatalf("NewLLMWikiProvider failed: %v", err)
	}
	defer provider.Close()

	embed := []float32{0.2, 0.4, 0.6}
	if err := provider.UpsertForTenant(ctx, "org-a-doc", "Org A", "org a content", embed, TenantScope{OrgID: "org-a"}); err != nil {
		t.Fatalf("UpsertForTenant failed: %v", err)
	}
	if err := provider.UpsertForTenant(ctx, "org-b-doc", "Org B", "org b content", embed, TenantScope{OrgID: "org-b"}); err != nil {
		t.Fatalf("UpsertForTenant failed: %v", err)
	}

	hits, err := provider.SimilaritySearchForTenant(ctx, embed, 10, TenantScope{OrgID: "org-a"})
	if err != nil {
		t.Fatalf("SimilaritySearchForTenant failed: %v", err)
	}
	for _, h := range hits {
		if h.ID == "org-b-doc" {
			t.Fatalf("LLMWikiProvider leaked org-b's document into org-a's search results: %+v", hits)
		}
	}
}
