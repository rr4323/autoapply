# `asyncpg` + Python `testcontainers` — the Postgres Side, From Python

## What it is

Every previous Python step talked to Redis; Step 21 (Scraper Agent wiring) is the first time Python code talks to Postgres — specifically, `application_events`, the idempotency ledger from `TDD.md` §4.2. `asyncpg` is the async-native Postgres driver that fits an `asyncio`-based codebase the same way `pgx` fits Go ([go_concepts/22_pgx_transactions_and_sqlc_withtx.md](../go_concepts/22_pgx_transactions_and_sqlc_withtx.md)): a connection pool, parameterized queries, no ORM.

## Verified example (from `backend/agents/src/agentos_agents/common/idempotency.py`)

```python
class ApplicationEventsIdempotency:
    def __init__(self, pool: asyncpg.Pool, event_type: str, agent_name: str) -> None:
        self.pool = pool
        self.event_type = event_type
        self.agent_name = agent_name

    async def already_handled(self, application_id: str) -> bool:
        row = await self.pool.fetchrow(
            "SELECT 1 FROM application_events WHERE application_id = $1::uuid AND event_type = $2",
            application_id,
            self.event_type,
        )
        return row is not None

    async def record(self, application_id: str, payload: dict) -> None:
        await self.pool.execute(
            """
            INSERT INTO application_events
                (application_id, event_type, produced_by_agent, payload_json)
            VALUES ($1::uuid, $2, $3, $4::jsonb)
            """,
            application_id, self.event_type, self.agent_name, json.dumps(payload),
        )
```

Two things worth noticing against the Go side:
- **`$1::uuid`, `$4::jsonb`** — explicit casts on the SQL side, not driver-side type coercion. `asyncpg` accepts a plain Python `str` for these parameters and lets Postgres do the parsing; this sidesteps the exact kind of driver-encoding surprise `pgx` hit with custom enum arrays ([go_concepts/21_pgx_custom_enum_arrays.md](../go_concepts/21_pgx_custom_enum_arrays.md)) — cast in SQL, not fight the driver's type-inference.
- **No ORM, hand-written SQL** — same choice as sqlc on the Go side, for the same reason (discussed with the user directly: raw SQL keeps the query's actual behavior visible and testable against a real database, not hidden behind a query builder).

## Testing it: Python's `testcontainers` package, not just `fakeredis`

Every consumer test so far used `fakeredis` — a protocol fake, sufficient because the thing under test was message-loop mechanics, already proven correct. Step 21's idempotency check is different: it's specifically *whether a raw SQL query against the real ledger table behaves correctly*, so a real Postgres container is the right tool, mirroring the Go side's `testcontainers-go` usage ([go_concepts/15_testcontainers.md](../go_concepts/15_testcontainers.md)) instead of extending the fake-based pattern to something it wasn't meant to prove.

```python
from testcontainers.community.postgres import PostgresContainer

with PostgresContainer(
    "postgres:16-alpine", username="agentos", password="agentos_test", dbname="agentos_test"
) as container:
    dsn = container.get_connection_url(driver=None)  # plain postgresql://... — no +psycopg2
    pool = await asyncpg.create_pool(dsn)
    async with pool.acquire() as conn:
        for name in MIGRATION_FILES:
            await conn.execute((MIGRATIONS_DIR / name).read_text())
```

Verified: both `test_scraper_agent.py` tests pass against a real container on the first run — `TestApplicationsAPI_*`'s Go container fixture and this one apply the exact same six migration files (a hand-copied list, since Go's `store.AllMigrationFiles` isn't importable from Python — same "two lists, must stay in sync" tension as [09_strenum_field_types.md](09_strenum_field_types.md) and `common/topics.py`, just crossing the language boundary this time instead of staying within one test suite).

**`driver=None`** matters: `testcontainers`'s Postgres module defaults to a `psycopg2`-flavored URL (`postgresql+psycopg2://...`) meant for SQLAlchemy; `asyncpg.create_pool()` wants a plain `postgresql://...` DSN, so the driver segment has to be explicitly suppressed.

**No log-scanning wait-strategy workaround needed here** (unlike Go's `.WithOccurrence(2)` fix for Postgres's post-init-script restart) — this Python module's default readiness check runs `psql -c 'select version()'` inside the container via `docker exec`, so it only reports ready once a real connection actually succeeds, sidestepping the log-race entirely.

## Running it

Kept out of the default `make test-py` (a `pytest.ini_options` marker, `integration`, plus `-m "not integration"` in the Makefile) — same split as Go's `-tags=integration`, for the same reason: Docker dependency, slower, not something every `pytest` invocation should pay for. `make test-integration-py` (or the umbrella `make test-integration`) runs it.

## Standard use case

Any Python agent that needs to read or write Postgres directly — the idempotency ledger here, later the Retriever Agent's `profile_chunks` reads (Phase D) and the Trainer/Drift Monitor's `model_registry` work (Phase K) will reach for the same `asyncpg.Pool` + real-container-test pattern.
