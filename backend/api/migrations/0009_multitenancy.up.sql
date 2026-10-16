-- P2 (SaaS pivot): implements docs/MULTI_TENANCY_AND_PRICING.md as
-- designed, not redesigned. Tenant = Organization; every user gets an
-- implicit single-person org (§1) so "does this user have a tenant" is
-- never a branch anywhere, including test helpers that only ever called
-- CreateUser(email) — the trigger at the bottom of this file backfills an
-- org for *any* user insert that doesn't supply one, present or future.
--
-- Isolation: shared schema + tenant_id + Postgres RLS (§2), not
-- database/schema-per-tenant — chosen for reasons already argued in that
-- doc, not re-argued here.

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN organization_id UUID REFERENCES organizations(id);

-- Backfill: one org per existing user (there is no ambiguous case per §1 —
-- every user gets exactly one). A plpgsql loop, not a single INSERT..SELECT,
-- because each user needs its OWN new organization row correlated back to
-- it; fine at Phase-1-pivot row counts, not a hot path.
DO $$
DECLARE
    existing_user RECORD;
    new_org_id UUID;
BEGIN
    FOR existing_user IN SELECT id, email FROM users WHERE organization_id IS NULL LOOP
        INSERT INTO organizations (name) VALUES (existing_user.email) RETURNING id INTO new_org_id;
        UPDATE users SET organization_id = new_org_id WHERE id = existing_user.id;
    END LOOP;
END $$;

ALTER TABLE users ALTER COLUMN organization_id SET NOT NULL;

-- Every future user insert (real signups via CreateUserWithPassword, and
-- test/demo helpers like CreateUser(email) that only ever set email) gets
-- an implicit single-person org automatically if it didn't supply one —
-- this is what makes "every user always has exactly one org" true
-- structurally, not just true of the application code paths we remembered
-- to update.
CREATE FUNCTION ensure_user_organization() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.organization_id IS NULL THEN
        INSERT INTO organizations (name) VALUES (NEW.email) RETURNING id INTO NEW.organization_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ensure_user_organization
    BEFORE INSERT ON users
    FOR EACH ROW EXECUTE FUNCTION ensure_user_organization();

-- users/organizations themselves are NOT RLS-protected: login/signup must
-- look up a user by email before any tenant is known (the same
-- chicken-and-egg every auth system has), so that boundary is enforced by
-- application logic (internal/handlers/auth.go), not by RLS. RLS below
-- protects the actual business data everything else in this schema holds.

-- Six tables already carry user_id directly — tenant_id is sourced from
-- users.organization_id via that column, denormalized onto the row itself
-- (not joined at query time) per §2/§3: RLS policies and query planning
-- both want it directly on the row.
ALTER TABLE profiles ADD COLUMN tenant_id UUID;
UPDATE profiles p SET tenant_id = u.organization_id FROM users u WHERE p.user_id = u.id;
ALTER TABLE profiles ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE profiles ADD CONSTRAINT fk_profiles_tenant FOREIGN KEY (tenant_id) REFERENCES organizations(id);
CREATE INDEX idx_profiles_tenant_id ON profiles(tenant_id);
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON profiles
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE applications ADD COLUMN tenant_id UUID;
UPDATE applications a SET tenant_id = u.organization_id FROM users u WHERE a.user_id = u.id;
ALTER TABLE applications ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE applications ADD CONSTRAINT fk_applications_tenant FOREIGN KEY (tenant_id) REFERENCES organizations(id);
CREATE INDEX idx_applications_tenant_id ON applications(tenant_id);
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON applications
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE profile_chunks ADD COLUMN tenant_id UUID;
UPDATE profile_chunks c SET tenant_id = u.organization_id FROM users u WHERE c.user_id = u.id;
ALTER TABLE profile_chunks ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE profile_chunks ADD CONSTRAINT fk_profile_chunks_tenant FOREIGN KEY (tenant_id) REFERENCES organizations(id);
CREATE INDEX idx_profile_chunks_tenant_id ON profile_chunks(tenant_id);
ALTER TABLE profile_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE profile_chunks FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON profile_chunks
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE discovered_urls ADD COLUMN tenant_id UUID;
UPDATE discovered_urls d SET tenant_id = u.organization_id FROM users u WHERE d.user_id = u.id;
ALTER TABLE discovered_urls ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE discovered_urls ADD CONSTRAINT fk_discovered_urls_tenant FOREIGN KEY (tenant_id) REFERENCES organizations(id);
CREATE INDEX idx_discovered_urls_tenant_id ON discovered_urls(tenant_id);
ALTER TABLE discovered_urls ENABLE ROW LEVEL SECURITY;
ALTER TABLE discovered_urls FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON discovered_urls
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE search_criteria ADD COLUMN tenant_id UUID;
UPDATE search_criteria s SET tenant_id = u.organization_id FROM users u WHERE s.user_id = u.id;
ALTER TABLE search_criteria ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE search_criteria ADD CONSTRAINT fk_search_criteria_tenant FOREIGN KEY (tenant_id) REFERENCES organizations(id);
CREATE INDEX idx_search_criteria_tenant_id ON search_criteria(tenant_id);
ALTER TABLE search_criteria ENABLE ROW LEVEL SECURITY;
ALTER TABLE search_criteria FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON search_criteria
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE search_profiles ADD COLUMN tenant_id UUID;
UPDATE search_profiles s SET tenant_id = u.organization_id FROM users u WHERE s.user_id = u.id;
ALTER TABLE search_profiles ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE search_profiles ADD CONSTRAINT fk_search_profiles_tenant FOREIGN KEY (tenant_id) REFERENCES organizations(id);
CREATE INDEX idx_search_profiles_tenant_id ON search_profiles(tenant_id);
ALTER TABLE search_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE search_profiles FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON search_profiles
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Four tables are one hop from applications (no user_id of their own) —
-- tenant_id still gets denormalized directly onto each row (sourced from
-- applications.tenant_id, which the block above already populated), same
-- reasoning, not a join-at-query-time shortcut. Order matters: this runs
-- after applications.tenant_id is backfilled, above.
ALTER TABLE application_events ADD COLUMN tenant_id UUID;
UPDATE application_events e SET tenant_id = a.tenant_id FROM applications a WHERE e.application_id = a.id;
ALTER TABLE application_events ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE application_events ADD CONSTRAINT fk_application_events_tenant FOREIGN KEY (tenant_id) REFERENCES organizations(id);
CREATE INDEX idx_application_events_tenant_id ON application_events(tenant_id);
ALTER TABLE application_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE application_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON application_events
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE application_outcomes ADD COLUMN tenant_id UUID;
UPDATE application_outcomes o SET tenant_id = a.tenant_id FROM applications a WHERE o.application_id = a.id;
ALTER TABLE application_outcomes ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE application_outcomes ADD CONSTRAINT fk_application_outcomes_tenant FOREIGN KEY (tenant_id) REFERENCES organizations(id);
CREATE INDEX idx_application_outcomes_tenant_id ON application_outcomes(tenant_id);
ALTER TABLE application_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE application_outcomes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON application_outcomes
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE generated_documents ADD COLUMN tenant_id UUID;
UPDATE generated_documents g SET tenant_id = a.tenant_id FROM applications a WHERE g.application_id = a.id;
ALTER TABLE generated_documents ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE generated_documents ADD CONSTRAINT fk_generated_documents_tenant FOREIGN KEY (tenant_id) REFERENCES organizations(id);
CREATE INDEX idx_generated_documents_tenant_id ON generated_documents(tenant_id);
ALTER TABLE generated_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE generated_documents FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON generated_documents
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE policy_decisions ADD COLUMN tenant_id UUID;
UPDATE policy_decisions d SET tenant_id = a.tenant_id FROM applications a WHERE d.application_id = a.id;
ALTER TABLE policy_decisions ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE policy_decisions ADD CONSTRAINT fk_policy_decisions_tenant FOREIGN KEY (tenant_id) REFERENCES organizations(id);
CREATE INDEX idx_policy_decisions_tenant_id ON policy_decisions(tenant_id);
ALTER TABLE policy_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_decisions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON policy_decisions
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Deliberately NOT tenant-scoped: platform_selector_maps (ATS DOM
-- selectors are per-ATS-platform procedural memory, useful across every
-- tenant, not per-tenant data — TDD.md's whole point in learning them once)
-- and daily_spend/eval_run/eval_result/drift_check/model_versions (M9/M10,
-- not built yet — the Cost Circuit Breaker becomes per-tenant in P3 when
-- its logic is actually generalized, not here as a bare unused column).

-- Trusted internal-plane role: the Go control plane's own bus consumers
-- (internal/policy, internal/terminal) and its /internal/agent/callback
-- handler, plus the entire Python agent fleet (which connects to Postgres
-- directly for pgvector retrieval/scoring/procedural-memory writes, with
-- no per-request HTTP tenant context to set) are already a trusted
-- boundary — gated by the shared-secret internal auth
-- (internal/middleware/internalauth.go) and network isolation, the same
-- trust level TDD.md's security analysis already assigns them. Rather than
-- thread tenant_id through every message on the bus and every Python
-- agent this pass (a materially larger change, honestly out of scope for
-- this migration), this role bypasses RLS entirely for that already-trusted
-- plane, while the public HTTP API's own role (unchanged) remains fully
-- RLS-enforced. Dev-only password, matching this repo's existing
-- plaintext-dev-secret convention (agentos_dev, dev-internal-secret) —
-- production rotates it via Secret Manager (P4).
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agentos_worker') THEN
        CREATE ROLE agentos_worker LOGIN PASSWORD 'agentos_worker_dev' BYPASSRLS;
    END IF;
END $$;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO agentos_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO agentos_worker;
