package search

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

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
	return NewClientWithCACert(url, user, password, index, "")
}

func NewClientWithCACert(url, user, password, index, caCertPath string) (*Client, error) {
	var transport *http.Transport
	if caCertPath != "" {
		caPEM, err := os.ReadFile(caCertPath)
		if err != nil {
			return nil, fmt.Errorf("read OpenSearch CA certificate: %w", err)
		}
		roots, err := x509.SystemCertPool()
		if err != nil || roots == nil {
			roots = x509.NewCertPool()
		}
		if !roots.AppendCertsFromPEM(caPEM) {
			return nil, fmt.Errorf("OpenSearch CA certificate contains no valid PEM certificates")
		}
		transport = &http.Transport{TLSClientConfig: &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12}}
	}
	if transport == nil {
		transport = http.DefaultTransport.(*http.Transport).Clone()
	}
	osClient, err := opensearch.NewClient(opensearch.Config{
		Addresses: []string{url},
		Username:  user,
		Password:  password,
		Transport: transport,
	})
	if err != nil {
		return nil, err
	}
	return &Client{os: osClient, index: index, shards: 16, replicas: 1}, nil
}

func NewClientWithScaling(url, user, password, index string, shards, replicas int) (*Client, error) {
	return NewClientWithScalingAndCACert(url, user, password, index, shards, replicas, "")
}

func NewClientWithScalingAndCACert(url, user, password, index string, shards, replicas int, caCertPath string) (*Client, error) {
	client, err := NewClientWithCACert(url, user, password, index, caCertPath)
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
		compatible, err := c.indexHasCompatibleKeywordMappings(ctx)
		if err != nil {
			return err
		}
		if compatible {
			return nil
		}
		deleteReq := opensearchapi.IndicesDeleteRequest{Index: []string{c.index}}
		deleteRes, err := deleteReq.Do(ctx, c.os)
		if err != nil {
			return fmt.Errorf("delete legacy index mapping for recreation: %w", err)
		}
		if deleteRes != nil && deleteRes.Body != nil {
			deleteRes.Body.Close()
		}
		if deleteRes != nil && deleteRes.IsError() && deleteRes.StatusCode != http.StatusNotFound {
			return fmt.Errorf("delete legacy index mapping error: %s", deleteRes.String())
		}
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
				"canonical_id": {"type": "keyword"},
				"document_id": {"type": "keyword"},
				"entity_type": {"type": "keyword"},
				"title": {"type": "text", "similarity": "BM25"},
				"content": {"type": "text", "similarity": "BM25"},
				"source": {"type": "keyword"},
				"aliases": {"type": "keyword"},
				"identifiers": {"type": "keyword"},
				"tenant_id": {"type": "keyword"},
				"workspace_id": {"type": "keyword"},
				"projection_version": {"type": "long"},
				"projection_key": {"type": "keyword"},
				"knowledge_available_at": {"type": "date"},
				"superseded_at": {"type": "date"},
				"source_record_id": {"type": "keyword"},
				"source_url": {"type": "keyword"},
				"published_at": {"type": "keyword"},
				"metadata": {"type": "flat_object"},
				"citations": {"type": "integer"},
				"embedding": {
					"type": "knn_vector",
					"dimension": 768,
					"method": {
						"name": "hnsw",
						"space_type": "cosinesimil",
						"engine": "lucene",
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
	if res.IsError() {
		return fmt.Errorf("opensearch index creation error: %s", res.String())
	}
	return nil
}

func (c *Client) indexHasCompatibleKeywordMappings(ctx context.Context) (bool, error) {
	getReq := opensearchapi.IndicesGetMappingRequest{Index: []string{c.index}}
	res, err := getReq.Do(ctx, c.os)
	if err != nil {
		return false, fmt.Errorf("read OpenSearch index mapping: %w", err)
	}
	defer res.Body.Close()
	if res.StatusCode == http.StatusNotFound {
		return false, nil
	}
	if res.IsError() {
		return false, fmt.Errorf("read OpenSearch index mapping error: %s", res.String())
	}

	var payload map[string]any
	if err := json.NewDecoder(res.Body).Decode(&payload); err != nil {
		return false, fmt.Errorf("decode OpenSearch index mapping: %w", err)
	}
	for _, name := range []string{"entity_type", "source", "tenant_id", "workspace_id", "canonical_id", "document_id", "projection_key"} {
		fieldType, ok := getMappingFieldType(payload, c.index, name)
		if !ok {
			continue
		}
		if fieldType == "text" {
			return false, nil
		}
	}
	return true, nil
}

func getMappingFieldType(payload map[string]any, indexName, fieldName string) (string, bool) {
	indexBlock, ok := payload[indexName].(map[string]any)
	if !ok {
		for _, value := range payload {
			if m, ok := value.(map[string]any); ok {
				if t, found := getMappingFieldType(m, indexName, fieldName); found {
					return t, true
				}
			}
		}
		return "", false
	}
	mappings, ok := indexBlock["mappings"].(map[string]any)
	if !ok {
		return "", false
	}
	properties, ok := mappings["properties"].(map[string]any)
	if !ok {
		return "", false
	}
	field, ok := properties[fieldName].(map[string]any)
	if !ok {
		return "", false
	}
	typeName, _ := field["type"].(string)
	return typeName, typeName != ""
}

type Document struct {
	ID                   string         `json:"id"`
	DocumentID           string         `json:"document_id,omitempty"`
	CanonicalID          string         `json:"canonical_id,omitempty"`
	EntityType           string         `json:"entity_type,omitempty"`
	Title                string         `json:"title"`
	Content              string         `json:"content"`
	Source               string         `json:"source"`
	Aliases              []string       `json:"aliases,omitempty"`
	Identifiers          []string       `json:"identifiers,omitempty"`
	TenantID             string         `json:"tenant_id,omitempty"`
	WorkspaceID          string         `json:"workspace_id,omitempty"`
	ProjectionVersion    int64          `json:"projection_version,omitempty"`
	ProjectionKey        string         `json:"projection_key,omitempty"`
	KnowledgeAvailableAt string         `json:"knowledge_available_at,omitempty"`
	SupersededAt         string         `json:"superseded_at,omitempty"`
	SourceRecordID       string         `json:"source_record_id,omitempty"`
	SourceURL            string         `json:"source_url,omitempty"`
	PublishedAt          string         `json:"published_at,omitempty"`
	Metadata             map[string]any `json:"metadata,omitempty"`
	Citations            int            `json:"citations,omitempty"`
	Embedding            []float32      `json:"embedding,omitempty"`
}

func (c *Client) IndexDocument(ctx context.Context, doc Document) error {
	return c.IndexDocumentForTenant(ctx, doc, TenantScope{System: true})
}

func (c *Client) IndexDocumentForTenant(ctx context.Context, doc Document, tenant TenantScope) error {
	if err := tenant.ValidateWrite(); err != nil {
		return err
	}
	if !tenant.System {
		if doc.TenantID == "" {
			doc.TenantID = tenant.OrgID
		} else if doc.TenantID != tenant.OrgID {
			return fmt.Errorf("document tenant does not match authenticated tenant")
		}
		if doc.WorkspaceID == "" {
			doc.WorkspaceID = tenant.WorkspaceID
		} else if doc.WorkspaceID != tenant.WorkspaceID {
			return fmt.Errorf("document workspace does not match authenticated workspace")
		}
	}
	if err := c.prepareVersionedDocument(ctx, &doc, tenant); err != nil {
		return err
	}
	body, err := json.Marshal(doc)
	if err != nil {
		return err
	}
	req := opensearchapi.IndexRequest{
		Index:      c.index,
		DocumentID: indexDocumentID(doc.ID, tenant),
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
	res.Body.Close()
	if err := c.closeOlderProjectionDocuments(ctx, doc, tenant); err != nil {
		return err
	}
	if err := c.reconcileProjectionDocument(ctx, doc, tenant); err != nil {
		return err
	}
	if err := c.deleteLegacyProjectionDocument(ctx, doc, tenant); err != nil {
		return err
	}
	return nil
}

// BulkIndexDocuments indexes multiple documents in a single bulk HTTP request,
// designed for scaling throughput up to 100 million document volumes.
func (c *Client) BulkIndexDocuments(ctx context.Context, docs []Document) error {
	return c.BulkIndexDocumentsForTenant(ctx, docs, TenantScope{System: true})
}

func (c *Client) BulkIndexDocumentsForTenant(ctx context.Context, docs []Document, tenant TenantScope) error {
	if len(docs) == 0 {
		return nil
	}
	if err := tenant.ValidateWrite(); err != nil {
		return err
	}
	if !tenant.System {
		for i := range docs {
			if docs[i].TenantID == "" {
				docs[i].TenantID = tenant.OrgID
			} else if docs[i].TenantID != tenant.OrgID {
				return fmt.Errorf("document tenant does not match authenticated tenant")
			}
			if docs[i].WorkspaceID == "" {
				docs[i].WorkspaceID = tenant.WorkspaceID
			} else if docs[i].WorkspaceID != tenant.WorkspaceID {
				return fmt.Errorf("document workspace does not match authenticated workspace")
			}
		}
	}
	for i := range docs {
		if err := c.prepareVersionedDocument(ctx, &docs[i], tenant); err != nil {
			return err
		}
	}
	var buf strings.Builder
	for _, doc := range docs {
		meta := fmt.Sprintf(`{"index": {"_index": %q, "_id": %q`, c.index, indexDocumentID(doc.ID, tenant))
		meta += "}}\n"
		buf.WriteString(meta)
		docBytes, err := json.Marshal(doc)
		if err != nil {
			return err
		}
		buf.Write(docBytes)
		buf.WriteString("\n")
	}

	req := opensearchapi.BulkRequest{
		Body:    strings.NewReader(buf.String()),
		Refresh: "true",
	}
	res, err := req.Do(ctx, c.os)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.IsError() {
		return fmt.Errorf("opensearch bulk error: %s", res.String())
	}
	var result struct {
		Errors bool `json:"errors"`
		Items  []map[string]struct {
			Status int             `json:"status"`
			Error  json.RawMessage `json:"error"`
		} `json:"items"`
	}
	if err := json.NewDecoder(res.Body).Decode(&result); err != nil {
		return fmt.Errorf("decode opensearch bulk response: %w", err)
	}
	if result.Errors {
		for _, item := range result.Items {
			for operation, details := range item {
				if len(details.Error) > 0 && string(details.Error) != "null" {
					return fmt.Errorf(
						"opensearch bulk response contains one or more failed document operations: %s status %d: %s",
						operation, details.Status, details.Error,
					)
				}
			}
		}
		return fmt.Errorf("opensearch bulk response contains one or more failed document operations")
	}
	for _, doc := range docs {
		if err := c.closeOlderProjectionDocuments(ctx, doc, tenant); err != nil {
			return err
		}
		if err := c.reconcileProjectionDocument(ctx, doc, tenant); err != nil {
			return err
		}
		if err := c.deleteLegacyProjectionDocument(ctx, doc, tenant); err != nil {
			return err
		}
	}
	return nil
}

type Hit struct {
	ID                   string         `json:"id"`
	CanonicalID          string         `json:"canonical_id,omitempty"`
	EntityType           string         `json:"entity_type,omitempty"`
	Score                float64        `json:"score"`
	Title                string         `json:"title"`
	Snippet              string         `json:"snippet"`
	Source               string         `json:"source,omitempty"`
	TenantID             string         `json:"tenant_id,omitempty"`
	WorkspaceID          string         `json:"workspace_id,omitempty"`
	CitationCount        int            `json:"citationCount,omitempty"`
	GraphScore           float64        `json:"graphScore,omitempty"`
	RRFScore             float64        `json:"rrfScore,omitempty"`
	Aliases              []string       `json:"aliases,omitempty"`
	Identifiers          []string       `json:"identifiers,omitempty"`
	SourceRecordID       string         `json:"source_record_id,omitempty"`
	SourceURL            string         `json:"source_url,omitempty"`
	PublishedAt          string         `json:"published_at,omitempty"`
	KnowledgeAvailableAt string         `json:"knowledge_available_at,omitempty"`
	Metadata             map[string]any `json:"metadata,omitempty"`
	Highlights           []string       `json:"highlights,omitempty"`
	EvidenceContext      map[string]any `json:"evidence_context,omitempty"`
	Contradictory        bool           `json:"contradictory,omitempty"`
}

func indexDocumentID(documentID string, tenant TenantScope) string {
	if tenant.System {
		return documentID
	}
	hash := sha256.Sum256([]byte(tenant.OrgID + "\x00" + tenant.WorkspaceID + "\x00" + documentID))
	return fmt.Sprintf("tenant-%x", hash)
}

func appendProjectionTenantFilters(filters []any, tenant TenantScope) []any {
	if tenant.System {
		return filters
	}
	filters = append(filters, map[string]any{"bool": map[string]any{
		"should": []any{
			map[string]any{"term": map[string]any{"tenant_id": tenant.OrgID}},
			map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "tenant_id"}}}}},
		}, "minimum_should_match": 1,
	}})
	if tenant.WorkspaceID != "" {
		return append(filters, map[string]any{"bool": map[string]any{
			"should": []any{
				map[string]any{"term": map[string]any{"workspace_id": tenant.WorkspaceID}},
				map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "workspace_id"}}}}},
			}, "minimum_should_match": 1,
		}})
	}
	return append(filters, map[string]any{"bool": map[string]any{
		"must_not": []any{map[string]any{"exists": map[string]any{"field": "workspace_id"}}},
	}})
}

func (c *Client) prepareVersionedDocument(ctx context.Context, doc *Document, tenant TenantScope) error {
	if doc.ProjectionVersion <= 0 || doc.ProjectionKey == "" || doc.KnowledgeAvailableAt == "" {
		return nil
	}
	filters := []any{
		map[string]any{"term": map[string]any{"projection_key": doc.ProjectionKey}},
		map[string]any{"range": map[string]any{"projection_version": map[string]any{"gt": doc.ProjectionVersion}}},
	}
	filters = appendProjectionTenantFilters(filters, tenant)
	nextBody, err := json.Marshal(map[string]any{
		"size": 1, "sort": []any{map[string]any{"projection_version": "asc"}},
		"query": map[string]any{"bool": map[string]any{"filter": filters}},
	})
	if err != nil {
		return fmt.Errorf("encode projection version lookup: %w", err)
	}
	nextRequest := opensearchapi.SearchRequest{Index: []string{c.index}, Body: bytes.NewReader(nextBody)}
	nextResponse, err := nextRequest.Do(ctx, c.os)
	if err != nil {
		return fmt.Errorf("lookup newer projection version: %w", err)
	}
	var next struct {
		Hits struct {
			Hits []struct {
				Source struct {
					KnowledgeAvailableAt string `json:"knowledge_available_at"`
				} `json:"_source"`
			} `json:"hits"`
		} `json:"hits"`
	}
	if nextResponse.IsError() {
		nextResponse.Body.Close()
		return fmt.Errorf("newer projection lookup error: %s", nextResponse.String())
	}
	err = json.NewDecoder(nextResponse.Body).Decode(&next)
	nextResponse.Body.Close()
	if err != nil {
		return fmt.Errorf("decode newer projection lookup: %w", err)
	}
	if len(next.Hits.Hits) > 0 {
		doc.SupersededAt = next.Hits.Hits[0].Source.KnowledgeAvailableAt
	}

	return nil
}

func (c *Client) closeOlderProjectionDocuments(ctx context.Context, doc Document, tenant TenantScope) error {
	if doc.ProjectionVersion <= 0 || doc.ProjectionKey == "" || doc.KnowledgeAvailableAt == "" {
		return nil
	}
	filters := []any{
		map[string]any{"term": map[string]any{"projection_key": doc.ProjectionKey}},
		map[string]any{"range": map[string]any{"projection_version": map[string]any{"lt": doc.ProjectionVersion}}},
	}
	filters = appendProjectionTenantFilters(filters, tenant)
	updateBody, err := json.Marshal(map[string]any{
		"query": map[string]any{"bool": map[string]any{"filter": filters}},
		"script": map[string]any{
			"lang":   "painless",
			"source": "ctx._source.superseded_at = params.at",
			"params": map[string]any{"at": doc.KnowledgeAvailableAt},
		},
	})
	if err != nil {
		return fmt.Errorf("encode projection history update: %w", err)
	}
	updateRequest := opensearchapi.UpdateByQueryRequest{
		Index: []string{c.index}, Body: bytes.NewReader(updateBody),
		Conflicts: "proceed", Refresh: boolPointer(true),
	}
	updateResponse, err := updateRequest.Do(ctx, c.os)
	if err != nil {
		return fmt.Errorf("close prior projection version: %w", err)
	}
	defer updateResponse.Body.Close()
	if updateResponse.IsError() {
		return fmt.Errorf("close prior projection version error: %s", updateResponse.String())
	}
	return nil
}

func (c *Client) reconcileProjectionDocument(ctx context.Context, doc Document, tenant TenantScope) error {
	if doc.ProjectionVersion <= 0 || doc.ProjectionKey == "" || doc.KnowledgeAvailableAt == "" {
		return nil
	}
	filters := appendProjectionTenantFilters(
		[]any{map[string]any{"term": map[string]any{"projection_key": doc.ProjectionKey}}},
		tenant,
	)
	body, err := json.Marshal(map[string]any{
		"size": 1,
		"sort": []any{map[string]any{"projection_version": "asc"}},
		"query": map[string]any{"bool": map[string]any{
			"filter": filters,
			"must":   []any{map[string]any{"range": map[string]any{"projection_version": map[string]any{"gt": doc.ProjectionVersion}}}},
		}},
	})
	if err != nil {
		return fmt.Errorf("encode next projection lookup: %w", err)
	}
	searchRequest := opensearchapi.SearchRequest{Index: []string{c.index}, Body: bytes.NewReader(body)}
	searchResponse, err := searchRequest.Do(ctx, c.os)
	if err != nil {
		return fmt.Errorf("lookup next projection version: %w", err)
	}
	var next struct {
		Hits struct {
			Hits []struct {
				Source struct {
					KnowledgeAvailableAt string `json:"knowledge_available_at"`
				} `json:"_source"`
			} `json:"hits"`
		} `json:"hits"`
	}
	if searchResponse.IsError() {
		searchResponse.Body.Close()
		return fmt.Errorf("next projection lookup error: %s", searchResponse.String())
	}
	err = json.NewDecoder(searchResponse.Body).Decode(&next)
	searchResponse.Body.Close()
	if err != nil {
		return fmt.Errorf("decode next projection lookup: %w", err)
	}
	var supersededAt any
	if len(next.Hits.Hits) > 0 {
		supersededAt = next.Hits.Hits[0].Source.KnowledgeAvailableAt
	}
	updateBody, err := json.Marshal(map[string]any{
		"query": map[string]any{"ids": map[string]any{"values": []string{indexDocumentID(doc.ID, tenant)}}},
		"script": map[string]any{
			"lang": "painless",
			"source": "if (params.at == null) { ctx._source.remove('superseded_at') } " +
				"else { ctx._source.superseded_at = params.at }",
			"params": map[string]any{"at": supersededAt},
		},
	})
	if err != nil {
		return fmt.Errorf("encode projection availability update: %w", err)
	}
	updateRequest := opensearchapi.UpdateByQueryRequest{
		Index: []string{c.index}, Body: bytes.NewReader(updateBody), Conflicts: "proceed", Refresh: boolPointer(true),
	}
	updateResponse, err := updateRequest.Do(ctx, c.os)
	if err != nil {
		return fmt.Errorf("reconcile projection availability: %w", err)
	}
	defer updateResponse.Body.Close()
	if updateResponse.IsError() {
		return fmt.Errorf("reconcile projection availability error: %s", updateResponse.String())
	}
	return nil
}

func (c *Client) deleteLegacyProjectionDocument(ctx context.Context, doc Document, tenant TenantScope) error {
	if !tenant.System || doc.ProjectionVersion <= 0 || doc.ProjectionKey == "" || doc.ID == doc.ProjectionKey {
		return nil
	}
	req := opensearchapi.DeleteRequest{
		Index: c.index, DocumentID: indexDocumentID(doc.ProjectionKey, tenant), Refresh: "true",
	}
	res, err := req.Do(ctx, c.os)
	if err != nil {
		return fmt.Errorf("remove legacy canonical projection: %w", err)
	}
	defer res.Body.Close()
	if res.StatusCode == http.StatusNotFound {
		return nil
	}
	if res.IsError() {
		return fmt.Errorf("remove legacy canonical projection error: %s", res.String())
	}
	return nil
}

func boolPointer(value bool) *bool {
	return &value
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

func (c *Client) Query(ctx context.Context, q string, limit int) ([]Hit, error) {
	return c.QueryForTenant(ctx, q, limit, TenantScope{})
}

func (c *Client) QueryForTenant(ctx context.Context, q string, limit int, tenant TenantScope) ([]Hit, error) {
	result, err := c.QueryForTenantResult(ctx, q, limit, tenant)
	if err != nil {
		return nil, err
	}
	return result.Hits, nil
}

type SearchResult struct {
	Hits   []Hit                   `json:"items"`
	Total  int                     `json:"total"`
	Facets map[string][]FacetValue `json:"facets,omitempty"`
}

type FacetValue struct {
	Value string `json:"value"`
	Count int    `json:"count"`
}

type QueryOptions struct {
	Query       string
	Page        int
	PageSize    int
	EntityTypes []string
	Sources     []string
	Identifier  string
	AsOf        *time.Time
}

func (c *Client) QueryForTenantResult(ctx context.Context, q string, limit int, tenant TenantScope) (SearchResult, error) {
	return c.QueryWithOptionsForTenant(ctx, QueryOptions{Query: q, Page: 1, PageSize: limit}, tenant)
}

func (c *Client) QueryWithOptionsForTenant(ctx context.Context, options QueryOptions, tenant TenantScope) (SearchResult, error) {
	if err := tenant.ValidateRead(); err != nil {
		return SearchResult{}, err
	}
	if options.Page < 1 {
		options.Page = 1
	}
	if options.PageSize < 1 {
		options.PageSize = 20
	}
	if options.PageSize > 100 {
		return SearchResult{}, fmt.Errorf("page_size must not exceed 100")
	}
	query := map[string]any{
		"from":             (options.Page - 1) * options.PageSize,
		"size":             options.PageSize,
		"track_total_hits": true,
		"sort":             []any{map[string]any{"_score": "desc"}, map[string]any{"_id": "asc"}},
		"aggs": map[string]any{
			"sources":      map[string]any{"terms": map[string]any{"field": "source", "size": 100}},
			"entity_types": map[string]any{"terms": map[string]any{"field": "entity_type", "size": 100}},
		},
		"query": map[string]any{
			"bool": map[string]any{
				"must": []any{map[string]any{"multi_match": map[string]any{
					"query": options.Query, "fields": []string{"title^3", "identifiers^4", "aliases^2", "content"},
				}}},
			},
		},
		"highlight": map[string]any{
			"fields": map[string]any{
				"title":   map[string]any{"number_of_fragments": 0},
				"content": map[string]any{"number_of_fragments": 3, "fragment_size": 180},
			},
		},
	}
	boolQuery := query["query"].(map[string]any)["bool"].(map[string]any)
	filters := make([]any, 0, 5)
	if !tenant.System {
		filters = append(filters, map[string]any{"bool": map[string]any{
			"should": []any{
				map[string]any{"term": map[string]any{"tenant_id": tenant.OrgID}},
				map[string]any{"term": map[string]any{"tenant_id.keyword": tenant.OrgID}},
				map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "tenant_id"}}}}},
			},
			"minimum_should_match": 1,
		}})
		workspaceFilter := map[string]any{"bool": map[string]any{
			"must_not": []any{map[string]any{"exists": map[string]any{"field": "workspace_id"}}},
		}}
		if tenant.WorkspaceID != "" {
			workspaceFilter = map[string]any{"bool": map[string]any{
				"should": []any{
					map[string]any{"term": map[string]any{"workspace_id": tenant.WorkspaceID}},
					map[string]any{"term": map[string]any{"workspace_id.keyword": tenant.WorkspaceID}},
					map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "workspace_id"}}}}},
				},
				"minimum_should_match": 1,
			}}
		}
		filters = append(filters, workspaceFilter)
	}
	if len(options.EntityTypes) > 0 {
		filters = append(filters, map[string]any{"terms": map[string]any{"entity_type": options.EntityTypes}})
	}
	if len(options.Sources) > 0 {
		filters = append(filters, map[string]any{"terms": map[string]any{"source": options.Sources}})
	}
	if options.Identifier != "" {
		boolQuery["must"] = append(boolQuery["must"].([]any), map[string]any{
			"term": map[string]any{"identifiers": options.Identifier},
		})
	}
	if options.Query == "" && options.Identifier != "" {
		boolQuery["must"] = []any{map[string]any{"match_all": map[string]any{}}}
		filters = append(filters, map[string]any{"term": map[string]any{"identifiers": options.Identifier}})
	}
	if options.AsOf != nil {
		filters = append(filters, map[string]any{"bool": map[string]any{
			"should": []any{
				map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "projection_key"}}}}},
				map[string]any{"bool": map[string]any{
					"filter": []any{map[string]any{"range": map[string]any{
						"knowledge_available_at": map[string]any{"lte": options.AsOf.UTC().Format(time.RFC3339Nano)},
					}}},
					"must_not": []any{map[string]any{"range": map[string]any{
						"superseded_at": map[string]any{"lte": options.AsOf.UTC().Format(time.RFC3339Nano)},
					}}},
				}},
			},
			"minimum_should_match": 1,
		}})
	} else {
		filters = append(filters, map[string]any{"bool": map[string]any{
			"should": []any{
				map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "projection_key"}}}}},
				map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "superseded_at"}}}}},
			},
			"minimum_should_match": 1,
		}})
	}
	if len(filters) > 0 {
		boolQuery["filter"] = filters
	}
	body, _ := json.Marshal(query)

	req := opensearchapi.SearchRequest{
		Index: []string{c.index},
		Body:  bytes.NewReader(body),
	}
	res, err := req.Do(ctx, c.os)
	if err != nil {
		return SearchResult{}, err
	}
	defer res.Body.Close()
	if res.IsError() {
		return SearchResult{}, fmt.Errorf("opensearch search error: %s", res.String())
	}

	var parsed struct {
		Hits struct {
			Total struct {
				Value int `json:"value"`
			} `json:"total"`
			Hits []struct {
				ID        string              `json:"_id"`
				Score     float64             `json:"_score"`
				Highlight map[string][]string `json:"highlight"`
				Source    struct {
					ID                   string         `json:"id"`
					DocumentID           string         `json:"document_id"`
					Title                string         `json:"title"`
					Content              string         `json:"content"`
					Source               string         `json:"source"`
					Citations            int            `json:"citations"`
					CanonicalID          string         `json:"canonical_id"`
					EntityType           string         `json:"entity_type"`
					TenantID             string         `json:"tenant_id"`
					WorkspaceID          string         `json:"workspace_id"`
					Aliases              []string       `json:"aliases"`
					Identifiers          []string       `json:"identifiers"`
					SourceRecordID       string         `json:"source_record_id"`
					SourceURL            string         `json:"source_url"`
					PublishedAt          string         `json:"published_at"`
					KnowledgeAvailableAt string         `json:"knowledge_available_at"`
					Metadata             map[string]any `json:"metadata"`
				} `json:"_source"`
			} `json:"hits"`
		} `json:"hits"`
		Aggregations map[string]struct {
			Buckets []struct {
				Key      string `json:"key"`
				DocCount int    `json:"doc_count"`
			} `json:"buckets"`
		} `json:"aggregations"`
	}
	if err := json.NewDecoder(res.Body).Decode(&parsed); err != nil {
		return SearchResult{}, err
	}

	hits := make([]Hit, 0, len(parsed.Hits.Hits))
	for _, h := range parsed.Hits.Hits {
		source := h.Source.Source
		if source == "" {
			source = "opensearch"
		}
		snippets := append([]string(nil), h.Highlight["content"]...)
		if titleFragments := h.Highlight["title"]; len(titleFragments) > 0 {
			snippets = append(titleFragments, snippets...)
		}
		snippet := h.Source.Content
		if len(snippets) > 0 {
			snippet = strings.Join(snippets, " … ")
		}
		hits = append(hits, Hit{
			ID:                   firstNonEmpty(h.Source.DocumentID, h.Source.CanonicalID, h.Source.ID, h.ID),
			CanonicalID:          h.Source.CanonicalID,
			EntityType:           h.Source.EntityType,
			Score:                h.Score,
			Title:                h.Source.Title,
			Snippet:              snippet,
			Source:               source,
			TenantID:             h.Source.TenantID,
			WorkspaceID:          h.Source.WorkspaceID,
			CitationCount:        h.Source.Citations,
			Aliases:              h.Source.Aliases,
			Identifiers:          h.Source.Identifiers,
			SourceRecordID:       h.Source.SourceRecordID,
			SourceURL:            h.Source.SourceURL,
			PublishedAt:          h.Source.PublishedAt,
			KnowledgeAvailableAt: h.Source.KnowledgeAvailableAt,
			Metadata:             h.Source.Metadata,
			Highlights:           snippets,
		})
	}
	facets := map[string][]FacetValue{}
	for facet, aggregation := range parsed.Aggregations {
		for _, bucket := range aggregation.Buckets {
			facets[facet] = append(facets[facet], FacetValue{Value: bucket.Key, Count: bucket.DocCount})
		}
		sort.Slice(facets[facet], func(i, j int) bool {
			if facets[facet][i].Count == facets[facet][j].Count {
				return facets[facet][i].Value < facets[facet][j].Value
			}
			return facets[facet][i].Count > facets[facet][j].Count
		})
	}
	return SearchResult{Hits: hits, Total: parsed.Hits.Total.Value, Facets: facets}, nil
}

func (c *Client) SemanticSearchForTenant(ctx context.Context, embedding []float32, limit int, tenant TenantScope) ([]Hit, error) {
	return c.SemanticSearchWithOptionsForTenant(ctx, embedding, QueryOptions{PageSize: limit}, tenant)
}

func (c *Client) SemanticSearchWithOptionsForTenant(
	ctx context.Context, embedding []float32, options QueryOptions, tenant TenantScope,
) ([]Hit, error) {
	if err := tenant.ValidateRead(); err != nil {
		return nil, err
	}
	if len(embedding) == 0 {
		return nil, fmt.Errorf("semantic search requires an embedding")
	}
	limit := options.PageSize
	if limit < 1 {
		limit = 20
	}
	filter := make([]any, 0, 2)
	if !tenant.System {
		filter = append(filter, map[string]any{"bool": map[string]any{
			"should": []any{
				map[string]any{"term": map[string]any{"tenant_id": tenant.OrgID}},
				map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "tenant_id"}}}}},
			}, "minimum_should_match": 1,
		}})
		if tenant.WorkspaceID != "" {
			filter = append(filter, map[string]any{"bool": map[string]any{
				"should": []any{
					map[string]any{"term": map[string]any{"workspace_id": tenant.WorkspaceID}},
					map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "workspace_id"}}}}},
				}, "minimum_should_match": 1,
			}})
		} else {
			filter = append(filter, map[string]any{"bool": map[string]any{
				"must_not": []any{map[string]any{"exists": map[string]any{"field": "workspace_id"}}},
			}})
		}
	}
	if len(options.EntityTypes) > 0 {
		filter = append(filter, map[string]any{"terms": map[string]any{"entity_type": options.EntityTypes}})
	}
	if len(options.Sources) > 0 {
		filter = append(filter, map[string]any{"terms": map[string]any{"source": options.Sources}})
	}
	if options.Identifier != "" {
		filter = append(filter, map[string]any{"term": map[string]any{"identifiers": options.Identifier}})
	}
	if options.AsOf != nil {
		filter = append(filter, map[string]any{"bool": map[string]any{
			"should": []any{
				map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "projection_key"}}}}},
				map[string]any{"bool": map[string]any{
					"filter": []any{map[string]any{"range": map[string]any{
						"knowledge_available_at": map[string]any{"lte": options.AsOf.UTC().Format(time.RFC3339Nano)},
					}}},
					"must_not": []any{map[string]any{"range": map[string]any{
						"superseded_at": map[string]any{"lte": options.AsOf.UTC().Format(time.RFC3339Nano)},
					}}},
				}},
			}, "minimum_should_match": 1,
		}})
	} else {
		filter = append(filter, map[string]any{"bool": map[string]any{
			"should": []any{
				map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "projection_key"}}}}},
				map[string]any{"bool": map[string]any{"must_not": []any{map[string]any{"exists": map[string]any{"field": "superseded_at"}}}}},
			}, "minimum_should_match": 1,
		}})
	}
	knn := map[string]any{"vector": embedding, "k": limit}
	if len(filter) > 0 {
		knn["filter"] = map[string]any{"bool": map[string]any{"filter": filter}}
	}
	requestBody := map[string]any{
		"size":  limit,
		"query": map[string]any{"knn": map[string]any{"embedding": knn}},
	}
	body, err := json.Marshal(requestBody)
	if err != nil {
		return nil, fmt.Errorf("encode semantic query: %w", err)
	}
	req := opensearchapi.SearchRequest{Index: []string{c.index}, Body: bytes.NewReader(body)}
	res, err := req.Do(ctx, c.os)
	if err != nil {
		return nil, fmt.Errorf("execute semantic search: %w", err)
	}
	if res.IsError() {
		errorBody := res.String()
		res.Body.Close()
		if len(filter) == 0 || !strings.Contains(errorBody, "Engine [NMSLIB] does not support filters") {
			return nil, fmt.Errorf("OpenSearch semantic search error: %s", errorBody)
		}

		candidateCount := limit * 20
		if candidateCount < 1000 {
			candidateCount = 1000
		}
		if candidateCount > 10000 {
			candidateCount = 10000
		}
		delete(knn, "filter")
		knn["k"] = candidateCount
		requestBody["post_filter"] = map[string]any{"bool": map[string]any{"filter": filter}}
		body, err = json.Marshal(requestBody)
		if err != nil {
			return nil, fmt.Errorf("encode legacy semantic query: %w", err)
		}
		req = opensearchapi.SearchRequest{Index: []string{c.index}, Body: bytes.NewReader(body)}
		res, err = req.Do(ctx, c.os)
		if err != nil {
			return nil, fmt.Errorf("execute legacy semantic search: %w", err)
		}
		if res.IsError() {
			defer res.Body.Close()
			return nil, fmt.Errorf("OpenSearch legacy semantic search error: %s", res.String())
		}
	}
	defer res.Body.Close()
	var parsed struct {
		Hits struct {
			Hits []struct {
				ID     string  `json:"_id"`
				Score  float64 `json:"_score"`
				Source struct {
					ID                   string         `json:"id"`
					CanonicalID          string         `json:"canonical_id"`
					EntityType           string         `json:"entity_type"`
					Title                string         `json:"title"`
					Content              string         `json:"content"`
					Source               string         `json:"source"`
					TenantID             string         `json:"tenant_id"`
					WorkspaceID          string         `json:"workspace_id"`
					Citations            int            `json:"citations"`
					Aliases              []string       `json:"aliases"`
					Identifiers          []string       `json:"identifiers"`
					SourceRecordID       string         `json:"source_record_id"`
					SourceURL            string         `json:"source_url"`
					PublishedAt          string         `json:"published_at"`
					KnowledgeAvailableAt string         `json:"knowledge_available_at"`
					Metadata             map[string]any `json:"metadata"`
				} `json:"_source"`
			} `json:"hits"`
		} `json:"hits"`
	}
	if err := json.NewDecoder(res.Body).Decode(&parsed); err != nil {
		return nil, fmt.Errorf("decode semantic search response: %w", err)
	}
	hits := make([]Hit, 0, len(parsed.Hits.Hits))
	for _, item := range parsed.Hits.Hits {
		hits = append(hits, Hit{
			ID: firstNonEmpty(item.Source.ID, item.ID), CanonicalID: item.Source.CanonicalID, EntityType: item.Source.EntityType,
			Score: item.Score, Title: item.Source.Title, Snippet: item.Source.Content,
			Source: item.Source.Source, TenantID: item.Source.TenantID,
			WorkspaceID: item.Source.WorkspaceID, CitationCount: item.Source.Citations,
			Aliases: item.Source.Aliases, Identifiers: item.Source.Identifiers,
			SourceRecordID: item.Source.SourceRecordID, SourceURL: item.Source.SourceURL,
			PublishedAt: item.Source.PublishedAt, KnowledgeAvailableAt: item.Source.KnowledgeAvailableAt,
			Metadata: item.Source.Metadata,
		})
	}
	return hits, nil
}

func parsePage(value string, fallback int) int {
	page, err := strconv.Atoi(value)
	if err != nil || page < 1 {
		return fallback
	}
	return page
}
