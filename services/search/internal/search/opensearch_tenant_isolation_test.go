package search

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"
)

func TestLiveOpenSearchTenantIsolation(t *testing.T) {
	baseURL := envOr("B08_OPENSEARCH_URL", "https://localhost:9200")
	user := envOr("B08_OPENSEARCH_USER", "admin")
	password := envOr("B08_OPENSEARCH_PASSWORD", "AiRxOS#Search9K")
	caPath := envOr("B08_OPENSEARCH_CA", filepath.Join("..", "..", "..", "..", "infra", "certs", "opensearch-demo-root-ca.pem"))
	transport, err := testTransport(caPath)
	if err != nil {
		t.Skipf("OpenSearch CA unavailable: %v", err)
	}
	httpClient := &http.Client{Transport: transport, Timeout: 3 * time.Second}
	probe, err := httpClient.Get(baseURL + "/_cluster/health")
	if err != nil {
		t.Skipf("OpenSearch unavailable: %v", err)
	}
	probe.Body.Close()

	index := "b08-isolation-test"
	client, err := NewClientWithCACert(baseURL, user, password, index, caPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := client.EnsureIndex(context.Background()); err != nil {
		t.Fatal(err)
	}
	cleanup := func() {
		req, _ := http.NewRequest(http.MethodDelete, baseURL+"/"+index, nil)
		req.SetBasicAuth(user, password)
		res, requestErr := httpClient.Do(req)
		if requestErr == nil {
			res.Body.Close()
		}
	}
	defer cleanup()

	vector := make([]float32, 768)
	vector[0] = 1
	docs := []Document{
		{ID: "b08-public", Title: "B08 Public", Content: "B08 common secret compound", Source: "b08", Embedding: vector},
		{ID: "b08-a1", Title: "B08 Tenant A Shared", Content: "B08 common secret compound", Source: "b08", Embedding: vector},
		{ID: "b08-a2", Title: "B08 Tenant A W1", Content: "B08 common secret compound", Source: "b08", WorkspaceID: "w1", Embedding: vector},
		{ID: "b08-a3", Title: "B08 Tenant A W2", Content: "B08 common secret compound", Source: "b08", WorkspaceID: "w2", Embedding: vector},
		{ID: "b08-b1", Title: "B08 Tenant B Shared", Content: "B08 common secret compound", Source: "b08", Embedding: vector},
		{ID: "b08-b2", Title: "B08 Tenant B W1", Content: "B08 common secret compound", Source: "b08", WorkspaceID: "w1", Embedding: vector},
	}
	if err := client.BulkIndexDocumentsForTenant(context.Background(), docs[:1], TenantScope{System: true}); err != nil {
		t.Fatal(err)
	}
	if err := client.BulkIndexDocumentsForTenant(context.Background(), docs[1:2], TenantScope{OrgID: "tenant-a"}); err != nil {
		t.Fatal(err)
	}
	if err := client.BulkIndexDocumentsForTenant(context.Background(), docs[2:3], TenantScope{OrgID: "tenant-a", WorkspaceID: "w1"}); err != nil {
		t.Fatal(err)
	}
	if err := client.BulkIndexDocumentsForTenant(context.Background(), docs[3:4], TenantScope{OrgID: "tenant-a", WorkspaceID: "w2"}); err != nil {
		t.Fatal(err)
	}
	if err := client.BulkIndexDocumentsForTenant(context.Background(), docs[4:5], TenantScope{OrgID: "tenant-b"}); err != nil {
		t.Fatal(err)
	}
	if err := client.BulkIndexDocumentsForTenant(context.Background(), docs[5:], TenantScope{OrgID: "tenant-b", WorkspaceID: "w1"}); err != nil {
		t.Fatal(err)
	}

	for _, test := range []struct {
		name  string
		scope TenantScope
		want  []string
	}{
		{name: "tenant a organization", scope: TenantScope{OrgID: "tenant-a"}, want: []string{"b08-public", "b08-a1"}},
		{name: "tenant a workspace w1", scope: TenantScope{OrgID: "tenant-a", WorkspaceID: "w1"}, want: []string{"b08-public", "b08-a1", "b08-a2"}},
		{name: "tenant b organization", scope: TenantScope{OrgID: "tenant-b"}, want: []string{"b08-public", "b08-b1"}},
		{name: "tenant b workspace w1", scope: TenantScope{OrgID: "tenant-b", WorkspaceID: "w1"}, want: []string{"b08-public", "b08-b1", "b08-b2"}},
	} {
		t.Run(test.name, func(t *testing.T) {
			result, err := client.QueryForTenantResult(context.Background(), "secret compound", 10, test.scope)
			if err != nil {
				t.Fatal(err)
			}
			if result.Total != len(test.want) {
				t.Fatalf("expected scoped total %d, got %d", len(test.want), result.Total)
			}
			seen := map[string]bool{}
			for _, hit := range result.Hits {
				seen[hit.ID] = true
				if !contains(test.want, hit.ID) {
					t.Errorf("unauthorized document or workspace leaked: %+v", hit)
				}
			}
			for _, id := range test.want {
				if !seen[id] {
					t.Errorf("expected %s in results: %+v", id, result.Hits)
				}
			}
		})
	}
	if _, err := client.QueryForTenant(context.Background(), "secret", 10, TenantScope{}); err == nil {
		t.Fatal("missing tenant scope must fail closed")
	}
	if err := client.BulkIndexDocumentsForTenant(context.Background(), []Document{{ID: "spoof", TenantID: "tenant-b"}}, TenantScope{OrgID: "tenant-a"}); err == nil {
		t.Fatal("cross-tenant bulk indexing must be rejected")
	}

	collisionDocs := []Document{
		{ID: "b08-shared-id", Title: "Tenant A private marker", Content: "tenantalphauniquecollisiontoken", Source: "b08"},
		{ID: "b08-shared-id", Title: "Tenant B private marker", Content: "tenantbravouniquecollisiontoken", Source: "b08"},
	}
	if err := client.BulkIndexDocumentsForTenant(context.Background(), collisionDocs[:1], TenantScope{OrgID: "tenant-a"}); err != nil {
		t.Fatal(err)
	}
	if err := client.BulkIndexDocumentsForTenant(context.Background(), collisionDocs[1:], TenantScope{OrgID: "tenant-b"}); err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		scope       TenantScope
		query       string
		shouldMatch bool
	}{
		{scope: TenantScope{OrgID: "tenant-a"}, query: "tenantalphauniquecollisiontoken", shouldMatch: true},
		{scope: TenantScope{OrgID: "tenant-a"}, query: "tenantbravouniquecollisiontoken", shouldMatch: false},
		{scope: TenantScope{OrgID: "tenant-b"}, query: "tenantbravouniquecollisiontoken", shouldMatch: true},
		{scope: TenantScope{OrgID: "tenant-b"}, query: "tenantalphauniquecollisiontoken", shouldMatch: false},
	} {
		hits, err := client.QueryForTenant(context.Background(), test.query, 10, test.scope)
		if err != nil {
			t.Fatal(err)
		}
		found := false
		for _, hit := range hits {
			if hit.ID == "b08-shared-id" {
				found = true
			}
		}
		if found != test.shouldMatch {
			t.Fatalf("tenant-scoped ID collision leaked or hid data for %+v: %+v", test, hits)
		}
	}

	semanticHits, err := client.SemanticSearchWithOptionsForTenant(
		context.Background(), vector, QueryOptions{PageSize: 10}, TenantScope{OrgID: "tenant-a"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(semanticHits) != 2 {
		t.Fatalf("tenant A semantic query should see public and organization-shared documents, got %+v", semanticHits)
	}
	for _, hit := range semanticHits {
		if hit.ID != "b08-public" && hit.ID != "b08-a1" {
			t.Fatalf("semantic tenant filter leaked document %q", hit.ID)
		}
	}

	oldAvailable := "2025-01-01T00:00:00Z"
	newAvailable := "2025-02-01T00:00:00Z"
	history := []Document{
		{
			ID: "b08-temporal:1", CanonicalID: "b08-temporal", ProjectionKey: "b08-temporal",
			ProjectionVersion: 1, KnowledgeAvailableAt: oldAvailable, Title: "Temporal version one",
			Content: "historical source fact", Source: "b08", TenantID: "tenant-a",
			Identifiers: []string{"B08TEMP"}, Embedding: vector,
		},
		{
			ID: "b08-temporal:2", CanonicalID: "b08-temporal", ProjectionKey: "b08-temporal",
			ProjectionVersion: 2, KnowledgeAvailableAt: newAvailable, Title: "Temporal version two",
			Content: "corrected source fact", Source: "b08", TenantID: "tenant-a",
			Identifiers: []string{"B08TEMP"}, Embedding: vector,
		},
	}
	if err := client.BulkIndexDocumentsForTenant(context.Background(), history, TenantScope{OrgID: "tenant-a"}); err != nil {
		t.Fatal(err)
	}
	if err := client.BulkIndexDocumentsForTenant(context.Background(), history[:1], TenantScope{OrgID: "tenant-a"}); err != nil {
		t.Fatalf("late stale projection replay should be idempotent: %v", err)
	}
	for _, test := range []struct {
		name     string
		cutoff   time.Time
		wantID   string
		wantHits int
	}{
		{
			name: "before first availability", cutoff: time.Date(2024, 12, 31, 23, 59, 59, 0, time.UTC),
			wantHits: 0,
		},
		{
			name: "exactly at first availability", cutoff: time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC),
			wantID: "b08-temporal:1", wantHits: 1,
		},
		{
			name: "exactly at second availability", cutoff: time.Date(2025, 2, 1, 0, 0, 0, 0, time.UTC),
			wantID: "b08-temporal:2", wantHits: 1,
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			hits, err := client.SemanticSearchWithOptionsForTenant(
				context.Background(), vector,
				QueryOptions{PageSize: 10, Identifier: "B08TEMP", AsOf: &test.cutoff},
				TenantScope{OrgID: "tenant-a"},
			)
			if err != nil {
				t.Fatal(err)
			}
			if len(hits) != test.wantHits {
				t.Fatalf("expected %d historical hits, got %+v", test.wantHits, hits)
			}
			if test.wantHits == 1 && hits[0].ID != test.wantID {
				t.Fatalf("expected historical projection %q, got %+v", test.wantID, hits)
			}
		})
	}
}

func contains(values []string, value string) bool {
	sort.Strings(values)
	index := sort.SearchStrings(values, value)
	return index < len(values) && values[index] == value
}

func testTransport(caPath string) (*http.Transport, error) {
	pemBytes, err := os.ReadFile(caPath)
	if err != nil {
		return nil, err
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(pemBytes) {
		return nil, os.ErrInvalid
	}
	return &http.Transport{TLSClientConfig: &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12}}, nil
}

func envOr(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
