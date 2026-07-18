package search

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"

	opensearch "github.com/opensearch-project/opensearch-go/v2"
	opensearchapi "github.com/opensearch-project/opensearch-go/v2/opensearchapi"
)

type Client struct {
	os    *opensearch.Client
	index string
}

func NewClient(url, user, password, index string) (*Client, error) {
	os, err := opensearch.NewClient(opensearch.Config{
		Addresses: []string{url},
		Username:  user,
		Password:  password,
	})
	if err != nil {
		return nil, err
	}
	return &Client{os: os, index: index}, nil
}

func (c *Client) EnsureIndex(ctx context.Context) error {
	exists, err := c.os.Indices.Exists([]string{c.index}, c.os.Indices.Exists.WithContext(ctx))
	if err != nil {
		return err
	}
	if exists.StatusCode == 200 {
		return nil
	}
	body := bytes.NewBufferString(`{
		"mappings": {"properties": {
			"title": {"type": "text"},
			"content": {"type": "text"},
			"source": {"type": "keyword"}
		}}
	}`)
	req := opensearchapi.IndicesCreateRequest{Index: c.index, Body: body}
	res, err := req.Do(ctx, c.os)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	return nil
}

type Document struct {
	ID      string `json:"id"`
	Title   string `json:"title"`
	Content string `json:"content"`
	Source  string `json:"source"`
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

type Hit struct {
	ID    string  `json:"id"`
	Score float64 `json:"score"`
	Title string  `json:"title"`
	Snippet string `json:"snippet"`
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
					Title   string `json:"title"`
					Content string `json:"content"`
				} `json:"_source"`
			} `json:"hits"`
		} `json:"hits"`
	}
	if err := json.NewDecoder(res.Body).Decode(&parsed); err != nil {
		return nil, err
	}

	hits := make([]Hit, 0, len(parsed.Hits.Hits))
	for _, h := range parsed.Hits.Hits {
		hits = append(hits, Hit{ID: h.ID, Score: h.Score, Title: h.Source.Title, Snippet: h.Source.Content})
	}
	return hits, nil
}
