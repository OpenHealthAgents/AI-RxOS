package search

import (
	"context"
	"errors"
)

// ErrProviderNotImplemented is returned by placeholder RetrievalProvider
// implementations that have no real backend wired up yet.
var ErrProviderNotImplemented = errors.New("retrieval provider not implemented, see README.md Retrieval providers")

// LLMWikiProvider is a placeholder RetrievalProvider for a future "LLM
// Wiki" retrieval backend. No API contract, SDK, or endpoint for this
// source exists anywhere in this repository or its documentation as of
// this scaffold — do not guess one. Implement SimilaritySearch against
// the real API once it is identified (see README.md "Retrieval providers"
// for exactly what information is still required).
type LLMWikiProvider struct {
	baseURL string
	apiKey  string
}

func NewLLMWikiProvider(cfg ProviderConfig) (*LLMWikiProvider, error) {
	return &LLMWikiProvider{baseURL: cfg.LLMWikiURL, apiKey: cfg.LLMWikiAPIKey}, nil
}

func (p *LLMWikiProvider) SimilaritySearch(ctx context.Context, embedding []float32, limit int) ([]Hit, error) {
	return nil, ErrProviderNotImplemented
}

func (p *LLMWikiProvider) Close() {}

// GoogleOKFProvider is a placeholder RetrievalProvider for a future
// "Google OKF" retrieval backend. No API contract, SDK, or endpoint for
// this source exists anywhere in this repository or its documentation as
// of this scaffold — do not guess one. Implement SimilaritySearch against
// the real API once it is identified (see README.md "Retrieval providers"
// for exactly what information is still required).
type GoogleOKFProvider struct {
	baseURL string
	apiKey  string
}

func NewGoogleOKFProvider(cfg ProviderConfig) (*GoogleOKFProvider, error) {
	return &GoogleOKFProvider{baseURL: cfg.GoogleOKFURL, apiKey: cfg.GoogleOKFAPIKey}, nil
}

func (p *GoogleOKFProvider) SimilaritySearch(ctx context.Context, embedding []float32, limit int) ([]Hit, error) {
	return nil, ErrProviderNotImplemented
}

func (p *GoogleOKFProvider) Close() {}
