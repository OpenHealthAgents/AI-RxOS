package search

import (
	"context"
	"math"
	"sort"
	"strings"
	"sync"
	"unicode"
)

// QMDDocument represents an item indexed in the local QMD engine over OKF concepts.
type QMDDocument struct {
	ID        string
	Title     string
	Content   string
	Source    string
	Embedding []float32
	Citations int
	Length    int
	Tokens    map[string]int
}

// QMDEngine provides high-speed in-memory QMD (Query-Metadata-Document) hybrid search
// combining lexical BM25 indexing and dense local vector similarity.
type QMDEngine struct {
	mu          sync.RWMutex
	docs        map[string]*QMDDocument
	index       map[string][]string // token -> list of document IDs
	totalLength int
	docCount    int
	k1          float64
	b           float64
}

// NewQMDEngine initialises a new QMD hybrid search engine with BM25 parameters k1 and b.
func NewQMDEngine() *QMDEngine {
	return &QMDEngine{
		docs:  make(map[string]*QMDDocument),
		index: make(map[string][]string),
		k1:    1.2,
		b:     0.75,
	}
}

// tokenize breaks text into lowercase alphanumeric terms.
func tokenize(text string) []string {
	var tokens []string
	var current strings.Builder
	for _, r := range text {
		if unicode.IsLetter(r) || unicode.IsNumber(r) {
			current.WriteRune(unicode.ToLower(r))
		} else if current.Len() > 0 {
			tokens = append(tokens, current.String())
			current.Reset()
		}
	}
	if current.Len() > 0 {
		tokens = append(tokens, current.String())
	}
	return tokens
}

// IndexDocument adds or updates a document in the QMD inverted index and vector store.
func (e *QMDEngine) IndexDocument(id, title, content, source string, embedding []float32, citations int) {
	e.mu.Lock()
	defer e.mu.Unlock()

	combinedText := title + " " + content
	tokens := tokenize(combinedText)
	tokenCounts := make(map[string]int)
	for _, t := range tokens {
		if len(t) < 2 {
			continue // skip single character words
		}
		tokenCounts[t]++
	}

	docLen := len(tokens)

	// Remove old doc if replacing
	if old, exists := e.docs[id]; exists {
		e.totalLength -= old.Length
	} else {
		e.docCount++
	}

	doc := &QMDDocument{
		ID:        id,
		Title:     title,
		Content:   content,
		Source:    source,
		Embedding: embedding,
		Citations: citations,
		Length:    docLen,
		Tokens:    tokenCounts,
	}
	e.docs[id] = doc
	e.totalLength += docLen

	for t := range tokenCounts {
		e.index[t] = append(e.index[t], id)
	}
}

// SearchBM25 calculates lexical BM25 scores across matching indexed documents.
func (e *QMDEngine) SearchBM25(ctx context.Context, query string, limit int) ([]Hit, error) {
	e.mu.RLock()
	defer e.mu.RUnlock()

	if e.docCount == 0 || query == "" {
		return nil, nil
	}

	queryTokens := tokenize(query)
	if len(queryTokens) == 0 {
		return nil, nil
	}

	avgdl := float64(e.totalLength) / float64(e.docCount)
	scores := make(map[string]float64)

	for _, token := range queryTokens {
		docIDs, ok := e.index[token]
		if !ok {
			continue
		}

		// Count unique docs containing token for IDF
		seen := make(map[string]bool)
		for _, id := range docIDs {
			if _, exists := e.docs[id]; exists {
				seen[id] = true
			}
		}
		docFreq := len(seen)
		if docFreq == 0 {
			continue
		}

		// IDF calculation: ln(1 + (N - n + 0.5) / (n + 0.5))
		idf := math.Log(1.0 + (float64(e.docCount)-float64(docFreq)+0.5)/(float64(docFreq)+0.5))

		for id := range seen {
			doc := e.docs[id]
			tf := float64(doc.Tokens[token])
			// BM25 term score
			num := tf * (e.k1 + 1.0)
			den := tf + e.k1*(1.0-e.b+e.b*(float64(doc.Length)/avgdl))
			scores[id] += idf * (num / den)
		}
	}

	var hits []Hit
	for id, score := range scores {
		doc := e.docs[id]
		hits = append(hits, Hit{
			ID:      doc.ID,
			Title:   doc.Title,
			Snippet: doc.Content,
			Score:   math.Round(score*10000) / 10000,
		})
	}

	sort.Slice(hits, func(i, j int) bool { return hits[i].Score > hits[j].Score })
	if len(hits) > limit {
		hits = hits[:limit]
	}
	return hits, nil
}

// cosineSimilarity computes cosine similarity between two float32 vectors.
func cosineSimilarity(a, b []float32) float64 {
	if len(a) != len(b) || len(a) == 0 {
		return 0.0
	}
	var dot, normA, normB float64
	for i := range a {
		valA := float64(a[i])
		valB := float64(b[i])
		dot += valA * valB
		normA += valA * valA
		normB += valB * valB
	}
	if normA == 0.0 || normB == 0.0 {
		return 0.0
	}
	return dot / (math.Sqrt(normA) * math.Sqrt(normB))
}

// SearchVector performs dense vector similarity ranking across indexed QMD documents.
func (e *QMDEngine) SearchVector(ctx context.Context, embedding []float32, limit int) ([]Hit, error) {
	e.mu.RLock()
	defer e.mu.RUnlock()

	if e.docCount == 0 || len(embedding) == 0 {
		return nil, nil
	}

	var hits []Hit
	for _, doc := range e.docs {
		if len(doc.Embedding) == 0 {
			continue
		}
		sim := cosineSimilarity(embedding, doc.Embedding)
		if sim > 0 {
			hits = append(hits, Hit{
				ID:      doc.ID,
				Title:   doc.Title,
				Snippet: doc.Content,
				Score:   math.Round(sim*10000) / 10000,
			})
		}
	}

	sort.Slice(hits, func(i, j int) bool { return hits[i].Score > hits[j].Score })
	if len(hits) > limit {
		hits = hits[:limit]
	}
	return hits, nil
}

// SearchHybrid combines BM25 lexical scores and local vector cosine similarity.
func (e *QMDEngine) SearchHybrid(ctx context.Context, query string, embedding []float32, limit int) ([]Hit, error) {
	bm25Hits, _ := e.SearchBM25(ctx, query, limit*2)
	vectorHits, _ := e.SearchVector(ctx, embedding, limit*2)

	merged := make(map[string]*Hit)
	for _, h := range bm25Hits {
		hCopy := h
		hCopy.Score *= 0.5 // weight lexical score
		merged[h.ID] = &hCopy
	}
	for _, h := range vectorHits {
		if ex, exists := merged[h.ID]; exists {
			ex.Score += h.Score * 0.5 // add vector weight
		} else {
			hCopy := h
			hCopy.Score *= 0.5
			merged[h.ID] = &hCopy
		}
	}

	var hits []Hit
	for _, h := range merged {
		hits = append(hits, *h)
	}
	sort.Slice(hits, func(i, j int) bool { return hits[i].Score > hits[j].Score })
	if len(hits) > limit {
		hits = hits[:limit]
	}
	return hits, nil
}
