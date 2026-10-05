package search

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestCanonicalDocumentIncludesStableIdentity(t *testing.T) {
	document := Document{
		ID:          "canonical-uuid",
		CanonicalID: "canonical-uuid",
		EntityType:  "therapeutic_asset",
		Title:       "Demo asset",
		Content:     `{"synthetic":true}`,
		Source:      "canonical_entity",
	}

	encoded, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	var fields map[string]any
	if err := json.Unmarshal(encoded, &fields); err != nil {
		t.Fatal(err)
	}
	if fields["canonical_id"] != "canonical-uuid" || fields["entity_type"] != "therapeutic_asset" {
		t.Fatalf("canonical identity fields missing from search document: %s", encoded)
	}
}

func TestEnsureIndexPreservesExistingMappings(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodHead:
			w.WriteHeader(http.StatusOK)
		case r.Method == http.MethodGet && r.URL.Path == "/documents/_mapping":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"documents":{"mappings":{"properties":{"tenant_id":{"type":"keyword"}}}}}`))
		default:
			t.Errorf("unexpected OpenSearch request: %s %s", r.Method, r.URL.Path)
			http.Error(w, "unexpected request", http.StatusInternalServerError)
		}
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "", "", "documents")
	if err != nil {
		t.Fatal(err)
	}
	if err := client.EnsureIndex(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestBulkIndexDocumentsReturnsItemFailures(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"errors":true,"items":[{"index":{"status":400}}]}`))
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "", "", "documents")
	if err != nil {
		t.Fatal(err)
	}
	err = client.BulkIndexDocuments(context.Background(), []Document{{
		ID: "canonical-id", CanonicalID: "canonical-id", EntityType: "therapeutic_asset",
		Title: "Demo", Content: "{}", Source: "canonical_entity",
	}})
	if err == nil || !strings.Contains(err.Error(), "failed document operations") {
		t.Fatalf("expected item-level bulk failure, got %v", err)
	}
}

func TestQueryForTenantAddsOrganizationAndWorkspaceFilters(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		encoded, _ := json.Marshal(body)
		request := string(encoded)
		if !strings.Contains(request, `"tenant_id"`) || !strings.Contains(request, `"org-a"`) || !strings.Contains(request, `"workspace_id"`) {
			t.Fatalf("tenant filters missing from OpenSearch query: %s", request)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"hits":{"hits":[]}}`))
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "", "", "documents")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.QueryForTenant(context.Background(), "secret", 10, TenantScope{OrgID: "org-a", WorkspaceID: "ws-1"}); err != nil {
		t.Fatal(err)
	}
}

func TestQueryForTenantOrganizationScopeExcludesWorkspacePrivateDocuments(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		encoded, _ := json.Marshal(body)
		request := string(encoded)
		if !strings.Contains(request, `"workspace_id"`) || !strings.Contains(request, `"must_not"`) || !strings.Contains(request, `"exists"`) {
			t.Fatalf("organization-only query must exclude workspace-private documents: %s", request)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"hits":{"hits":[]}}`))
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "", "", "documents")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.QueryForTenant(context.Background(), "secret", 10, TenantScope{OrgID: "org-a"}); err != nil {
		t.Fatal(err)
	}
}
