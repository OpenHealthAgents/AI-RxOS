package handlers

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"

	"github.com/openhealthagents/ai-rxos/services/search/internal/search"
)

type indexItem struct {
	ID                   string         `json:"id"`
	DocumentID           string         `json:"document_id"`
	CanonicalID          string         `json:"canonical_id"`
	EntityType           string         `json:"entity_type"`
	Title                string         `json:"title"`
	Content              string         `json:"content"`
	Source               string         `json:"source"`
	Aliases              []string       `json:"aliases"`
	Identifiers          []string       `json:"identifiers"`
	TenantID             string         `json:"tenant_id"`
	WorkspaceID          string         `json:"workspace_id"`
	ProjectionVersion    int64          `json:"projection_version"`
	ProjectionKey        string         `json:"projection_key"`
	KnowledgeAvailableAt string         `json:"knowledge_available_at"`
	SourceRecordID       string         `json:"source_record_id"`
	SourceURL            string         `json:"source_url"`
	PublishedAt          string         `json:"published_at"`
	Metadata             map[string]any `json:"metadata"`
	Citations            int            `json:"citations"`
	Embedding            []float32      `json:"embedding"`
	Embeddings           []float32      `json:"embeddings"`
}

type batchIndexPayload struct {
	DocumentID string            `json:"document_id"`
	Title      string            `json:"title"`
	Content    string            `json:"content"`
	Source     string            `json:"source"`
	Citations  int               `json:"citations"`
	Documents  []indexItem       `json:"documents"`
	Items      []indexItem       `json:"items"`
	Tenant     map[string]string `json:"tenant"`
}

func tenantFromMap(tenant map[string]string) search.TenantScope {
	return search.TenantScope{
		OrgID:       tenant["organization_id"],
		WorkspaceID: tenant["workspace_id"],
	}
}

// Index handles POST /api/v1/search/index — indexing document text and vector embeddings
// submitted by upstream services (such as literature or OKF compiler) into OpenSearch and OKF/QMD engines.
func (h *SearchHandler) Index(w http.ResponseWriter, r *http.Request) {
	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_body", "message": "could not read request body"})
		return
	}
	tenant, scopeErr := requestWriteScope(r, h.InternalToken)
	if scopeErr != nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"code": "tenant_context_required", "message": "authenticated tenant context is required"})
		return
	}

	var items []indexItem

	// Try decoding as JSON array first
	if err := json.Unmarshal(bodyBytes, &items); err != nil {
		// Try decoding as a wrapper object or single item
		var wrapper batchIndexPayload
		if err2 := json.Unmarshal(bodyBytes, &wrapper); err2 != nil {
			var single indexItem
			if err3 := json.Unmarshal(bodyBytes, &single); err3 != nil {
				writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_json", "message": "unable to parse document indexing payload"})
				return
			}
			items = []indexItem{single}
		} else {
			if len(wrapper.Documents) > 0 {
				items = wrapper.Documents
			} else if len(wrapper.Items) > 0 {
				items = wrapper.Items
			} else if wrapper.DocumentID != "" || wrapper.Title != "" {
				items = []indexItem{{
					ID:        wrapper.DocumentID,
					Title:     wrapper.Title,
					Content:   wrapper.Content,
					Source:    wrapper.Source,
					Citations: wrapper.Citations,
				}}
			}
		}
	}

	if len(items) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{"status": "skipped", "upserted": 0, "message": "no documents found in payload"})
		return
	}
	if h.OpenSearch == nil && h.Vectors == nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"code": "index_unavailable", "message": "no search index provider is available"})
		return
	}

	upsertCount := 0
	var osDocs []search.Document

	for _, item := range items {
		id := item.ID
		if id == "" {
			id = item.DocumentID
		}
		if id == "" {
			continue // ignore items without an ID
		}
		source := item.Source
		if source == "" {
			source = "literature_service"
		}
		vec := item.Embedding
		if len(vec) == 0 {
			vec = item.Embeddings
		}
		if !tenant.System {
			if item.TenantID != "" && item.TenantID != tenant.OrgID {
				writeJSON(w, http.StatusForbidden, map[string]string{"code": "tenant_scope_violation", "message": "document tenant does not match authenticated tenant"})
				return
			}
			if item.WorkspaceID != "" && item.WorkspaceID != tenant.WorkspaceID {
				writeJSON(w, http.StatusForbidden, map[string]string{"code": "tenant_scope_violation", "message": "document workspace does not match authenticated workspace"})
				return
			}
		}
		documentTenant := item.TenantID
		documentWorkspace := item.WorkspaceID
		if !tenant.System {
			documentTenant = tenant.OrgID
			documentWorkspace = tenant.WorkspaceID
		}

		osDocs = append(osDocs, search.Document{
			ID:                   id,
			DocumentID:           item.DocumentID,
			CanonicalID:          item.CanonicalID,
			EntityType:           item.EntityType,
			Title:                item.Title,
			Content:              item.Content,
			Source:               source,
			Aliases:              item.Aliases,
			Identifiers:          item.Identifiers,
			TenantID:             documentTenant,
			WorkspaceID:          documentWorkspace,
			ProjectionVersion:    item.ProjectionVersion,
			ProjectionKey:        item.ProjectionKey,
			KnowledgeAvailableAt: item.KnowledgeAvailableAt,
			SourceRecordID:       item.SourceRecordID,
			SourceURL:            item.SourceURL,
			PublishedAt:          item.PublishedAt,
			Metadata:             item.Metadata,
			Citations:            item.Citations,
			Embedding:            vec,
		})

		if h.Vectors != nil && len(vec) > 0 {
			if err := h.Vectors.UpsertForTenant(r.Context(), id, item.Title, item.Content, vec, tenant); err != nil {
				slog.Error("search vector upsert failed", "document_id", id, "err", err)
				writeJSON(w, http.StatusBadGateway, map[string]string{"code": "vector_index_failed", "message": "search vector indexing failed"})
				return
			}
		}
		if h.Citations != nil && item.Citations > 0 {
			h.Citations.SetCitationCount(id, item.Citations)
		}
		upsertCount++
	}

	// Index in bulk into OpenSearch when available
	if h.OpenSearch != nil && len(osDocs) > 0 {
		if err := h.OpenSearch.BulkIndexDocumentsForTenant(r.Context(), osDocs, tenant); err != nil {
			slog.Error("OpenSearch bulk indexing failed", "document_count", len(osDocs), "err", err)
			writeJSON(w, http.StatusBadGateway, map[string]string{"code": "opensearch_index_failed", "message": "OpenSearch indexing failed"})
			return
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"status":   "ok",
		"upserted": upsertCount,
		"message":  "Documents successfully indexed into OpenSearch and hybrid OKF/QMD engines",
	})
}

func firstNonEmpty(value, fallback string) string {
	if value != "" {
		return value
	}
	return fallback
}
