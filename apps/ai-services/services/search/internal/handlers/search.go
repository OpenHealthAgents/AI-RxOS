package handlers

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/openhealthagents/ai-rxos/services/search/internal/search"
)

type SearchHandler struct {
	OpenSearch    *search.Client
	Vectors       search.RetrievalProvider
	VectorSource  string
	InternalToken string
	Citations     *search.CitationSearcher
	Graph         *search.GraphSearcher
	Canonical     *search.CanonicalContextClient
	Ranker        *search.ResultRanker
}

type hybridRequest struct {
	Query          string    `json:"query"`
	Mode           string    `json:"mode,omitempty"`
	Embedding      []float32 `json:"embedding,omitempty"`
	Limit          int       `json:"limit,omitempty"`
	Page           int       `json:"page,omitempty"`
	PageSize       int       `json:"page_size,omitempty"`
	EntityTypes    []string  `json:"entity_types,omitempty"`
	Sources        []string  `json:"sources,omitempty"`
	Identifier     string    `json:"identifier,omitempty"`
	AsOf           string    `json:"as_of,omitempty"`
	OrganizationID string    `json:"organization_id,omitempty"`
	WorkspaceID    string    `json:"workspace_id,omitempty"`
}

func (r hybridRequest) tenant() search.TenantScope {
	return search.TenantScope{OrgID: r.OrganizationID, WorkspaceID: r.WorkspaceID}
}

func requireRequestScope(w http.ResponseWriter, r *http.Request) (search.TenantScope, bool) {
	scope, err := requestScope(r)
	if err != nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"code": "tenant_context_required", "message": "authenticated tenant context is required"})
		return search.TenantScope{}, false
	}
	return scope, true
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func parseAsOf(value string) (*time.Time, error) {
	if value == "" {
		return nil, nil
	}
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		return nil, err
	}
	utc := parsed.UTC()
	return &utc, nil
}

func splitFilter(value string) []string {
	if value == "" {
		return nil
	}
	var values []string
	for _, item := range strings.Split(value, ",") {
		if item = strings.TrimSpace(item); item != "" {
			values = append(values, item)
		}
	}
	return values
}

// Query exposes keyword, identifier, filtering, faceting, pagination and temporal search.
func (h *SearchHandler) Query(w http.ResponseWriter, r *http.Request) {
	params := r.URL.Query()
	query := strings.TrimSpace(params.Get("q"))
	identifier := strings.TrimSpace(params.Get("identifier"))
	if query == "" && identifier == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "missing_query", "message": "q or identifier is required"})
		return
	}
	tenant, ok := requireRequestScope(w, r)
	if !ok {
		return
	}
	asOf, err := parseAsOf(params.Get("as_of"))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_as_of", "message": "as_of must be an RFC3339 timestamp"})
		return
	}
	page := parseQueryInt(params.Get("page"), 1)
	pageSize := parseQueryInt(params.Get("page_size"), parseQueryInt(params.Get("limit"), 20))
	result, err := h.OpenSearch.QueryWithOptionsForTenant(r.Context(), search.QueryOptions{
		Query: query, Identifier: identifier, Page: page, PageSize: pageSize,
		EntityTypes: splitFilter(params.Get("entity_type")), Sources: splitFilter(params.Get("source")), AsOf: asOf,
	}, tenant)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"code": "search_failed", "message": err.Error()})
		return
	}
	if h.Graph != nil && query != "" {
		authorization := r.Header.Get("Authorization")
		if authorization == "" && h.InternalToken != "" {
			authorization = "Bearer " + h.InternalToken
		}
		result.Hits, err = h.Graph.EnrichHits(r.Context(), query, result.Hits, authorization)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"code": "graph_enrichment_failed", "message": err.Error()})
			return
		}
	}
	if h.Citations != nil {
		result.Hits = h.Citations.EnrichHits(r.Context(), result.Hits)
	}
	if h.Canonical != nil {
		authorization := r.Header.Get("Authorization")
		if authorization == "" && h.InternalToken != "" {
			authorization = "Bearer " + h.InternalToken
		}
		result.Hits, err = h.Canonical.EnrichHits(r.Context(), result.Hits, authorization, asOf)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"code": "canonical_context_failed", "message": err.Error()})
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": result.Hits, "total": result.Total, "page": page, "page_size": pageSize, "facets": result.Facets,
	})
}

// Hybrid supports keyword, durable OpenSearch vector, and hybrid retrieval.
func (h *SearchHandler) Hybrid(w http.ResponseWriter, r *http.Request) {
	var req hybridRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_body", "message": err.Error()})
		return
	}
	req.Query = strings.TrimSpace(req.Query)
	if req.Page < 1 {
		req.Page = 1
	}
	if req.PageSize < 1 {
		req.PageSize = req.Limit
	}
	if req.PageSize < 1 {
		req.PageSize = 20
	}
	if req.PageSize > 100 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_page_size", "message": "page_size must not exceed 100"})
		return
	}
	mode := strings.ToLower(strings.TrimSpace(req.Mode))
	if mode == "" {
		mode = "hybrid"
	}
	if mode != "hybrid" && mode != "keyword" && mode != "semantic" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_mode", "message": "mode must be keyword, semantic, or hybrid"})
		return
	}
	if (mode == "keyword" && req.Query == "") ||
		(mode == "semantic" && len(req.Embedding) == 0) ||
		(mode == "hybrid" && req.Query == "" && len(req.Embedding) == 0) {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "missing_query", "message": "query or embedding is required for the selected mode"})
		return
	}
	tenant, ok := requireRequestScope(w, r)
	if !ok {
		return
	}
	asOf, err := parseAsOf(req.AsOf)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_as_of", "message": "as_of must be an RFC3339 timestamp"})
		return
	}
	window := req.Page * req.PageSize
	options := search.QueryOptions{
		Query: req.Query, Page: 1, PageSize: window, EntityTypes: req.EntityTypes,
		Sources: req.Sources, Identifier: req.Identifier, AsOf: asOf,
	}
	var keywordHits, semanticHits []search.Hit
	if mode != "semantic" && req.Query != "" {
		result, err := h.OpenSearch.QueryWithOptionsForTenant(r.Context(), options, tenant)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"code": "keyword_search_failed", "message": err.Error()})
			return
		}
		keywordHits = result.Hits
	}
	if mode != "keyword" && len(req.Embedding) > 0 {
		semanticHits, err = h.OpenSearch.SemanticSearchWithOptionsForTenant(r.Context(), req.Embedding, options, tenant)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"code": "semantic_search_failed", "message": err.Error()})
			return
		}
	}
	if h.Citations != nil {
		keywordHits = h.Citations.EnrichHits(r.Context(), keywordHits)
		semanticHits = h.Citations.EnrichHits(r.Context(), semanticHits)
	}
	if h.Graph != nil && req.Query != "" {
		authorization := r.Header.Get("Authorization")
		if authorization == "" && h.InternalToken != "" {
			authorization = "Bearer " + h.InternalToken
		}
		keywordHits, err = h.Graph.EnrichHits(r.Context(), req.Query, keywordHits, authorization)
		if err == nil {
			semanticHits, err = h.Graph.EnrichHits(r.Context(), req.Query, semanticHits, authorization)
		}
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"code": "graph_enrichment_failed", "message": err.Error()})
			return
		}
	}
	ranker := h.Ranker
	if ranker == nil {
		ranker = search.NewResultRanker(60, 0.35, 0.35, 0.15, 0.15)
	}
	ranked := ranker.RankRRF(window, keywordHits, semanticHits)
	if h.Canonical != nil {
		ranked, err = h.Canonical.EnrichHits(r.Context(), ranked, r.Header.Get("Authorization"), asOf)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"code": "canonical_context_failed", "message": err.Error()})
			return
		}
	}
	start := (req.Page - 1) * req.PageSize
	if start > len(ranked) {
		start = len(ranked)
	}
	end := start + req.PageSize
	if end > len(ranked) {
		end = len(ranked)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": ranked[start:end], "total": len(ranked), "page": req.Page, "page_size": req.PageSize,
	})
}

func parseQueryInt(value string, fallback int) int {
	parsed, err := strconv.Atoi(value)
	if err != nil || parsed < 1 {
		return fallback
	}
	return parsed
}
