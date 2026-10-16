# Testing pgvector Ranking Without a Real Embedding Model

## The problem

`top_k_chunks_for_requirement` (Step 26) ranks `profile_chunks` by cosine distance to a query vector:

```sql
SELECT id, source_section, text, 1 - (embedding <=> $2::vector) AS similarity
FROM profile_chunks
WHERE user_id = $1::uuid
ORDER BY embedding <=> $2::vector
LIMIT $3
```

The Step 25 tests used an all-zero `FakeEmbeddingClient` — fine for proving delete/insert/replace behavior, but useless here: every vector would be identical, so "ranks the expected chunk first" would pass by coincidence (or fail unpredictably on tie-breaking), not by actually exercising the `ORDER BY embedding <=> ...` logic. There's no network access in this environment to call a real embedding API either.

## The fix: a deterministic bag-of-words fake, not an all-zero one

```python
VOCAB = ["go", "backend", "distributed", "marketing", "campaigns"]

class FakeKeywordEmbeddingClient(EmbeddingClient):
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            words = set(text.lower().replace(",", " ").replace(".", " ").split())
            vec = [1.0 if term in words else 0.0 for term in VOCAB]
            vec += [0.0] * (1536 - len(VOCAB))
            vectors.append(vec)
        return vectors
```

A requirement ("Go backend experience") and a chunk sharing real words ("Built backend services in Go...") get genuinely nonorthogonal vectors; a chunk about something else ("Led marketing campaigns...") gets a vector with zero dot-product against the requirement — cosine similarity exactly `0`. This is what makes `test_retriever_agent_ranks_expected_chunk_first`'s assertion meaningful:

```python
assert chunks[0]["text"] == RELEVANT_BULLET
assert chunks[1]["text"] == IRRELEVANT_BULLET
assert chunks[0]["similarity"] > chunks[1]["similarity"]
assert chunks[1]["similarity"] == 0  # orthogonal bag-of-words vectors
```

Verified: run against a real `pgvector`-enabled Postgres (`conftest.py`'s `pg_pool` fixture) — the SQL's `<=>` operator, the index, and the Python-side ordering are all real; only the embedding *model* is fake.

## What this test does and doesn't prove

**Proves**: the retrieval SQL correctly ranks by vector similarity, `1 - distance` is computed correctly, results come back in the right order, and the whole pipeline (index a profile → embed a requirement → query → return ranked chunks) wires together end to end.

**Doesn't prove**: that a *real* embedding model (Step 24's actual `OpenAIEmbeddingClient` against a real API) produces semantically sensible vectors — that's a model-quality question (`TDD.md` §10's Ragas `context_precision`/`context_recall` evaluation, not yet built) genuinely out of reach without network access, and out of scope for what Step 26 needs to prove.

## Standard use case

Any test of ranking/ordering/similarity logic sitting on top of a black-box scoring function (embeddings, ML model outputs, external ranking APIs) — replace the black box with a small deterministic function that's *predictably* related to the input, so the ranking assertion tests the ranking code, not the black box's quality.
