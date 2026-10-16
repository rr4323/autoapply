-- TDD.md §3.1.1/§8: search_criteria (one row/user, shared config),
-- search_profiles (many rows/user, per-track facets), discovered_urls.

CREATE TABLE search_criteria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ats_domain_allowlist TEXT[] NOT NULL DEFAULT '{}',
    exclusion_terms TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- One row per user (TDD.md §3.1.1 — shared config, not per-profile).
CREATE UNIQUE INDEX idx_search_criteria_user_id ON search_criteria(user_id);

CREATE TABLE search_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role_titles TEXT[] NOT NULL DEFAULT '{}',
    title_scoped BOOLEAN NOT NULL DEFAULT true,
    skill_keywords TEXT[] NOT NULL DEFAULT '{}',
    locations TEXT[] NOT NULL DEFAULT '{}',
    compiled_query_text TEXT,
    compiled_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_search_profiles_user_id ON search_profiles(user_id);
-- Max 3 active per user (TDD.md §3.1.1) is enforced at the API layer, not here.

CREATE TABLE discovered_urls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    search_profile_id UUID REFERENCES search_profiles(id) ON DELETE SET NULL,
    url TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    application_id UUID REFERENCES applications(id) ON DELETE SET NULL,
    UNIQUE (user_id, url)
);

-- applications.search_profile_id (migration 0002) can now be properly
-- foreign-keyed, since search_profiles didn't exist until this migration.
ALTER TABLE applications
    ADD CONSTRAINT fk_applications_search_profile
    FOREIGN KEY (search_profile_id) REFERENCES search_profiles(id) ON DELETE SET NULL;
