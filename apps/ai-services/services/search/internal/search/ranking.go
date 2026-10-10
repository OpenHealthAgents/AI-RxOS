package search

import (
	"math"
	"sort"
)

// ResultRanker performs Reciprocal Rank Fusion (RRF) and multi-signal weighted linear
// combination across keyword, vector, QMD, graph, and citation hit lists.
type ResultRanker struct {
	k              int // RRF constant (default 60)
	weightBM25     float64
	weightVector   float64
	weightGraph    float64
	weightCitation float64
}

// NewResultRanker constructs a new ResultRanker with customizable RRF constant K and weights.
func NewResultRanker(k int, wBM25, wVector, wGraph, wCitation float64) *ResultRanker {
	if k <= 0 {
		k = 60
	}
	return &ResultRanker{
		k:              k,
		weightBM25:     wBM25,
		weightVector:   wVector,
		weightGraph:    wGraph,
		weightCitation: wCitation,
	}
}

// RankRRF executes Reciprocal Rank Fusion across multiple candidate hit lists:
// Score_RRF(d) = sum( 1.0 / (k + rank_i) ).
func (r *ResultRanker) RankRRF(limit int, hitLists ...[]Hit) []Hit {
	rrfScores := make(map[string]float64)
	mergedHits := make(map[string]Hit)

	for _, list := range hitLists {
		for rankIdx, hit := range list {
			rank := float64(rankIdx + 1) // 1-indexed rank
			rrfScores[hit.ID] += 1.0 / (float64(r.k) + rank)

			if existing, present := mergedHits[hit.ID]; present {
				// Merge richest metadata fields across candidate sources
				if existing.Title == "" && hit.Title != "" {
					existing.Title = hit.Title
				}
				if existing.Snippet == "" && hit.Snippet != "" {
					existing.Snippet = hit.Snippet
				}
				if existing.CitationCount < hit.CitationCount {
					existing.CitationCount = hit.CitationCount
				}
				if existing.GraphScore < hit.GraphScore {
					existing.GraphScore = hit.GraphScore
				}
				if existing.EvidenceContext == nil {
					existing.EvidenceContext = hit.EvidenceContext
				}
				existing.Contradictory = existing.Contradictory || hit.Contradictory
				if len(existing.Aliases) == 0 {
					existing.Aliases = hit.Aliases
				}
				if len(existing.Identifiers) == 0 {
					existing.Identifiers = hit.Identifiers
				}
				if existing.SourceRecordID == "" {
					existing.SourceRecordID = hit.SourceRecordID
				}
				if existing.SourceURL == "" {
					existing.SourceURL = hit.SourceURL
				}
				if existing.PublishedAt == "" {
					existing.PublishedAt = hit.PublishedAt
				}
				if existing.KnowledgeAvailableAt == "" {
					existing.KnowledgeAvailableAt = hit.KnowledgeAvailableAt
				}
				if existing.Metadata == nil {
					existing.Metadata = hit.Metadata
				}
				if len(existing.Highlights) == 0 {
					existing.Highlights = hit.Highlights
				}
				if existing.Source != hit.Source && hit.Source != "" {
					if existing.Source == "opensearch" || existing.Source == "" {
						existing.Source = hit.Source
					}
				}
				mergedHits[hit.ID] = existing
			} else {
				mergedHits[hit.ID] = hit
			}
		}
	}

	var finalHits []Hit
	for id, hit := range mergedHits {
		hit.RRFScore = math.Round(rrfScores[id]*100000) / 100000
		citationSignal := math.Min(1.0, math.Log10(1.0+float64(hit.CitationCount))/4.0)
		hit.Score = hit.RRFScore + r.weightGraph*hit.GraphScore + r.weightCitation*citationSignal
		hit.Score = math.Round(hit.Score*10000) / 10000
		finalHits = append(finalHits, hit)
	}

	sort.Slice(finalHits, func(i, j int) bool {
		if finalHits[i].Score == finalHits[j].Score {
			return finalHits[i].ID < finalHits[j].ID // Stable tie breaking
		}
		return finalHits[i].Score > finalHits[j].Score
	})

	if len(finalHits) > limit && limit > 0 {
		finalHits = finalHits[:limit]
	}
	return finalHits
}

// normalizeScores rescales hit scores in-place to [0, 1] range for weighted fusion.
func normalizeScores(hits []Hit) map[string]float64 {
	norm := make(map[string]float64)
	if len(hits) == 0 {
		return norm
	}
	var minScore, maxScore float64 = hits[0].Score, hits[0].Score
	for _, h := range hits {
		if h.Score < minScore {
			minScore = h.Score
		}
		if h.Score > maxScore {
			maxScore = h.Score
		}
	}
	delta := maxScore - minScore
	for _, h := range hits {
		if delta == 0 {
			norm[h.ID] = 1.0
		} else {
			norm[h.ID] = (h.Score - minScore) / delta
		}
	}
	return norm
}

// RankWeighted combines BM25 lexical matches and dense semantic vector hits using configured weights.
func (r *ResultRanker) RankWeighted(bm25Hits, vectorHits []Hit, limit int) []Hit {
	normBM25 := normalizeScores(bm25Hits)
	normVector := normalizeScores(vectorHits)

	merged := make(map[string]Hit)
	for _, h := range bm25Hits {
		merged[h.ID] = h
	}
	for _, h := range vectorHits {
		if ex, present := merged[h.ID]; present {
			if ex.Source == "opensearch" && h.Source != "" {
				ex.Source = h.Source
			}
			merged[h.ID] = ex
		} else {
			merged[h.ID] = h
		}
	}

	var results []Hit
	for id, hit := range merged {
		sBM25 := normBM25[id]
		sVector := normVector[id]
		composite := (r.weightBM25 * sBM25) + (r.weightVector * sVector) + (r.weightGraph * hit.GraphScore)
		if hit.CitationCount > 0 {
			citBoost := math.Log10(1.0 + float64(hit.CitationCount))
			composite += r.weightCitation * math.Min(1.0, citBoost/4.0)
		}
		hit.Score = math.Round(composite*10000) / 10000
		results = append(results, hit)
	}

	sort.Slice(results, func(i, j int) bool { return results[i].Score > results[j].Score })
	if len(results) > limit && limit > 0 {
		results = results[:limit]
	}
	return results
}
