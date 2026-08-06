package search

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"strings"

	opensearch "github.com/opensearch-project/opensearch-go/v2"
	opensearchapi "github.com/opensearch-project/opensearch-go/v2/opensearchapi"
)

type Client struct {
	os       *opensearch.Client
	index    string
	shards   int
	replicas int
}

func NewClient(url, user, password, index string) (*Client, error) {
	osClient, err := opensearch.NewClient(opensearch.Config{
		Addresses: []string{url},
		Username:  user,
		Password:  password,
	})
	if err != nil {
		return nil, err
	}
	return &Client{os: osClient, index: index, shards: 16, replicas: 1}, nil
}

func NewClientWithScaling(url, user, password, index string, shards, replicas int) (*Client, error) {
	client, err := NewClient(url, user, password, index)
	if err != nil {
		return nil, err
	}
	if shards > 0 {
		client.shards = shards
	}
	if replicas >= 0 {
		client.replicas = replicas
	}
	return client, nil
}

func (c *Client) EnsureIndex(ctx context.Context) error {
	exists, err := c.os.Indices.Exists([]string{c.index}, c.os.Indices.Exists.WithContext(ctx))
	if err != nil {
		return err
	}
	if exists.StatusCode == 200 {
		return nil
	}
	mappingJSON := fmt.Sprintf(`{
		"settings": {
			"index": {
				"number_of_shards": "%d",
				"number_of_replicas": "%d",
				"refresh_interval": "30s",
				"knn": true
			}
		},
		"mappings": {
			"properties": {
				"id": {"type": "keyword"},
				"title": {"type": "text", "similarity": "BM25"},
				"content": {"type": "text", "similarity": "BM25"},
				"source": {"type": "keyword"},
				"citations": {"type": "integer"},
				"embedding": {
					"type": "knn_vector",
					"dimension": 768,
					"method": {
						"name": "hnsw",
						"space_type": "cosine",
						"engine": "nmslib",
						"parameters": {
							"ef_construction": 512,
							"m": 16
						}
					}
				}
			}
		}
	}`, c.shards, c.replicas)

	body := bytes.NewBufferString(mappingJSON)
	req := opensearchapi.IndicesCreateRequest{Index: c.index, Body: body}
	res, err := req.Do(ctx, c.os)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	return nil
}

type Document struct {
	ID        string    `json:"id"`
	Title     string    `json:"title"`
	Content   string    `json:"content"`
	Source    string    `json:"source"`
	Citations int       `json:"citations,omitempty"`
	Embedding []float32 `json:"embedding,omitempty"`
}

func (c *Client) IndexDocument(ctx context.Context, doc Document) error {
	body, err := json.Marshal(doc)
	if err != nil {
		return err
	}
	req := opensearchapi.IndexRequest{
		Index:      c.index,
		DocumentID: doc.ID,
		Body:       bytes.NewReader(body),
		Refresh:    "true",
	}
	res, err := req.Do(ctx, c.os)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.IsError() {
		return fmt.Errorf("opensearch index error: %s", res.String())
	}
	return nil
}

// BulkIndexDocuments indexes multiple documents in a single bulk HTTP request,
// designed for scaling throughput up to 100 million document volumes.
func (c *Client) BulkIndexDocuments(ctx context.Context, docs []Document) error {
	if len(docs) == 0 {
		return nil
	}
	var buf strings.Builder
	for _, doc := range docs {
		meta := fmt.Sprintf(`{"index": {"_index": %q, "_id": %q}}`+"\n", c.index, doc.ID)
		buf.WriteString(meta)
		docBytes, err := json.Marshal(doc)
		if err != nil {
			return err
		}
		buf.Write(docBytes)
		buf.WriteString("\n")
	}

	req := opensearchapi.BulkRequest{
		Body: strings.NewReader(buf.String()),
	}
	res, err := req.Do(ctx, c.os)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.IsError() {
		return fmt.Errorf("opensearch bulk error: %s", res.String())
	}
	return nil
}

type Hit struct {
	ID            string  `json:"id"`
	Score         float64 `json:"score"`
	Title         string  `json:"title"`
	Snippet       string  `json:"snippet"`
	Source        string  `json:"source,omitempty"`
	CitationCount int     `json:"citationCount,omitempty"`
	GraphScore    float64 `json:"graphScore,omitempty"`
	RRFScore      float64 `json:"rrfScore,omitempty"`
}

func (c *Client) Query(ctx context.Context, q string, limit int) ([]Hit, error) {
	query := map[string]any{
		"size": limit,
		"query": map[string]any{
			"multi_match": map[string]any{
				"query":  q,
				"fields": []string{"title^2", "content"},
			},
		},
	}
	body, _ := json.Marshal(query)

	req := opensearchapi.SearchRequest{
		Index: []string{c.index},
		Body:  bytes.NewReader(body),
	}
	res, err := req.Do(ctx, c.os)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()

	var parsed struct {
		Hits struct {
			Hits []struct {
				ID     string  `json:"_id"`
				Score  float64 `json:"_score"`
				Source struct {
					Title     string `json:"title"`
					Content   string `json:"content"`
					Source    string `json:"source"`
					Citations int    `json:"citations"`
				} `json:"_source"`
			} `json:"hits"`
		} `json:"hits"`
	}
	if err := json.NewDecoder(res.Body).Decode(&parsed); err != nil {
		return nil, err
	}

	hits := make([]Hit, 0, len(parsed.Hits.Hits))
	for _, h := range parsed.Hits.Hits {
		source := h.Source.Source
		if source == "" {
			source = "opensearch"
		}
		hits = append(hits, Hit{
			ID:            h.ID,
			Score:         h.Score,
			Title:         h.Source.Title,
			Snippet:       h.Source.Content,
			Source:        source,
			CitationCount: h.Source.Citations,
		})
	}
	return hits, nil
}
