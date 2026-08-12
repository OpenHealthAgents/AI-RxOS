package search

import (
	"context"
	"math"
	"sort"
	"sync"
)

// CitationSearcher calculates authority scores and queries citation graph networks
// to enhance literature search results with co-citation and authority signals.
type CitationSearcher struct {
	mu           sync.RWMutex
	citations    map[string]int      // doc ID -> citation count
	coCitations  map[string][]string // doc ID -> list of co-cited document IDs
}

// NewCitationSearcher initialises a new CitationSearcher with local cache capabilities.
func NewCitationSearcher() *CitationSearcher {
	return &CitationSearcher{
		citations:   make(map[string]int),
		coCitations: make(map[string][]string),
	}
}

// SetCitationCount caches citation authority count for a document ID.
func (c *CitationSearcher) SetCitationCount(docID string, count int) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.citations[docID] = count
}

// AddCoCitation links two document IDs in the co-citation network graph.
func (c *CitationSearcher) AddCoCitation(docA, docB string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.coCitations[docA] = append(c.coCitations[docA], docB)
	c.coCitations[docB] = append(c.coCitations[docB], docA)
}

// CalculateBoost computes a logarithmic dampening authority boost for citations:
// boost = log10(1 + citationCount).
func (c *CitationSearcher) CalculateBoost(citationCount int) float64 {
	if citationCount <= 0 {
		return 0.0
	}
	boost := math.Log10(1.0 + float64(citationCount))
	return math.Round(boost*10000) / 10000
}

// EnrichHits evaluates citation counts and attaches authority boost multipliers to hits.
func (c *CitationSearcher) EnrichHits(ctx context.Context, hits []Hit) []Hit {
	c.mu.RLock()
	defer c.mu.RUnlock()

	enriched := make([]Hit, len(hits))
	for i, h := range hits {
		count := h.CitationCount
		if count == 0 {
			if stored, exists := c.citations[h.ID]; exists {
				count = stored
			}
		}
		boost := c.CalculateBoost(count)
		hCopy := h
		hCopy.CitationCount = count
		// Apply lightweight authority multiplier to score while preserving ordering signals
		if boost > 0 {
			hCopy.Score += boost * 0.1
			hCopy.Score = math.Round(hCopy.Score*10000) / 10000
		}
		enriched[i] = hCopy
	}
	return enriched
}

// FindCoCited identifies documents frequently co-cited with the provided candidate IDs.
func (c *CitationSearcher) FindCoCited(ctx context.Context, docIDs []string, limit int) []Hit {
	c.mu.RLock()
	defer c.mu.RUnlock()

	frequency := make(map[string]int)
	for _, id := range docIDs {
		if related, exists := c.coCitations[id]; exists {
			for _, rel := range related {
				frequency[rel]++
			}
		}
	}

	var hits []Hit
	for relID, freq := range frequency {
		hits = append(hits, Hit{
			ID:            relID,
			Score:         math.Round(float64(freq)*10.0) / 10.0,
			Source:        "citation_network",
			CitationCount: c.citations[relID],
		})
	}
	sort.Slice(hits, func(i, j int) bool { return hits[i].Score > hits[j].Score })
	if len(hits) > limit {
		hits = hits[:limit]
	}
	return hits
}
