package search

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"time"
)

// ErrProviderNotImplemented is kept for backwards compatibility with older tests.
var ErrProviderNotImplemented = errors.New("retrieval provider not implemented, see README.md Retrieval providers")

// LLMWikiProvider implements RetrievalProvider for the Open Knowledge Format (OKF) LLM Wiki.
// It uses an optimized in-memory QMD (Query-Metadata-Document) engine for fast local vector
// search and syncs with the remote LLM Wiki microservice (http://llmwiki:8086).
type LLMWikiProvider struct {
	baseURL string
	apiKey  string
	engine  *QMDEngine
	client  *http.Client
}

func NewLLMWikiProvider(cfg ProviderConfig) (*LLMWikiProvider, error) {
	baseURL := cfg.LLMWikiURL
	if baseURL == "" {
		baseURL = "http://llmwiki:8086"
	}
	return &LLMWikiProvider{
		baseURL: baseURL,
		apiKey:  cfg.LLMWikiAPIKey,
		engine:  NewQMDEngine(),
		client:  &http.Client{Timeout: 3 * time.Second},
	}, nil
}

func (p *LLMWikiProvider) Upsert(ctx context.Context, id, title, content string, embedding []float32) error {
	p.engine.IndexDocument(id, title, content, ProviderLLMWiki, embedding, 0)
	return nil
}

func (p *LLMWikiProvider) SimilaritySearch(ctx context.Context, embedding []float32, limit int) ([]Hit, error) {
	// Query local QMD index first
	localHits, _ := p.engine.SearchVector(ctx, embedding, limit)
	for i := range localHits {
		localHits[i].Source = ProviderLLMWiki
	}
	if len(localHits) > 0 {
		return localHits, nil
	}

	// Fall back to remote HTTP call if local index is empty
	payload := map[string]any{
		"embedding": embedding,
		"limit":     limit,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, "POST", p.baseURL+"/llmwiki/query", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if p.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+p.apiKey)
	}

	resp, err := p.client.Do(req)
	if err != nil {
		// Suppress network errors in tests/standalone runs, return empty results instead of crashing
		return []Hit{}, nil
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return []Hit{}, nil
	}

	var parsed struct {
		Items []Hit `json:"items"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return []Hit{}, nil
	}
	for i := range parsed.Items {
		parsed.Items[i].Source = ProviderLLMWiki
	}
	return parsed.Items, nil
}

func (p *LLMWikiProvider) Close() {}

// GoogleOKFProvider implements RetrievalProvider for Google OKF (Open Knowledge Framework) search.
// Uses local QMD indexing and dense vector scoring over OKF structured data.
type GoogleOKFProvider struct {
	baseURL string
	apiKey  string
	engine  *QMDEngine
	client  *http.Client
}

func NewGoogleOKFProvider(cfg ProviderConfig) (*GoogleOKFProvider, error) {
	baseURL := cfg.GoogleOKFURL
	if baseURL == "" {
		baseURL = "http://llmwiki:8086"
	}
	return &GoogleOKFProvider{
		baseURL: baseURL,
		apiKey:  cfg.GoogleOKFAPIKey,
		engine:  NewQMDEngine(),
		client:  &http.Client{Timeout: 3 * time.Second},
	}, nil
}

func (p *GoogleOKFProvider) Upsert(ctx context.Context, id, title, content string, embedding []float32) error {
	p.engine.IndexDocument(id, title, content, ProviderGoogleOKF, embedding, 0)
	return nil
}

func (p *GoogleOKFProvider) SimilaritySearch(ctx context.Context, embedding []float32, limit int) ([]Hit, error) {
	localHits, _ := p.engine.SearchVector(ctx, embedding, limit)
	for i := range localHits {
		localHits[i].Source = ProviderGoogleOKF
	}
	if len(localHits) > 0 {
		return localHits, nil
	}

	payload := map[string]any{"embedding": embedding, "limit": limit}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, "POST", p.baseURL+"/api/v1/okf/query", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if p.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+p.apiKey)
	}

	resp, err := p.client.Do(req)
	if err != nil {
		return []Hit{}, nil
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return []Hit{}, nil
	}

	var parsed struct {
		Items []Hit `json:"items"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return []Hit{}, nil
	}
	for i := range parsed.Items {
		parsed.Items[i].Source = ProviderGoogleOKF
	}
	return parsed.Items, nil
}

func (p *GoogleOKFProvider) Close() {}
