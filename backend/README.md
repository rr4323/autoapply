# AgentOS — Backend

Two runtimes, per `../docs/TDD.md` §2–§3:

- **`api/`** — Go control plane: REST API, auth, Policy Engine, Ingestion Cron, Eval/Drift Cron, Cost Circuit Breaker. See `TDD.md` §3.1, §7, §7.5.
- **`agents/`** — Python agent fleet: Scraper, Retriever, Scoring, Generator, Filler, Verifier, Drift Monitor, Trainer agents, each a separate message-bus consumer. See `TDD.md` §3.2.

Both talk only through the message bus (Redis Streams, `TDD.md` §4) — no agent calls another agent's code directly, and the Go control plane is the only writer allowed to authorize a submit (§7.3).

## Where to start

Follow `../docs/IMPLEMENTATION_PLAN.md` §1 (Backend Implementation Plan) — milestones M0–M10, each with unit and integration tests specified before you write the milestone's code, not after.

## API contract

The REST surface `api/` implements is fully specified in:
- `../docs/API_REFERENCE.md` — human-readable, with rationale
- `api/openapi.yaml` — machine-readable source of truth (import into Postman/Swagger UI, or codegen a client)

If the implementation needs to diverge from either, update both in the same change — they must never drift apart, since the frontend team builds against them without reading the Go source.

## Local dev

Not yet scaffolded (`IMPLEMENTATION_PLAN.md` M0). Target: `docker-compose.yml` at the repo root bringing up Postgres, Redis, the Go API, and the Python agent fleet together — see `TDD.md` §2's architecture diagram for what needs to be running.
