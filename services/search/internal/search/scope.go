package search

import "fmt"

// TenantScope is the immutable per-operation visibility scope.
type TenantScope struct {
	OrgID       string
	WorkspaceID string
	System      bool
}

func (s TenantScope) ValidateRead() error {
	if s.System {
		return nil
	}
	if s.OrgID == "" {
		return fmt.Errorf("tenant context required")
	}
	return nil
}

func (s TenantScope) ValidateWrite() error {
	return s.ValidateRead()
}

func (s TenantScope) matches(docTenant TenantScope) bool {
	if s.System {
		return true
	}
	if s.OrgID == "" || docTenant.OrgID == "" || s.OrgID != docTenant.OrgID {
		return s.OrgID != "" && docTenant.OrgID == ""
	}
	return docTenant.WorkspaceID == "" || docTenant.WorkspaceID == s.WorkspaceID
}
