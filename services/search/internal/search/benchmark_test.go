package search

import (
	"context"
	"fmt"
	"math/rand"
	"testing"
)

// makeSyntheticDocument generates realistic biomedical text and 768-dim float32 vectors for benchmarking.
func makeSyntheticDocument(id int) (string, string, string, []float32) {
	docID := fmt.Sprintf("doc-%d", id)
	title := fmt.Sprintf("Biomedical Study on Protein %d and Drug Treatment", id%100)
	content := fmt.Sprintf("Clinical trials demonstrated therapeutic activity of kinase inhibitor %d against receptor target mutations in human disease cohorts with significant efficacy over control.", id)
	embed := make([]float32, 768)
	for i := range embed {
		embed[i] = float32(rand.Float64())
	}
	return docID, title, content, embed
}

func BenchmarkQmdBM25(b *testing.B) {
	engine := NewQMDEngine()
	for i := 0; i < 500; i++ {
		id, title, content, embed := makeSyntheticDocument(i)
		engine.IndexDocument(id, title, content, "benchmark", embed, i%50)
	}
	ctx := context.Background()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = engine.SearchBM25(ctx, "kinase inhibitor therapeutic activity", 20)
	}
}

func BenchmarkVectorSimilarity(b *testing.B) {
	engine := NewQMDEngine()
	for i := 0; i < 500; i++ {
		id, title, content, embed := makeSyntheticDocument(i)
		engine.IndexDocument(id, title, content, "benchmark", embed, i%50)
	}
	ctx := context.Background()
	queryEmbed := make([]float32, 768)
	for i := range queryEmbed {
		queryEmbed[i] = float32(rand.Float64())
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = engine.SearchVector(ctx, queryEmbed, 20)
	}
}

func BenchmarkReciprocalRankFusion(b *testing.B) {
	ranker := NewResultRanker(60, 0.35, 0.35, 0.15, 0.15)
	listA := make([]Hit, 200)
	listB := make([]Hit, 200)
	listC := make([]Hit, 200)

	for i := 0; i < 200; i++ {
		listA[i] = Hit{ID: fmt.Sprintf("doc-%d", i), Score: float64(200 - i), Source: "opensearch"}
		listB[i] = Hit{ID: fmt.Sprintf("doc-%d", 199-i), Score: float64(i) * 0.5, Source: "google_okf", CitationCount: i}
		listC[i] = Hit{ID: fmt.Sprintf("doc-%d", (i*7)%200), Score: float64(i) * 0.2, Source: "llm_wiki"}
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = ranker.RankRRF(50, listA, listB, listC)
	}
}

// Benchmark100MScalingSimulation benchmarks sharded multi-signal ranking computations simulating
// throughput across 16 primary OpenSearch shards for 100M document capacity.
func Benchmark100MScalingSimulation(b *testing.B) {
	numShards := 16
	shardEngines := make([]*QMDEngine, numShards)
	for s := 0; s < numShards; s++ {
		shardEngines[s] = NewQMDEngine()
		for i := 0; i < 50; i++ {
			id, title, content, embed := makeSyntheticDocument((s * 1000) + i)
			shardEngines[s].IndexDocument(id, title, content, fmt.Sprintf("shard-%d", s), embed, i)
		}
	}

	ctx := context.Background()
	ranker := NewResultRanker(60, 0.35, 0.35, 0.15, 0.15)
	query := "kinase inhibitor mutations"
	queryEmbed := make([]float32, 768)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var allHitLists [][]Hit
		for s := 0; s < numShards; s++ {
			hBM, _ := shardEngines[s].SearchBM25(ctx, query, 10)
			hVec, _ := shardEngines[s].SearchVector(ctx, queryEmbed, 10)
			allHitLists = append(allHitLists, hBM, hVec)
		}
		_ = ranker.RankRRF(50, allHitLists...)
	}
}
