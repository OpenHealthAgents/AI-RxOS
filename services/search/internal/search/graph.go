package search

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"time"
)

type GraphSearcher struct {
	baseURL      string
	client       *http.Client
	internalToken string
}

func NewGraphSearcher(kgURL string, internalToken ...string) *GraphSearcher {
	if kgURL == "" {
		kgURL = "http://kg:8083"
	}
	var token string
	if len(internalToken) > 0 {
		token = internalToken[0]
	}
	return &GraphSearcher{
		baseURL:      kgURL,
		client:       &http.Client{Timeout: 3 * time.Second},
		internalToken: token,
	}
}

func (g *GraphSearcher) QueryGraphRelevance(
	ctx context.Context, query string, documentIDs []string, authorization string,
) (map[string]float64, error) {
	if len(documentIDs) == 0 || query == "" {
		return map[string]float64{}, nil
	}
	body, err := json.Marshal(map[string]any{"query": query, "document_ids": documentIDs})
	if err != nil {
		return nil, fmt.Errorf("encode graph relevance request: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		g.baseURL+"/api/v1/graph/relevance", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create graph relevance request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if g.internalToken != "" {
		req.Header.Set("X-Search-Internal-Token", g.internalToken)
	}
	if authorization != "" {
		req.Header.Set("Authorization", authorization)
	}
	resp, err := g.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request graph relevance: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("graph relevance returned HTTP %d", resp.StatusCode)
	}
	var parsed struct {
		Relevance map[string]float64 `json:"relevance"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return nil, fmt.Errorf("decode graph relevance response: %w", err)
	}
	if parsed.Relevance == nil {
		return nil, fmt.Errorf("graph relevance response omitted relevance map")
	}
	return parsed.Relevance, nil
}

func (g *GraphSearcher) EnrichHits(
	ctx context.Context, query string, hits []Hit, authorization string,
) ([]Hit, error) {
	if len(hits) == 0 || query == "" {
		return hits, nil
	}
	ids := make([]string, len(hits))
	for i, hit := range hits {
		ids[i] = hit.CanonicalID
		if ids[i] == "" {
			ids[i] = hit.ID
		}
	}
	scores, err := g.QueryGraphRelevance(ctx, query, ids, authorization)
	if err != nil {
		return nil, err
	}
	enriched := make([]Hit, len(hits))
	for i, hit := range hits {
		if score, ok := scores[ids[i]]; ok {
			hit.GraphScore = score
			hit.Score = math.Round((hit.Score+score*0.2)*10000) / 10000
		}
		enriched[i] = hit
	}
	return enriched, nil
}
