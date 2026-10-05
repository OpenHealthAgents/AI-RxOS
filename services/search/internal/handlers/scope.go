package handlers

import (
	"fmt"
	"net/http"

	"github.com/openhealthagents/ai-rxos/services/search/internal/search"
)

func requestScope(r *http.Request) (search.TenantScope, error) {
	org := r.Header.Get("X-Authenticated-Organization-ID")
	if org == "" {
		return search.TenantScope{}, fmt.Errorf("tenant context required")
	}
	return search.TenantScope{
		OrgID:       org,
		WorkspaceID: r.Header.Get("X-Authenticated-Workspace-ID"),
	}, nil
}

func requestWriteScope(r *http.Request, internalToken string) (search.TenantScope, error) {
	if internalToken != "" && r.Header.Get("X-Search-Internal-Token") == internalToken {
		return search.TenantScope{System: true}, nil
	}
	return requestScope(r)
}
