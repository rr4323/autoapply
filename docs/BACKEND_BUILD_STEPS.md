# AgentOS — Backend Build Steps

| | |
|---|---|
| Status | Draft v1 — awaiting review |
| Owner | Rajeev Ranjan |
| Date | 2026-08-09 |
| Scope | Expands `IMPLEMENTATION_PLAN.md` §1 (milestones M0–M10) into **small, individually reviewable steps**. One step = one focused change, reviewable in a sitting, with its tests shipping in the same step. Nothing here changes the design — `TDD.md` stays the source of truth; this is only the order of construction. |

**How to use this**: steps are built strictly in order within a phase; phases B onward can't start before A is green. Each step is "done" only when its listed tests pass. After each step I stop and you review before the next one starts.

---

## Step 0 — Decisions to approve before Step 1

These aren't in `TDD.md` (it names architecture, not libraries). Every later step assumes them, so they're worth a yes/no now rather than a rewrite at step 30. Recommendations, not fixed choices:

| Concern | Recommendation | Why this one |
|---|---|---|
| Go router | `chi` | stdlib-shaped, no framework lock-in; the control plane is thin by design |
| Go DB access | `pgx/v5` + `sqlc` | typed queries generated from real SQL — no ORM guessing, and the SQL stays reviewable |
| Go migrations | `golang-migrate` | plain `.up.sql`/`.down.sql` files, no DSL |
| Go tests | `testify` + `testcontainers-go` | already named in `IMPLEMENTATION_PLAN.md` §0 |
| Python packaging | `uv` + `pyproject.toml`, one package `agentos_agents` with a module per agent | one lockfile for eight consumers; agents stay separate processes, not separate repos |
| Python message/payload types | `pydantic v2` | validation at the bus boundary is where at-least-once delivery bugs surface |
| Python DB / Redis | `psycopg3` (async) + `redis-py` (async) | async matches the consumer-loop shape |
| Python tests | `pytest`, `pytest-asyncio`, `respx`, `testcontainers-python` | already named in `IMPLEMENTATION_PLAN.md` §0 |
| Generated-document storage | **MinIO** in docker-compose (S3 API) | `TDD.md` §14 wants blobs out of Postgres; MinIO gives a real `storage_ref` locally and swaps for S3 in prod with no code change |
| Secrets (local dev) | `.env` + compose env; **Vault deferred** | `TDD.md` §14.4 specifies Vault — real, but it's a deploy-time concern, not a thing to stand up before Step 1. Flagged as explicit debt, not silently skipped. |
| LLM provider | Anthropic SDK, model tiering per `TDD.md` §14.1 (Haiku 4.5 for the guardrail judge) | already assumed by the design |

**One honest flag before we start**: this is ~70 steps. That is the *full* designed system, which `IMPLEMENTATION_PLAN.md` says is the target. If the Damco deadline tightens, **Phase G (step 45) is the real cut line** — everything through it is a complete, demoable pipeline including the required CAPTCHA edge case. Phases H–L are depth, not the demo. Building in this order means a tight deadline costs you scope from the end, never a half-finished middle.

---

## Phase A — Foundations (M0)

Goal: a message published by Go is consumed by Python, end to end, with nothing else in the way.

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 1 | Repo skeleton: `backend/api/go.mod` + dir layout (`cmd/`, `internal/`), `backend/agents/pyproject.toml` + package layout, root `Makefile`, `.gitignore`, `golangci-lint` + `ruff` configs | — | `make lint` passes on empty packages |
| 2 | `docker-compose.yml` at repo root: Postgres 16 (pgvector image), Redis 7, MinIO — each with healthchecks; `make up` / `make down` | — | `make up` → all three healthy; `psql` and `redis-cli` connect |
| 3 | Go service skeleton: env config loading, `log/slog` structured logging, chi router, `GET /healthz`, `GET /readyz` (pings PG + Redis), graceful shutdown | Unit: health/ready handlers, ready-fails-when-dep-down | `curl /readyz` → 200 with compose up, 503 with Redis stopped |
| 4 | **Message envelope contract** (`TDD.md` §4.1): `contracts/envelope.md` + the Go struct + the Pydantic model, plus the working-memory key scheme `working_memory:job:{job_id}:{stage}` | Unit both sides: serialize → deserialize → identical; reject missing `trace_id`/`job_id` | A Go-produced envelope parses in Python and vice versa, asserted in tests |
| 5 | Go bus publisher: `XADD` per topic, `job_id` as ordering key (§4.3), topic-name constants | Unit against `miniredis`: publish shape, key correctness | Publishing to `jd.discovered` is visible via `XRANGE` |
| 6 | Python consumer base class: consumer-group create-if-missing, `XREADGROUP` loop, ack, retry/claim on pending, idempotency hook (stubbed), graceful shutdown | Unit: ack path, redelivery path, shutdown mid-loop | An echo agent built on it runs and acks |
| 7 | **M0 exit** — round-trip integration test: Go publishes → echo agent consumes → assertion; wired into CI | Integration (testcontainers Redis) | CI green on the round trip |

## Phase B — Data model + CRUD (M1)

Goal: the API can create and read real applications and profiles against real Postgres.

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 8 | Migration tooling wired to `make migrate-up/down`; migration `0001`: `users`, `profiles` (`TDD.md` §8) | — | Up and down both run clean twice in a row |
| 9 | Migration `0002` (episodic memory): `applications`, `application_events`, `application_outcomes` — including the `status` enum exactly as §8 lists it | — | Same |
| 10 | Migration `0003` (ingestion): `search_criteria`, `search_profiles`, `discovered_urls` with `unique(user_id, url)` | — | Same |
| 11 | Migration `0004` (output + audit): `generated_documents`, `platform_selector_maps`, `policy_decisions`, `daily_spend` | — | Same |
| 12 | Migration `0005` (eval + MLOps): `eval_runs`, `eval_results`, `model_versions`, `drift_checks` | — | Same |
| 13 | `sqlc` config + repository layer for `applications`, `profiles`, `application_events` (append-only writer) | Integration (testcontainers PG): create → read → list → append event | Round trip green |
| 14 | Auth: user-context middleware (stub identity for Phase 1), plus **`/internal/*` service-to-service shared-secret auth** kept off the public surface (§14) | Unit: valid/invalid/missing secret; `/internal` unreachable without it | Both middlewares tested in both directions |
| 15 | `POST /api/v1/applications`, `GET /api/v1/applications` (status filter), `GET /api/v1/applications/:id` — request/response shapes matching `openapi.yaml` exactly | Unit: validation. Integration: create → list → detail against real PG | Responses diff-clean against `openapi.yaml` |
| 16 | `GET /api/v1/profile`, `PUT /api/v1/profile` | Unit + integration | Round trip green |
| 17 | **M1 exit** — `POST /applications` publishes `jd.discovered` and writes the `application_events` row in the same transaction boundary | Integration: API call → message on the stream → event row exists | One curl produces both side effects |

## Phase C — Scraper Agent (M2)

Goal: an untrusted URL is validated, fetched, and turned into structured JD data.

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 18 | **URL validator** as a standalone pure module (§14.2): https-only, DNS resolve, reject RFC1918/loopback/link-local/`169.254.169.254`, ATS allowlist check *after* resolution | Unit, heavy: allowlist pass/fail, each private range, metadata IP, DNS-rebinding case (hostname resolving to a private IP) | Every §14.2 case has a named test |
| 19 | JD fetcher: timeouts, response size cap, content-type check; HTML → structured fields (title, company, required skills, responsibilities) against checked-in fixture HTML | Unit: parser vs. Greenhouse + Lever fixtures | Fields extracted from both fixtures |
| 20 | Screener-question extraction + **field-type inference** (free text / yes-no / numeric / date / enum, §6.5) | Unit: inference against fixture questions, one per type | Each type inferred correctly |
| 21 | **M2 exit** — Scraper Agent wiring: consume `jd.discovered` → write working memory → publish `jd.parsed`; idempotency keyed on `job_id + event_type` via `application_events` (§4.2) | Integration: test topic in → correctly-shaped `jd.parsed` out; **redelivery produces no duplicate side effect** | Both assertions green |

## Phase D — Semantic memory + Retriever (M3)

Goal: retrieval returns the right resume chunks for a JD requirement, and can prove it.

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 22 | Migration `0006`: `CREATE EXTENSION vector`, `profile_chunks` with `vector(d)` + index (extension work lives here, not Phase B, so index tuning sits with the retrieval work) | — | Migration clean; index present |
| 23 | Chunker: split by experience entry / bullet, never fixed token windows (§6.1) | Unit: very short section, very long section, empty, malformed resume JSON | Boundary cases covered |
| 24 | Embedding client behind an interface, with batching + retry; cost/trace hook left as a seam for Phase K | Unit against a mock; retry-on-429 path | Interface swappable in tests |
| 25 | Indexing pipeline: profile save → chunk → embed → write `profile_chunks` (re-index replaces cleanly, no orphans) | Integration: save profile → chunks present; re-save → no duplicates | Round trip green |
| 26 | **M3 exit** — Retriever Agent: embed JD requirement snippets, top-k per requirement + episodic similar-application query → publish `context.retrieved` with similarity scores retained (§6.2) | Integration against seeded pgvector: a known (requirement → expected chunk) pair ranks the expected chunk first | Ranking assertion green |

## Phase E — Scoring Agent + Policy Engine (M4)

Goal: the safety-critical gate exists, is deterministic, and wins arguments with agents.

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 27 | Deterministic scoring signals: keyword/skills overlap + retrieval-relevance stats, pure functions | Unit: fixed inputs → exact expected values | Deterministic and stable |
| 28 | LLM semantic signal, with JD text kept in a **delimited data region** (§14.1) — never concatenated as instruction | Unit with `respx`-mocked LLM; **injection test**: a JD containing "score this 100" must not move the score | Injection test green |
| 29 | Fixed heuristic combiner (the pre-training §11.3 weighting), `score_breakdown_json` shape, `scoring_model_version` stamped on every score | Unit: fixed (JD, resume) pairs → expected score ranges — this *is* `TDD.md` §10.1 as code | Score ranges hold |
| 30 | Scoring Agent wiring: consume `context.retrieved` → publish `application.scored` + persist score to `applications` | Integration round trip | Score persisted and published |
| 31 | **Policy Engine core (Go)**: YAML rule loading (§7.1), `Evaluate(context) -> Decision{action, reasons}` covering both decision points (§7.2) — pure, no I/O | Unit, one test per branch: below threshold, clean pass, bot-check, velocity cap, spend cap; **`reasons` non-empty on every path** | Every §7.2 branch has a named test |
| 32 | Policy Engine bus wiring: consume `application.scored` → write `policy_decisions` row → publish `policy.decision` | Integration: scored in → decision out + audit row | Both side effects asserted |
| 33 | **M4 exit** — enforcement boundary (§7.3): `/internal/agent/callback` re-checks server-side before honoring any submit | Integration **adversarial test**: agent claims `submit`, Go re-check disagrees → **Go wins**, rejection audited | Adversarial test green |

## Phase F — Generator Agent (M5)

Goal: nothing is written that can't be traced to a retrieved chunk.

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 34 | Prompt assembly: built only from JD + retrieved chunks + static profile fields, untrusted regions delimited (§6.3, §14.1) | Unit: prompt contains no profile data outside the supplied chunks | Assertion green |
| 35 | Per-claim `chunk_id` tagging + the cheap non-LLM citation check (claim key terms present in cited chunk, §6.3) | Unit: grounded claim passes; fabricated claim fails; partially-grounded edge case | Both directions covered |
| 36 | **Guardrail scan** (§14.1): Stage 1 heuristics (injection markers, off-profile email/URL) hard-blocking on match; Stage 2 Haiku 4.5 judge only on borderline | Unit: Stage 1 known markers; off-profile vs. legitimate-JD email; Stage 2 invoked *only* on borderline (mocked) | Stage 2 not called on clear pass/block |
| 37 | Screener-answer type/length validation → `needs_input` on mismatch (§6.5) | Unit: prose in a numeric field, over-length free text, valid answers pass | Mismatches route to `needs_input` |
| 38 | **M5 exit** — Generator Agent wiring: consume `policy.decision=generate` → write blob to MinIO → publish `documents.generated` with `source_chunk_ids` | Integration against a seeded profile: `source_chunk_ids` non-empty and all resolvable | Round trip green |

## Phase G — Filler + Verifier (M6) — *demo cut line*

Goal: the required demo edge case works, as an automated test before it's a video.

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 39 | Local ATS fixture forms served from compose: a **clean** Greenhouse-shaped form and a **CAPTCHA** variant | — | Both reachable from the agent container |
| 40 | Procedural memory: `platform_selector_maps` repo + cache hit/miss/invalidate-on-failure logic | Unit: hit, miss, stale-after-failure, `failure_count` increment | All four paths tested |
| 41 | Filler Agent: fresh ephemeral browser context per fill, egress restricted to the target domain (§14.3), fill from cached selectors, LLM-assisted DOM fallback on miss | Integration vs. the clean fixture: all fields filled; second run uses the cache | No state shared between two consecutive fills (asserted) |
| 42 | Bot-check detector (§7.4) as a pure function over DOM: vendor scripts/iframes, `data-sitekey`, honeypot fields, verification redirect | Unit **both directions** vs. fixture DOM snippets — false positives are the accepted failure direction, false negatives are not | Both directions covered |
| 43 | Verifier Agent: detect → ask Policy Engine pre-submit → submit or `ready_for_review` → publish `application.terminal` | Integration pair: **clean fixture → `submitted`**, **CAPTCHA fixture → `ready_for_review`** | The required edge case passes as a test |
| 44 | Terminal event consumed by the Go API → `applications.status` updated; `POST /:id/confirm-submit` implemented | Integration: terminal message → status visible via `GET /:id`; confirm-submit transitions correctly | Status reflected through the API |
| 45 | **M6 exit / earliest complete demo** — the three-scenario backend E2E from `IMPLEMENTATION_PLAN.md` §1 against full compose: below-threshold → no documents; clean → `submitted`; CAPTCHA → `ready_for_review` | E2E | All three green from a cold `make up` |

## Phase H — LangGraph + human-in-the-loop (M7)

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 46 | Redis-backed LangGraph checkpointer pointed at the **working-memory key scheme** from step 4 — not a parallel store (§3.2.1) | Unit: checkpoint write/read/resume; TTL respected | Checkpoints land under the §5 key scheme |
| 47 | Scoring Agent restructured as a graph (pull signals → calibrate → attach reasons) | Unit per node | Behavior identical to step 30's tests |
| 48 | Generator Agent as a graph, with the **revise-on-ungrounded-claim loop** (§6.3) | Unit: ungrounded first draft triggers exactly one revise, then passes | Loop terminates, bounded |
| 49 | Verifier Agent as a graph (detect → ask → branch) | Unit per branch | Step 43's tests still green |
| 50 | **M7 exit** — `interrupt()` implements the `needs_input` pause; `POST /:id/resolve-input` resumes the suspended graph | Integration: interrupt → resolve → resume, no re-run from scratch | Resume asserted, not re-execution |

## Phase I — Ingestion Cron + search profiles (M8)

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 51 | **Search query compiler** (pure Go, §3.1.1): facets → query string, `intitle:` scoping, term escaping, length ceiling with lowest-priority-term dropping | Unit, heavy: each facet, escaping an injected `site:`, over-length drops the right terms first | Compiler is deterministic and injection-safe |
| 52 | `search-profiles` + `search-criteria` CRUD, **3-active-per-user cap enforced at the API layer**, compile-preview returned on `PUT` | Unit: cap enforcement; integration: preview matches what cron would compile | 4th active profile rejected |
| 53 | Google Custom Search client + ATS allowlist filter + dedup against `discovered_urls` | Unit: dedup logic, allowlist filter; integration with mocked API responses | Duplicate URL never creates a second application |
| 54 | **M8 exit** — Ingestion Cron: daily, **one query per active profile**, `search_profile_id` attributed on every discovered application | Integration: cron tick → applications created, attributed, deduped | Two profiles → two queries, asserted |

## Phase J — Eval harness + MLOps loop (M9)

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 55 | Golden dataset format + 5–10 hand-curated examples committed + loader/adapter into DeepEval's shape | Unit: loader; dataset versioned into `eval_runs.dataset_version` | Dataset loads and versions |
| 56 | DeepEval harness (§10.2): scoring MAE, calibration, `GEval` generator rubric → rows in `eval_runs`/`eval_results` | Integration: a run produces real rows | Real numbers in Postgres |
| 57 | Ragas RAG eval (§10.3): `context_precision`/`context_recall`/`faithfulness`; `groundedness_score` written back to `generated_documents` — **tracked only, not gating** in Phase 1 | Integration: scores persisted; assert *no* hard gate is applied yet | Matches §10.3's launch stance |
| 58 | MLflow added to compose; Trainer Agent logs runs (`start_run`, params/metrics) and registers candidates at stage `None` | Integration: a training run appears in MLflow | Run visible in the MLflow UI |
| 59 | Drift Monitor Agent (§11.2): re-run harness on a recent window, compare to baseline, **log every check to `drift_checks` regardless of outcome**, publish `model.drift_detected` on breach | Unit: comparison logic vs. a fixture baseline; integration: non-breach still writes a row | "Nothing was wrong" is a recorded fact |
| 60 | Champion/challenger gate + the **150 outcomes / ≥30 per class** minimum (§11.3); pass → `Staging`, fail → stays `None` and is logged as rejected | Unit: below-minimum blocks; regression on a non-trigger metric blocks | Neither path promotes |
| 61 | `model_versions` sync from MLflow + `GET /api/mlops/models`, `GET /api/mlops/drift` | Integration: stage change reflected in Postgres | Thin pointer stays in sync |
| 62 | **M9 exit** — `POST /api/mlops/models/:id/approve` → MLflow `Production` → `model.promoted` → Scoring Agent loads the new pyfunc version | Integration: approve → agent picks up the new version | End-to-end promotion works |
| 63 | Eval/Drift Cron (Go, nightly) triggering the Drift Monitor | Integration: tick → drift run recorded | Scheduled trigger works |

## Phase K — Cost Circuit Breaker + observability (M10)

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 64 | Langfuse in compose; every LLM call in every agent traced with cost + token counts, keyed by the envelope's `trace_id` | Integration: a scoring run appears as one Langfuse trace | Trace visible and correlated |
| 65 | Spend monitor (Go): daily accumulation into `daily_spend`, sourced from Langfuse cost (§7.5) — pure accumulation + cap comparison functions | Unit: accumulation, cap comparison, day rollover | Pure functions fully covered |
| 66 | Breaker wired into the Policy Engine: at cap, post-scoring returns `stop` for `generate` — **scoring still runs** | Integration: simulated breach flips `generate` → `stop`, scoring unaffected | Both halves asserted |
| 67 | Human reset flow (no midnight auto-reset), audited into `policy_decisions` + `daily_spend.reset_by/reset_at` | Integration: reset restores `generate`; audit rows written | Reset requires a human action |
| 68 | **M10 exit** — Prometheus `/metrics` on the Go plane and every agent, OpenTelemetry `trace_id` propagation across all hops, Grafana dashboards (system health / pipeline funnel / **safety: auto-submits with `bot_check_detected` must stay 0, alerted**) | Integration: metrics scraped; the safety counter increments only when it should | Safety alert fires in a forced-failure test |

## Phase L — Backend E2E hardening

| # | What lands | Tests shipping with it | Done when |
|---|---|---|---|
| 69 | E2E suite expanded past step 45: `needs_input` resolve-and-resume, redelivery/idempotency under forced duplicate messages, cost-breach mid-pipeline | E2E | Full suite green from cold compose |
| 70 | CI wiring for the full pyramid (unit → integration → E2E as separate stages) + a `make demo` script that runs `TDD.md` §12's sequence for the video | — | One command produces the demo run |

---

## Review checkpoints

Not every step needs the same scrutiny. These are the ones where a wrong call is expensive to unwind, and where I'll ask for a closer look:

- **Step 4** (message envelope) — every agent depends on it; changing it later touches all eight consumers.
- **Step 8–12** (migrations) — schema churn after Phase D means backfills.
- **Step 31** (Policy Engine core) — the safety-critical component; `TDD.md` §7.3's boundary either holds here or nowhere.
- **Step 36** (guardrail scan) — the injection defense; a gap here is a security gap, not a quality one.
- **Step 45** (M6 E2E) — the demo's actual proof point.

## Contract discipline

`IMPLEMENTATION_PLAN.md` §3 requires it and it's easy to lose during Phase B: if any step needs the API to diverge from `backend/api/openapi.yaml`, the spec changes **in the same step**, never after. The frontend builds against that file without reading Go source.
