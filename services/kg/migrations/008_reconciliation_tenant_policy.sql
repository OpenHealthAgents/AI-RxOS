ALTER TABLE canonical.reconciliation_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical.reconciliation_results FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS reconciliation_results_scope ON canonical.reconciliation_results;
CREATE POLICY reconciliation_results_scope ON canonical.reconciliation_results
    FOR ALL
    USING (tenant_id IS NULL OR tenant_id = canonical.current_organization_id())
    WITH CHECK (tenant_id IS NULL OR tenant_id = canonical.current_organization_id());
