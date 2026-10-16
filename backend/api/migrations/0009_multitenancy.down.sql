DROP OWNED BY agentos_worker;
DROP ROLE IF EXISTS agentos_worker;

ALTER TABLE policy_decisions DROP POLICY IF EXISTS tenant_isolation;
ALTER TABLE policy_decisions NO FORCE ROW LEVEL SECURITY;
ALTER TABLE policy_decisions DISABLE ROW LEVEL SECURITY;
ALTER TABLE policy_decisions DROP CONSTRAINT IF EXISTS fk_policy_decisions_tenant;
DROP INDEX IF EXISTS idx_policy_decisions_tenant_id;
ALTER TABLE policy_decisions DROP COLUMN tenant_id;

ALTER TABLE generated_documents DROP POLICY IF EXISTS tenant_isolation;
ALTER TABLE generated_documents NO FORCE ROW LEVEL SECURITY;
ALTER TABLE generated_documents DISABLE ROW LEVEL SECURITY;
ALTER TABLE generated_documents DROP CONSTRAINT IF EXISTS fk_generated_documents_tenant;
DROP INDEX IF EXISTS idx_generated_documents_tenant_id;
ALTER TABLE generated_documents DROP COLUMN tenant_id;

ALTER TABLE application_outcomes DROP POLICY IF EXISTS tenant_isolation;
ALTER TABLE application_outcomes NO FORCE ROW LEVEL SECURITY;
ALTER TABLE application_outcomes DISABLE ROW LEVEL SECURITY;
ALTER TABLE application_outcomes DROP CONSTRAINT IF EXISTS fk_application_outcomes_tenant;
DROP INDEX IF EXISTS idx_application_outcomes_tenant_id;
ALTER TABLE application_outcomes DROP COLUMN tenant_id;

ALTER TABLE application_events DROP POLICY IF EXISTS tenant_isolation;
ALTER TABLE application_events NO FORCE ROW LEVEL SECURITY;
ALTER TABLE application_events DISABLE ROW LEVEL SECURITY;
ALTER TABLE application_events DROP CONSTRAINT IF EXISTS fk_application_events_tenant;
DROP INDEX IF EXISTS idx_application_events_tenant_id;
ALTER TABLE application_events DROP COLUMN tenant_id;

ALTER TABLE search_profiles DROP POLICY IF EXISTS tenant_isolation;
ALTER TABLE search_profiles NO FORCE ROW LEVEL SECURITY;
ALTER TABLE search_profiles DISABLE ROW LEVEL SECURITY;
ALTER TABLE search_profiles DROP CONSTRAINT IF EXISTS fk_search_profiles_tenant;
DROP INDEX IF EXISTS idx_search_profiles_tenant_id;
ALTER TABLE search_profiles DROP COLUMN tenant_id;

ALTER TABLE search_criteria DROP POLICY IF EXISTS tenant_isolation;
ALTER TABLE search_criteria NO FORCE ROW LEVEL SECURITY;
ALTER TABLE search_criteria DISABLE ROW LEVEL SECURITY;
ALTER TABLE search_criteria DROP CONSTRAINT IF EXISTS fk_search_criteria_tenant;
DROP INDEX IF EXISTS idx_search_criteria_tenant_id;
ALTER TABLE search_criteria DROP COLUMN tenant_id;

ALTER TABLE discovered_urls DROP POLICY IF EXISTS tenant_isolation;
ALTER TABLE discovered_urls NO FORCE ROW LEVEL SECURITY;
ALTER TABLE discovered_urls DISABLE ROW LEVEL SECURITY;
ALTER TABLE discovered_urls DROP CONSTRAINT IF EXISTS fk_discovered_urls_tenant;
DROP INDEX IF EXISTS idx_discovered_urls_tenant_id;
ALTER TABLE discovered_urls DROP COLUMN tenant_id;

ALTER TABLE profile_chunks DROP POLICY IF EXISTS tenant_isolation;
ALTER TABLE profile_chunks NO FORCE ROW LEVEL SECURITY;
ALTER TABLE profile_chunks DISABLE ROW LEVEL SECURITY;
ALTER TABLE profile_chunks DROP CONSTRAINT IF EXISTS fk_profile_chunks_tenant;
DROP INDEX IF EXISTS idx_profile_chunks_tenant_id;
ALTER TABLE profile_chunks DROP COLUMN tenant_id;

ALTER TABLE applications DROP POLICY IF EXISTS tenant_isolation;
ALTER TABLE applications NO FORCE ROW LEVEL SECURITY;
ALTER TABLE applications DISABLE ROW LEVEL SECURITY;
ALTER TABLE applications DROP CONSTRAINT IF EXISTS fk_applications_tenant;
DROP INDEX IF EXISTS idx_applications_tenant_id;
ALTER TABLE applications DROP COLUMN tenant_id;

ALTER TABLE profiles DROP POLICY IF EXISTS tenant_isolation;
ALTER TABLE profiles NO FORCE ROW LEVEL SECURITY;
ALTER TABLE profiles DISABLE ROW LEVEL SECURITY;
ALTER TABLE profiles DROP CONSTRAINT IF EXISTS fk_profiles_tenant;
DROP INDEX IF EXISTS idx_profiles_tenant_id;
ALTER TABLE profiles DROP COLUMN tenant_id;

DROP TRIGGER IF EXISTS trg_ensure_user_organization ON users;
DROP FUNCTION IF EXISTS ensure_user_organization();

ALTER TABLE users ALTER COLUMN organization_id DROP NOT NULL;
ALTER TABLE users DROP COLUMN organization_id;

DROP TABLE organizations;
