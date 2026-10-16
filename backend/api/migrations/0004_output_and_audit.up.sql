-- TDD.md §8: generated_documents (RAG output/traceability),
-- platform_selector_maps (procedural memory), policy_decisions (policy
-- audit), daily_spend (cost circuit breaker audit trail, §7.5).

CREATE TYPE generated_document_type AS ENUM ('resume', 'cover_letter', 'screener_answer');

CREATE TABLE generated_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    type generated_document_type NOT NULL,
    storage_ref TEXT NOT NULL,
    source_chunk_ids UUID[] NOT NULL DEFAULT '{}',
    groundedness_score DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_generated_documents_application_id ON generated_documents(application_id);

CREATE TABLE platform_selector_maps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ats_domain TEXT NOT NULL,
    field_map_json JSONB NOT NULL DEFAULT '{}',
    last_success_at TIMESTAMPTZ,
    failure_count INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX idx_platform_selector_maps_ats_domain ON platform_selector_maps(ats_domain);

CREATE TABLE policy_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    decision_point TEXT NOT NULL,
    action TEXT NOT NULL,
    reasons_json JSONB NOT NULL DEFAULT '[]',
    rules_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_policy_decisions_application_id ON policy_decisions(application_id);

CREATE TABLE daily_spend (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    cumulative_generate_spend_usd NUMERIC(12, 4) NOT NULL DEFAULT 0,
    cap_usd NUMERIC(12, 4),
    breached BOOLEAN NOT NULL DEFAULT false,
    breached_at TIMESTAMPTZ,
    reset_by TEXT,
    reset_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX idx_daily_spend_date ON daily_spend(date);
