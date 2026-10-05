package search

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestSemanticSearchAppliesTenantFiltersAndReturnsProvenance(t *testing.T) {
	cutoff := time.Date(2025, time.March, 4, 12, 30, 0, 0, time.UTC)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/documents/_search" {
			t.Errorf("unexpected OpenSearch request: %s %s", r.Method, r.URL.Path)
			http.Error(w, "unexpected request", http.StatusNotFound)
			return
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Errorf("decode semantic request: %v", err)
			http.Error(w, "invalid request", http.StatusBadRequest)
			return
		}
		encoded, _ := json.Marshal(body)
		request := string(encoded)
		for _, required := range []string{
			`"vector":[0.25,0.75]`,
			`"tenant_id":"org-a"`,
			`"workspace_id":"workspace-a"`,
			`"entity_type":["publication"]`,
			`"source":["pubmed"]`,
			`"identifiers":"PMID:12345"`,
			`"knowledge_available_at":{"lte":"2025-03-04T12:30:00Z"}`,
		} {
			if !strings.Contains(request, required) {
				t.Errorf("semantic query is missing %s: %s", required, request)
			}
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"hits":{"hits":[{"_id":"publication:1","_score":0.91,"_source":{"canonical_id":"publication","entity_type":"publication","title":"HER2 study","content":"Source-backed abstract","source":"pubmed","tenant_id":"org-a","workspace_id":"workspace-a","source_record_id":"record-1","source_url":"https://pubmed.ncbi.nlm.nih.gov/12345/","published_at":"2024","knowledge_available_at":"2025-03-04T12:30:00Z","identifiers":["PMID:12345"],"metadata":{"evidence_count":2}}}]}}`))
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "", "", "documents")
	if err != nil {
		t.Fatal(err)
	}
	hits, err := client.SemanticSearchWithOptionsForTenant(context.Background(), []float32{0.25, 0.75}, QueryOptions{
		PageSize: 10, EntityTypes: []string{"publication"}, Sources: []string{"pubmed"},
		Identifier: "PMID:12345", AsOf: &cutoff,
	}, TenantScope{OrgID: "org-a", WorkspaceID: "workspace-a"})
	if err != nil {
		t.Fatal(err)
	}
	if len(hits) != 1 {
		t.Fatalf("expected one semantic hit, got %d", len(hits))
	}
	hit := hits[0]
	if hit.CanonicalID != "publication" || hit.SourceRecordID != "record-1" ||
		hit.PublishedAt != "2024" || hit.KnowledgeAvailableAt != cutoff.Format(time.RFC3339Nano) {
		t.Fatalf("semantic hit lost canonical provenance or temporal metadata: %+v", hit)
	}
	if hit.Metadata["evidence_count"] != float64(2) {
		t.Fatalf("semantic hit lost evidence metadata: %+v", hit.Metadata)
	}
}

func TestKeywordSearchReturnsFacetsHighlightsAndStablePage(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatalf("decode keyword request: %v", err)
		}
		if body["from"] != float64(20) || body["size"] != float64(10) {
			t.Errorf("unexpected page window: from=%v size=%v", body["from"], body["size"])
		}
		encoded, _ := json.Marshal(body)
		request := string(encoded)
		for _, required := range []string{`"identifiers":"PMID:12345"`, `"title"`, `"content"`} {
			if !strings.Contains(request, required) {
				t.Errorf("keyword request is missing %s: %s", required, request)
			}
		}

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"hits":{"total":{"value":21},"hits":[{"_id":"publication:2","_score":1.4,
				"highlight":{"content":["...abstract match..."]},
				"_source":{"canonical_id":"publication","title":"HER2 study","content":"full abstract","source":"pubmed","identifiers":["PMID:12345"]}}]},
			"aggregations":{"sources":{"buckets":[{"key":"pubmed","doc_count":21}]},"entity_types":{"buckets":[{"key":"publication","doc_count":21}]}}
		}`))
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "", "", "documents")
	if err != nil {
		t.Fatal(err)
	}
	result, err := client.QueryWithOptionsForTenant(context.Background(), QueryOptions{
		Query: "HER2", Identifier: "PMID:12345", Page: 3, PageSize: 10,
	}, TenantScope{OrgID: "org-a"})
	if err != nil {
		t.Fatal(err)
	}
	if result.Total != 21 || len(result.Hits) != 1 {
		t.Fatalf("unexpected search result totals: %+v", result)
	}
	if result.Hits[0].Snippet != "...abstract match..." {
		t.Fatalf("expected highlighted snippet, got %q", result.Hits[0].Snippet)
	}
	if len(result.Facets["sources"]) != 1 || result.Facets["sources"][0].Value != "pubmed" {
		t.Fatalf("expected deterministic source facet, got %+v", result.Facets)
	}
}

func TestSemanticSearchRetriesLegacyNMSLIBWithPostFilter(t *testing.T) {
	requestCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++
		if requestCount == 1 {
			http.Error(w, `{"reason":"Engine [NMSLIB] does not support filters"}`, http.StatusBadRequest)
			return
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatalf("decode compatibility query: %v", err)
		}
		knnQuery := body["query"].(map[string]any)["knn"].(map[string]any)["embedding"].(map[string]any)
		if _, exists := knnQuery["filter"]; exists {
			t.Errorf("legacy retry must not use unsupported in-kNN filters: %+v", knnQuery)
		}
		if knnQuery["k"] != float64(1000) {
			t.Errorf("expected bounded candidate expansion to 1000, got %v", knnQuery["k"])
		}
		postFilter := body["post_filter"].(map[string]any)
		encoded, _ := json.Marshal(postFilter)
		if !strings.Contains(string(encoded), `"tenant_id":"org-a"`) {
			t.Errorf("legacy retry dropped tenant isolation: %s", encoded)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"hits":{"hits":[]}}`))
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "", "", "documents")
	if err != nil {
		t.Fatal(err)
	}
	_, err = client.SemanticSearchWithOptionsForTenant(context.Background(), []float32{0.5}, QueryOptions{
		PageSize: 10,
	}, TenantScope{OrgID: "org-a"})
	if err != nil {
		t.Fatal(err)
	}
	if requestCount != 2 {
		t.Fatalf("expected one compatibility retry, got %d requests", requestCount)
	}
}
