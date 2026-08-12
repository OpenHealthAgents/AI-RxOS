package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"

	"github.com/openhealthagents/ai-rxos/services/search/internal/search"
)

// StreamQuery handles GET /api/v1/search/stream?q=...&limit=... — Server-Sent Events (SSE)
// streaming of keyword matches and progress events.
func (h *SearchHandler) StreamQuery(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"code": "stream_unsupported", "message": "streaming not supported by client connection"})
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(http.StatusOK)

	sendEvent := func(event string, data any) {
		payload, _ := json.Marshal(data)
		fmt.Fprintf(w, "event: %s\ndata: %s\n\n", event, payload)
		flusher.Flush()
	}

	q := r.URL.Query().Get("q")
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit <= 0 {
		limit = 20
	}
	if q == "" {
		sendEvent("error", map[string]string{"message": "q query parameter is required"})
		return
	}

	sendEvent("progress", map[string]string{"step": "keyword_search", "message": "Executing OpenSearch BM25 lexical query..."})
	hits, err := h.OpenSearch.Query(r.Context(), q, limit)
	if err != nil {
		sendEvent("error", map[string]string{"message": err.Error()})
		return
	}

	if h.Citations != nil {
		hits = h.Citations.EnrichHits(r.Context(), hits)
	}

	sendEvent("keyword_hits", map[string]any{"items": hits, "count": len(hits)})
	sendEvent("done", map[string]string{"status": "complete"})
}

// StreamHybrid handles POST /api/v1/search/stream — Server-Sent Events (SSE) streaming of
// multi-signal hybrid search, broadcasting keyword hits, vector matches, graph enrichments, and RRF rankings.
func (h *SearchHandler) StreamHybrid(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"code": "stream_unsupported", "message": "streaming not supported by client connection"})
		return
	}

	var req hybridRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_body", "message": err.Error()})
		return
	}
	if req.Limit <= 0 {
		req.Limit = 20
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(http.StatusOK)

	sendEvent := func(event string, data any) {
		payload, _ := json.Marshal(data)
		fmt.Fprintf(w, "event: %s\ndata: %s\n\n", event, payload)
		flusher.Flush()
	}

	var bm25Hits []search.Hit
	var vectorHits []search.Hit

	// Step 1: OpenSearch BM25 Keyword Query
	if req.Query != "" {
		sendEvent("progress", map[string]string{"step": "keyword_search", "message": "Executing OpenSearch BM25 lexical search..."})
		if hits, err := h.OpenSearch.Query(r.Context(), req.Query, req.Limit); err == nil {
			bm25Hits = hits
			sendEvent("keyword_hits", map[string]any{"items": bm25Hits, "count": len(bm25Hits)})
		}
	}

	// Step 2: Dense Semantic Vector & QMD Concept Search
	if len(req.Embedding) > 0 && h.Vectors != nil {
		sendEvent("progress", map[string]string{"step": "semantic_search", "message": "Executing dense semantic & QMD concept vector search..."})
		source := h.VectorSource
		if source == "" {
			source = search.ProviderLLMWiki
		}
		if hits, err := h.Vectors.SimilaritySearch(r.Context(), req.Embedding, req.Limit); err == nil {
			for i := range hits {
				if hits[i].Source == "" {
					hits[i].Source = source
				}
			}
			vectorHits = hits
			sendEvent("semantic_hits", map[string]any{"items": vectorHits, "count": len(vectorHits)})
		}
	}

	// Step 3: Knowledge Graph & Citation Enrichment
	sendEvent("progress", map[string]string{"step": "graph_enrichment", "message": "Evaluating Neo4j Knowledge Graph topologies and citation network authority..."})
	if h.Citations != nil {
		bm25Hits = h.Citations.EnrichHits(r.Context(), bm25Hits)
		vectorHits = h.Citations.EnrichHits(r.Context(), vectorHits)
	}
	if h.Graph != nil {
		bm25Hits = h.Graph.EnrichHits(r.Context(), req.Query, bm25Hits)
		vectorHits = h.Graph.EnrichHits(r.Context(), req.Query, vectorHits)
	}

	// Step 4: Reciprocal Rank Fusion (RRF)
	sendEvent("progress", map[string]string{"step": "rrf_ranking", "message": "Applying Reciprocal Rank Fusion (RRF) and multi-signal score weighting..."})
	ranker := h.Ranker
	if ranker == nil {
		ranker = search.NewResultRanker(60, 0.35, 0.35, 0.15, 0.15)
	}
	ranked := ranker.RankRRF(req.Limit, bm25Hits, vectorHits)

	sendEvent("ranked_results", map[string]any{"items": ranked, "total": len(ranked), "page": 1, "pageSize": req.Limit})
	sendEvent("done", map[string]string{"status": "complete"})
}
