-- Semantic memory (TDD.md §5/§6.1/§8): chunked resume/experience facts with
-- embeddings, queried by cosine similarity in the Retriever Agent (§6.2).
-- docs/BACKEND_BUILD_STEPS.md Step 22 originally numbered this migration
-- 0006 — 0006 went to the profile_fixes bugfix that landed first (Step 16),
-- so this is 0007 instead; the plan's step numbering didn't anticipate an
-- interleaved bugfix migration.
CREATE EXTENSION IF NOT EXISTS vector;

-- 1536 = OpenAI text-embedding-3-small's native dimension — a placeholder
-- choice, not a commitment: Step 24 (embedding client) is what actually
-- picks the provider/model. Changing it later means a new migration
-- (ALTER COLUMN ... TYPE vector(d) requires re-embedding everything
-- anyway, so there's no cheaper time to get this wrong than now, and no
-- real cost to revisiting it either).
CREATE TABLE profile_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_section TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_profile_chunks_user_id ON profile_chunks(user_id);

-- HNSW over IVFFlat: HNSW needs no training step and gives good recall
-- immediately, which matters at Phase 1's corpus size (TDD.md §13: "low
-- thousands of chunks") — IVFFlat's list-count tuning and "needs data
-- present before building the index well" tradeoffs solve a scale problem
-- this project doesn't have yet. Cosine distance (vector_cosine_ops)
-- because embedding-model similarity is conventionally cosine-based, not
-- L2 or inner-product.
CREATE INDEX idx_profile_chunks_embedding ON profile_chunks
    USING hnsw (embedding vector_cosine_ops);
