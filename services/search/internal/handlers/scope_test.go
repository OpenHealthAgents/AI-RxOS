package handlers

import (
	"net/http/httptest"
	"strings"
	"testing"
)

func TestStreamQueryMissingTenantFailsBeforeCommittingSuccess(t *testing.T) {
	handler := &SearchHandler{}
	request := httptest.NewRequest("GET", "/api/v1/search/stream?q=private", strings.NewReader(""))
	response := httptest.NewRecorder()

	handler.StreamQuery(response, request)

	if response.Code != 401 {
		t.Fatalf("expected missing tenant scope to return 401, got %d: %s", response.Code, response.Body.String())
	}
}

func TestHybridMissingTenantFailsClosed(t *testing.T) {
	handler := &SearchHandler{}
	request := httptest.NewRequest("POST", "/api/v1/search", strings.NewReader(`{"query":"private"}`))
	response := httptest.NewRecorder()

	handler.Hybrid(response, request)

	if response.Code != 401 {
		t.Fatalf("expected missing tenant scope to return 401, got %d: %s", response.Code, response.Body.String())
	}
}

func TestRequestWriteScopeUsesGatewayVerifiedTenant(t *testing.T) {
	request := httptest.NewRequest("POST", "/api/v1/search/index", nil)
	request.Header.Set("X-Authenticated-Organization-ID", "org-a")
	request.Header.Set("X-Authenticated-Workspace-ID", "workspace-a")

	scope, err := requestWriteScope(request, "")
	if err != nil {
		t.Fatalf("expected trusted gateway scope, got error: %v", err)
	}
	if scope.OrgID != "org-a" || scope.WorkspaceID != "workspace-a" || scope.System {
		t.Fatalf("unexpected tenant scope: %#v", scope)
	}
}

func TestRequestWriteScopeRejectsUnscopedRequest(t *testing.T) {
	request := httptest.NewRequest("POST", "/api/v1/search/index", nil)

	if _, err := requestWriteScope(request, ""); err == nil {
		t.Fatal("expected unscoped request to be rejected")
	}
}

func TestRequestWriteScopeAllowsConfiguredInternalToken(t *testing.T) {
	request := httptest.NewRequest("POST", "/api/v1/search/index", nil)
	request.Header.Set("X-Search-Internal-Token", "internal-secret")

	scope, err := requestWriteScope(request, "internal-secret")
	if err != nil {
		t.Fatalf("expected internal token to grant system scope, got error: %v", err)
	}
	if !scope.System {
		t.Fatalf("expected system scope, got %#v", scope)
	}
}
