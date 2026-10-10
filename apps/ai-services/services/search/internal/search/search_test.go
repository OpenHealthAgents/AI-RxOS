package search

import (
	"context"
	"math"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestQMDEngine_BM25AndVector(t *testing.T) {
	engine := NewQMDEngine()
	ctx := context.Background()
	system := TenantScope{System: true}

	doc1Embed := []float32{1.0, 0.0, 0.0, 0.5}
	doc2Embed := []float32{0.0, 1.0, 0.5, 0.0}

	engine.IndexDocumentForTenant("doc1", "HER2 Breast Cancer Antibody", "Trastuzumab monoclonal antibody treatment for HER2-positive breast cancer patients.", "okf_concept", doc1Embed, 150, system)
	engine.IndexDocumentForTenant("doc2", "EGFR Lung Cancer Inhibitor", "Erlotinib tyrosine kinase inhibitor targeting EGFR mutations in non-small cell lung cancer.", "okf_concept", doc2Embed, 45, system)

	bm25Hits, err := engine.SearchBM25ForTenant(ctx, "breast antibody treatment", 10, system)
	if err != nil {
		t.Fatalf("SearchBM25 failed: %v", err)
	}
	if len(bm25Hits) == 0 || bm25Hits[0].ID != "doc1" {
		t.Errorf("Expected doc1 as top hit for breast cancer query, got: %+v", bm25Hits)
	}

	queryEmbed := []float32{0.0, 0.9, 0.4, 0.1}
	vectorHits, err := engine.SearchVectorForTenant(ctx, queryEmbed, 10, system)
	if err != nil {
		t.Fatalf("SearchVector failed: %v", err)
	}
	if len(vectorHits) == 0 || vectorHits[0].ID != "doc2" {
		t.Errorf("Expected doc2 as top vector hit, got: %+v", vectorHits)
	}

	hybridHits, err := engine.SearchHybridForTenant(ctx, "HER2 antibody", doc1Embed, 10, system)
	if err != nil {
		t.Fatalf("SearchHybrid failed: %v", err)
	}
	if len(hybridHits) == 0 || hybridHits[0].ID != "doc1" {
		t.Errorf("Expected doc1 as top hybrid hit, got: %+v", hybridHits)
	}
}

func TestCitationSearcher(t *testing.T) {
	cs := NewCitationSearcher()
	ctx := context.Background()
	cs.SetCitationCount("paper-a", 99)
	boost := cs.CalculateBoost(99)
	if math.Abs(boost-2.0) > 0.001 {
		t.Errorf("Expected boost ~2.0, got %f", boost)
	}
	cs.AddCoCitation("paper-a", "paper-b")
	cs.AddCoCitation("paper-a", "paper-c")
	if coCited := cs.FindCoCited(ctx, []string{"paper-a"}, 5); len(coCited) != 2 {
		t.Errorf("Expected 2 co-cited papers, got %d", len(coCited))
	}
	hits := []Hit{{ID: "paper-a", Score: 1.0}, {ID: "paper-z", Score: 1.0}}
	enriched := cs.EnrichHits(ctx, hits)
	if enriched[0].CitationCount != 99 || enriched[0].Score <= 1.0 {
		t.Errorf("Expected enriched score > 1.0 with citation count 99, got %+v", enriched[0])
	}
}

func TestGraphSearcher(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer test-token" {
			t.Errorf("expected forwarded bearer token, got %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"relevance":{"canonical-1":0.75}}`))
	}))
	defer server.Close()
	gs := NewGraphSearcher(server.URL)
	hits := []Hit{{ID: "canonical-1:3", CanonicalID: "canonical-1", Score: 1.0}, {ID: "canonical-2:4", CanonicalID: "canonical-2", Score: 0.8}}
	enriched, err := gs.EnrichHits(context.Background(), "breast cancer EGFR receptor target", hits, "Bearer test-token")
	if err != nil {
		t.Fatal(err)
	}
	if len(enriched) != 2 {
		t.Fatalf("Expected 2 hits from graph enrichment, got %d", len(enriched))
	}
	if enriched[0].GraphScore != 0.75 || enriched[1].GraphScore != 0 {
		t.Errorf("Expected only KG-returned graph scores, got %+v", enriched)
	}
}

func TestGraphSearcherReturnsKGFailureInsteadOfSyntheticScores(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "unavailable", http.StatusServiceUnavailable)
	}))
	defer server.Close()
	gs := NewGraphSearcher(server.URL)
	_, err := gs.QueryGraphRelevance(
		context.Background(), "EGFR target", []string{"canonical-1"}, "Bearer test-token",
	)
	if err == nil {
		t.Fatal("expected graph backend failure to be explicit")
	}
}

func TestResultRanker_RRF(t *testing.T) {
	ranker := NewResultRanker(60, 0.35, 0.35, 0.15, 0.15)
	listA := []Hit{{ID: "doc A", Title: "A", Score: 10.5, Source: "opensearch"}, {ID: "doc B", Title: "B", Score: 8.2, Source: "opensearch"}}
	listB := []Hit{{ID: "doc B", Title: "B", Score: 0.95, Source: "google_okf", CitationCount: 50}, {ID: "doc A", Title: "A", Score: 0.85, Source: "google_okf"}}
	ranked := ranker.RankRRF(10, listA, listB)
	if len(ranked) != 2 || ranked[0].RRFScore == 0.0 {
		t.Fatalf("Expected ranked deduplicated hits, got %+v", ranked)
	}
	if ranked[0].CitationCount == 0 && ranked[1].CitationCount == 0 {
		t.Errorf("Expected citation metadata to survive ranking, got %+v", ranked)
	}
}

func TestLLMWiki_and_GoogleOKF_Providers(t *testing.T) {
	ctx := context.Background()
	system := TenantScope{System: true}
	wikiProvider, err := NewRetrievalProvider(ctx, ProviderConfig{Provider: ProviderLLMWiki})
	if err != nil {
		t.Fatalf("NewRetrievalProvider(LLMWiki) failed: %v", err)
	}
	defer wikiProvider.Close()
	embed := []float32{0.5, 0.5, 0.5, 0.5}
	if err := wikiProvider.UpsertForTenant(ctx, "wiki-1", "Concept Page", "OKF frontmatter and references", embed, system); err != nil {
		t.Fatalf("Upsert on LLMWikiProvider failed: %v", err)
	}
	hits, err := wikiProvider.SimilaritySearchForTenant(ctx, embed, 5, system)
	if err != nil || len(hits) == 0 || hits[0].Source != ProviderLLMWiki {
		t.Fatalf("LLMWikiProvider search failed: hits=%v, err=%v", hits, err)
	}

	okfProvider, err := NewRetrievalProvider(ctx, ProviderConfig{Provider: ProviderGoogleOKF})
	if err != nil {
		t.Fatalf("NewRetrievalProvider(GoogleOKF) failed: %v", err)
	}
	defer okfProvider.Close()
	if err := okfProvider.UpsertForTenant(ctx, "okf-1", "Google OKF Data", "Structured biomedical triples", embed, system); err != nil {
		t.Fatal(err)
	}
	okfHits, _ := okfProvider.SimilaritySearchForTenant(ctx, embed, 5, system)
	if len(okfHits) == 0 || okfHits[0].Source != ProviderGoogleOKF {
		t.Errorf("Expected GoogleOKFProvider hit, got %v", okfHits)
	}
}
