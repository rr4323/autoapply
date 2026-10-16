-- TDD.md §8: applications, application_events (idempotency ledger, §4.2),
-- application_outcomes.

CREATE TYPE application_source AS ENUM ('manual', 'discovered');
CREATE TYPE application_status AS ENUM (
    'pending', 'scored', 'below_threshold', 'filling',
    'ready_for_review', 'needs_input', 'submitted', 'failed'
);

CREATE TABLE applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jd_url TEXT,
    jd_text TEXT,
    company TEXT,
    role_title TEXT,
    source application_source NOT NULL,
    search_profile_id UUID,  -- FK added in migration 0003 once search_profiles exists
    jd_fit_score DOUBLE PRECISION,
    resume_match_score DOUBLE PRECISION,
    score_breakdown_json JSONB,
    scoring_model_version TEXT,
    status application_status NOT NULL DEFAULT 'pending',
    bot_check_detected BOOLEAN NOT NULL DEFAULT false,
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_applications_user_id ON applications(user_id);
CREATE INDEX idx_applications_status ON applications(status);

-- Append-only (TDD.md §8: "the scoring dataset survives even if later logic
-- changes how status is derived"). No UNIQUE constraint on
-- (application_id, event_type) — a legitimate re-score/re-fill can produce
-- a second event of the same type; redelivery dedup is application-layer
-- logic (the Python Consumer's is_duplicate hook, wired to real storage in
-- a later step), not a DB constraint.
CREATE TABLE application_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    produced_by_agent TEXT NOT NULL,
    payload_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_application_events_app_event_type ON application_events(application_id, event_type);

CREATE TYPE outcome_type AS ENUM ('interview', 'rejected', 'no_response');

CREATE TABLE application_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    outcome outcome_type NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_application_outcomes_application_id ON application_outcomes(application_id);
