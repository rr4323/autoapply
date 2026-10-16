-- TDD.md §8: users(id, email, created_at, ...), profiles(id, user_id, base_resume_doc_id, skills[], experience_json, ...)

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- base_resume_doc_id holds a storage_ref into object storage (TDD.md §14 —
-- raw resume content never lives in Postgres), nullable until a profile
-- has actually uploaded one.
CREATE TABLE profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    base_resume_doc_id TEXT,
    skills TEXT[] NOT NULL DEFAULT '{}',
    experience_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_profiles_user_id ON profiles(user_id);
