package handlers

import (
	"net/http/httptest"
	"strings"
	"testing"
)

func TestIndexReturnsFailureWhenNoProviderIsAvailable(t *testing.T) {
	handler := &SearchHandler{}
	request := httptest.NewRequest("POST", "/api/v1/search/index", strings.NewReader(`{"documents":[{"id":"canonical-id","title":"Demo asset"}]}`))
	request.Header.Set("X-Authenticated-Organization-ID", "org-a")
	response := httptest.NewRecorder()

	handler.Index(response, request)

	if response.Code != 502 {
		t.Fatalf("expected 502 when index providers are unavailable, got %d: %s", response.Code, response.Body.String())
	}
}
