package search

import (
	"context"
	"math"
	"testing"
)

func TestQMDEngine_BM25AndVector(t *testing.T) {
	engine := NewQMDEngine()
	ctx := context.Background()

	doc1Embed := []float32{1.0, 0.0, 0.0, 0.5}
	doc2Embed := []float32{0.0, 1.0, 0.5, 0.0}

	engine.IndexDocument(
		"doc1",
		"HER2 Breast Cancer Antibody",
		"Trastuzumab monoclonal antibody treatment for HER2-positive breast cancer patients.",
		"okf_concept",
		doc1Embed,
		150,
	)
	engine.IndexDocument(
		"doc2",
		"EGFR Lung Cancer Inhibitor",
		"Erlotinib tyrosine kinase inhibitor targeting EGFR mutations in non-small cell lung cancer.",
		"okf_concept",
		doc2Embed,
		45,
	)

	// Test BM25 Lexical Search
	bm25Hits, err := engine.SearchBM25(ctx, "breast antibody treatment", 10)
	if err != nil {
		t.Fatalf("SearchBM25 failed: %v", err)
	}
	if len(bm25Hits) == 0 || bm25Hits[0].ID != "doc1" {
		t.Errorf("Expected doc1 as top hit for breast cancer query, got: %+v", bm25Hits)
	}

	// Test Vector Similarity Search
	queryEmbed := []float32{0.0, 0.9, 0.4, 0.1}
	vectorHits, err := engine.SearchVector(ctx, queryEmbed, 10)
	if err != nil {
		t.Fatalf("SearchVector failed: %v", err)
	}
	if len(vectorHits) == 0 || vectorHits[0].ID != "doc2" {
		t.Errorf("Expected doc2 as top vector similarity hit, got: %+v", vectorHits)
	}

	// Test Hybrid Search
	hybridHits, err := engine.SearchHybrid(ctx, "HER2 antibody", doc1Embed, 10)
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

	cs.SetCitationCount("paper-a", 99) // 100 total with log10(1 + 99) = 2.0
	boost := cs.CalculateBoost(99)
	if math.Abs(boost-2.0) > 0.001 {
		t.Errorf("Expected boost ~2.0, got %f", boost)
	}

	cs.AddCoCitation("paper-a", "paper-b")
	cs.AddCoCitation("paper-a", "paper-c")
	coCited := cs.FindCoCited(ctx, []string{"paper-a"}, 5)
	if len(coCited) != 2 {
		t.Errorf("Expected 2 co-cited papers, got %d", len(coCited))
	}

	hits := []Hit{{ID: "paper-a", Score: 1.0}, {ID: "paper-z", Score: 1.0}}
	enriched := cs.EnrichHits(ctx, hits)
	if enriched[0].CitationCount != 99 || enriched[0].Score <= 1.0 {
		t.Errorf("Expected enriched score > 1.0 with citation count 99, got %+v", enriched[0])
	}
}

func TestGraphSearcher(t *testing.T) {
	gs := NewGraphSearcher("http://localhost:8083")
	ctx := context.Background()

	hits := []Hit{{ID: "doc-target-1", Score: 1.0}, {ID: "doc-target-2", Score: 0.8}}
	enriched := gs.EnrichHits(ctx, "breast cancer EGFR receptor target", hits)
	if len(enriched) != 2 {
		t.Fatalf("Expected 2 hits from graph enrichment, got %d", len(enriched))
	}
	if enriched[0].GraphScore == 0 && enriched[1].GraphScore == 0 {
		t.Errorf("Expected heuristic fallback graph scores to be applied, got %+v", enriched)
	}
}

func TestResultRanker_RRF(t *testing.T) {
	ranker := NewResultRanker(60, 0.35, 0.35, 0.15, 0.15)

	listA := []Hit{
		{ID: "doc A", Title: "A", Score: 10.5, Source: "opensearch"},
		{ID: "doc B", Title: "B", Score: 8.2, Source: "opensearch"},
	}
	listB := []Hit{
		{ID: "doc B", Title: "B", Score: 0.95, Source: "google_okf", CitationCount: 50},
		{ID: "doc A", Title: "A", Score: 0.85, Source: "google_okf"},
	}

	ranked := ranker.RankRRF(10, listA, listB)
	if len(ranked) != 2 {
		t.Fatalf("Expected 2 deduplicated hits, got %d", len(ranked))
	}
	if ranked[0].RRFScore == 0.0 {
		t.Errorf("Expected non-zero RRF score, got %f", ranked[0].RRFScore)
	}
	if ranked[0].CitationCount == 0 && ranked[1].CitationCount == 0 {
		t.Errorf("Expected merged metadata to preserve CitationCount, got %+v", ranked)
	}
}

func TestLLMWiki_and_GoogleOKF_Providers(t *testing.T) {
	ctx := context.Background()
	cfgWiki := ProviderConfig{Provider: ProviderLLMWiki}
	wikiProvider, err := NewRetrievalProvider(ctx, cfgWiki)
	if err != nil {
		t.Fatalf("NewRetrievalProvider(LLMWiki) failed: %v", err)
	}
	defer wikiProvider.Close()

	embed := []float32{0.5, 0.5, 0.5, 0.5}
	if err := wikiProvider.Upsert(ctx, "wiki-1", "Concept Page", "OKF frontmatter and references", embed); err != nil {
		t.Fatalf("Upsert on LLMWikiProvider failed: %v", err)
	}

	hits, err := wikiProvider.SimilaritySearch(ctx, embed, 5)
	if err != nil || len(hits) == 0 {
		t.Fatalf("SimilaritySearch on LLMWikiProvider failed or returned empty: hits=%v, err=%v", hits, err)
	}
	if hits[0].Source != ProviderLLMWiki {
		t.Errorf("Expected source %q, got %q", ProviderLLMWiki, hits[0].Source)
	}

	cfgOKF := ProviderConfig{Provider: ProviderGoogleOKF}
	okfProvider, err := NewRetrievalProvider(ctx, cfgOKF)
	if err != nil {
		t.Fatalf("NewRetrievalProvider(GoogleOKF) failed: %v", err)
	}
	defer okfProvider.Close()
	_ = okfProvider.Upsert(ctx, "okf-1", "Google OKF Data", "Structured biomedical triples", embed)
	okfHits, _ := okfProvider.SimilaritySearch(ctx, embed, 5)
	if len(okfHits) == 0 || okfHits[0].Source != ProviderGoogleOKF {
		t.Errorf("Expected GoogleOKFProvider hit with proper source tag, got %v", okfHits)
	}
}
