package handlers

import (
	"encoding/json"
	"io"
	"net/http"

	"github.com/openhealthagents/ai-rxos/services/search/internal/search"
)

type indexItem struct {
	ID        string    `json:"id"`
	DocumentID string   `json:"document_id"`
	Title     string    `json:"title"`
	Content   string    `json:"content"`
	Source    string    `json:"source"`
	Citations int       `json:"citations"`
	Embedding []float32 `json:"embedding"`
	Embeddings []float32 `json:"embeddings"`
}

type batchIndexPayload struct {
	DocumentID string      `json:"document_id"`
	Title      string      `json:"title"`
	Content    string      `json:"content"`
	Source     string      `json:"source"`
	Citations  int         `json:"citations"`
	Documents  []indexItem `json:"documents"`
	Items      []indexItem `json:"items"`
}

// Index handles POST /api/v1/search/index — indexing document text and vector embeddings
// submitted by upstream services (such as literature or OKF compiler) into OpenSearch and OKF/QMD engines.
func (h *SearchHandler) Index(w http.ResponseWriter, r *http.Request) {
	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_body", "message": "could not read request body"})
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

		osDocs = append(osDocs, search.Document{
			ID:        id,
			Title:     item.Title,
			Content:   item.Content,
			Source:    source,
			Citations: item.Citations,
			Embedding: vec,
		})

		if h.Vectors != nil {
			_ = h.Vectors.Upsert(r.Context(), id, item.Title, item.Content, vec)
		}
		if h.Citations != nil && item.Citations > 0 {
			h.Citations.SetCitationCount(id, item.Citations)
		}
		upsertCount++
	}

	// Index in bulk into OpenSearch when available
	if h.OpenSearch != nil && len(osDocs) > 0 {
		_ = h.OpenSearch.BulkIndexDocuments(r.Context(), osDocs)
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"status":   "ok",
		"upserted": upsertCount,
		"message":  "Documents successfully indexed into OpenSearch and hybrid OKF/QMD engines",
	})
}
