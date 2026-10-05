package search

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type CanonicalContextClient struct {
	baseURL      string
	client       *http.Client
	internalToken string
}

func NewCanonicalContextClient(baseURL string, internalToken ...string) *CanonicalContextClient {
	if baseURL == "" {
		baseURL = "http://kg:8083"
	}
	var token string
	if len(internalToken) > 0 {
		token = internalToken[0]
	}
	return &CanonicalContextClient{
		baseURL:       baseURL,
		client:        &http.Client{Timeout: 5 * time.Second},
		internalToken: token,
	}
}

func (c *CanonicalContextClient) EnrichHits(
	ctx context.Context, hits []Hit, authorization string, asOf *time.Time,
) ([]Hit, error) {
	ids := make([]string, 0, len(hits))
	seen := make(map[string]bool, len(hits))
	for _, hit := range hits {
		if hit.CanonicalID != "" && !seen[hit.CanonicalID] {
			ids = append(ids, hit.CanonicalID)
			seen[hit.CanonicalID] = true
		}
	}
	if len(ids) == 0 {
		return hits, nil
	}
	payload := map[string]any{"entity_ids": ids}
	if asOf != nil {
		payload["as_of"] = asOf.UTC().Format(time.RFC3339Nano)
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("encode canonical search context request: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.baseURL+"/api/v1/canonical/search-context", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create canonical search context request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if c.internalToken != "" {
		req.Header.Set("X-Search-Internal-Token", c.internalToken)
	}
	if authorization != "" {
		req.Header.Set("Authorization", authorization)
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request canonical search context: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("canonical search context returned HTTP %d", resp.StatusCode)
	}
	var parsed struct {
		Items map[string]map[string]any `json:"items"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return nil, fmt.Errorf("decode canonical search context: %w", err)
	}
	for i := range hits {
		if context, ok := parsed.Items[hits[i].CanonicalID]; ok {
			hits[i].EvidenceContext = context
			hits[i].Contradictory, _ = context["contradictory"].(bool)
		}
	}
	return hits, nil
}
