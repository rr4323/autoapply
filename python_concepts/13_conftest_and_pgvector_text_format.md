# `conftest.py` Fixture Sharing + pgvector's Text Input Format

## `conftest.py`: pytest fixtures shared across files, no import needed

Step 21 (`test_scraper_agent.py`) and Step 25 (`test_indexer.py`) both need the exact same real-Postgres-testcontainer setup. Copy-pasting it a second time is exactly the mistake Step 16 already made once with `AllMigrationFiles` (two Go test files with the same hand-written migration list, which drifted out of sync) — so this time the fixture moved into `tests/conftest.py` at the second occurrence, not before it (premature extraction after only one user would've been guessing at the right shape).

```python
# tests/conftest.py
@pytest.fixture
async def pg_pool():
    with PostgresContainer("pgvector/pgvector:pg16", ...) as container:
        pool = await asyncpg.create_pool(container.get_connection_url(driver=None))
        async with pool.acquire() as conn:
            for name in MIGRATION_FILES:
                await conn.execute((MIGRATIONS_DIR / name).read_text())
        yield pool
        await pool.close()
```

Any test function in `tests/` can now just declare `async def test_x(pg_pool): ...` — pytest discovers fixtures defined in `conftest.py` automatically, in any test file in the same directory (or below), with **no import statement**. This is different from Python's normal name resolution (everything else needs an explicit `import`) — `conftest.py` is pytest's own special-cased discovery mechanism, not a language feature.

Verified: `test_indexer.py`'s 4 tests and `test_scraper_agent.py`'s 2 tests (after removing its now-duplicate copy of the same fixture) all pass using the shared fixture — [python_concepts/10_asyncpg_and_python_testcontainers.md](10_asyncpg_and_python_testcontainers.md)'s container setup, now written once.

## pgvector's text input format — no extra dependency needed

`profile_chunks.embedding` is `vector(1536)`. `asyncpg` has no built-in codec for that type, and there's a `pgvector` PyPI package with an `asyncpg` codec registration helper — but it pulls in `numpy`, and this project doesn't need array math on embeddings in Python anywhere (similarity search runs inside Postgres via the `<=>` operator, not in application code). Simpler, verified directly against a real pgvector-enabled Postgres before trusting it:

```python
def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"

await conn.execute(
    "INSERT INTO profile_chunks (..., embedding) VALUES (..., $4::vector)",
    ..., _vector_literal(vector),
)
```

pgvector accepts its own text representation (`[0.1,0.2,...]`) as a plain string, cast with `::vector` — the same "cast in SQL, don't fight the driver's type system" move as `asyncpg`'s `$1::uuid`/`$4::jsonb` casts in [10_asyncpg_and_python_testcontainers.md](10_asyncpg_and_python_testcontainers.md). Confirmed with a one-off script against the local dev Postgres before writing `indexer.py`: insert a `[0.1, 0.2, 0.3, 0, 0, ...]` literal, read it back, get the same values.

## Standard use case

`conftest.py`: the moment a second test file needs the same non-trivial fixture — not before. pgvector text literals: any time application code needs to write a vector without doing vector math on it in Python.
