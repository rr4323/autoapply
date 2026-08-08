# AgentOS — Implementation Plan
### Backend and frontend, each sequenced unit → integration → e2e

| | |
|---|---|
| Status | Draft v2 — full-system scope |
| Owner | Rajeev Ranjan |
| Date | 2026-08-08 |
| Scope | Turns `TDD.md` into a buildable sequence. **Rajeev is building the full designed system** — the earlier scoped-down "minimal demo slice" framing is superseded; the complete system *is* the Damco submission's demo. Milestones marked **[EARLIEST DEMOABLE]** mark the earliest point something real can be shown on camera if the timeline gets tight — a fallback checkpoint, not the target. All milestones (M0–M10, F0–F5) are in scope and should be built. Directory layout: `../backend/` (Go control plane in `api/`, Python agent fleet in `agents/`) and `../frontend/` (React) — see each directory's `README.md`. API contract for frontend/backend to build against in parallel: `../docs/API_REFERENCE.md` + `../backend/api/openapi.yaml`. |

---

## 0. Testing Philosophy (applies to both tracks)

Tests are written **alongside** each milestone, not after it — a milestone isn't "done" until its unit tests pass, and integration tests for a milestone are written as soon as the *next* milestone gives it something real to integrate with. E2E tests come last on purpose: they're the most expensive and slowest signal, so they should only need to catch what unit/integration tests structurally can't (real cross-service timing, real browser behavior, real UI flows) — not re-verify logic already covered cheaper elsewhere.

| Layer | What it catches | What it doesn't need |
|---|---|---|
| Unit | Logic correctness in isolation — a scoring formula, a rule evaluation, a component's render given props | Real DB, real Redis, real LLM, real browser |
| Integration | Two real things actually agreeing on a contract — Go API against real Postgres, an agent against a real (test) Redis Streams topic, React against a mocked-but-contract-accurate API | The full stack running together |
| E2E | The full stack, end to end, for the handful of journeys that matter — TDD §12's sequence, PRD's key flows | Exhaustive coverage — e2e is for golden paths + the required edge cases, not every branch |

**Tooling** (Go, Python, TypeScript each get idiomatic choices, not a forced-common framework):

| Track | Unit | Integration | E2E |
|---|---|---|---|
| Go (control plane) | stdlib `testing` + `testify` | `testcontainers-go` (real Postgres/Redis in CI) | — |
| Python (agent fleet) | `pytest` + `pytest-asyncio` | `testcontainers-python`, HTTP mocking (`respx`) for LLM calls | — |
| React (frontend) | Vitest/Jest + React Testing Library | MSW (Mock Service Worker) against the real API contract | — |
| Full-stack | — | — | **Playwright** — already a core dependency for the Filler Agent (TDD §3.2), reused here for browser-driven frontend e2e rather than adopting a second browser-automation tool |

---

## 1. Backend Implementation Plan

Milestones deliver vertical slices (one working piece of the pipeline), not horizontal layers (not "all models, then all handlers") — each milestone should be independently demoable via a script or a couple of curl/CLI calls before the next one starts.

| # | Milestone | Unit tests | Integration tests |
|---|---|---|---|
| M0 **[EARLIEST DEMOABLE]** | Infra scaffolding: Postgres, Redis, Docker Compose for local dev; Go service skeleton; Python worker skeleton; Redis Streams client wiring on both sides | — (infra) | Basic pub/sub round-trip: publish to a test topic, assert a consumer receives it |
| M1 **[EARLIEST DEMOABLE]** | Data model migrations (TDD §8 — full schema, multi-tenancy tables from `MULTI_TENANCY_AND_PRICING.md` deferred until that phase actually starts); Go API CRUD for `applications`/`profiles` (§9) | Handler unit tests against a mocked DB; request/response validation | API + real Postgres (testcontainers): create → read → list round trip |
| M2 **[EARLIEST DEMOABLE]** | Scraper Agent: JD fetch/parse, SSRF validation (§14.2 — scheme/DNS/private-IP checks) | URL validator: allowlist pass/fail cases, private-IP/metadata-IP rejection cases (these are pure functions — cheap, high-value tests); JD parser against fixture HTML | Scraper Agent consuming from a test `jd.discovered` topic, publishing correctly-shaped `jd.parsed` |
| M3 **[EARLIEST DEMOABLE]** | Semantic memory: pgvector setup, chunking + embedding pipeline (§6.1), Retriever Agent (§6.2) | Chunking logic (boundary cases: very short/long resume sections); embedding client behind a mock | Real pgvector query against seeded test chunks — assert retrieval ranking is sane for a known (JD requirement → expected chunk) pair |
| M4 **[EARLIEST DEMOABLE]** | Scoring Agent (§7's deterministic + semantic signal) + Go Policy Engine (§7.1–§7.4) | Policy Engine rule evaluation — every branch as a separate test (below threshold, bot-check present, velocity cap hit, spend cap hit, clean pass); Scoring Agent against fixed (JD, resume) pairs with expected score ranges (this *is* TDD §10.1's spec, now as actual test code) | Scoring Agent → `policy.decision` round trip over Redis; **adversarial test**: a worker claims `submit` but the Go-side re-check disagrees — assert Go wins (TDD §7.3's enforcement boundary, made concrete as a test) |
| M5 **[EARLIEST DEMOABLE]** | Generator Agent: grounded generation (§6.3), citation check, guardrail scan (§14.1), screener field validation (§6.5) | Citation-check logic (claim text vs. cited chunk); guardrail heuristic pattern matches (known injection markers, off-profile email/URL detection); field-type inference against fixture screener questions | Generator Agent consuming `policy.decision=generate`, producing `documents.generated` with correct `source_chunk_ids` against a seeded test profile |
| M6 **[EARLIEST DEMOABLE]** | Filler Agent (Playwright): form fill, procedural-memory selector cache, ephemeral context isolation (§14.3); Verifier Agent: bot-check detection (§7.4) | Bot-check heuristic against fixture DOM snippets (with/without CAPTCHA markers — both directions tested, since a false positive is the accepted failure direction per §7.4); selector-cache hit/miss logic | **Filler Agent against a local fixture Greenhouse form** (already specified in TDD §10.1) — full fill → detect → decide round trip, run twice: once against a clean fixture (expect `submit`), once against a CAPTCHA-fixture (expect `ready_for_review`) — this pair *is* the required demo edge case, built as an automated test first |
| M7 | LangGraph integration: Redis-backed checkpointer, `interrupt()` for `needs_input` | Graph node unit tests | Interrupt → `POST /resolve-input` → resume round trip |
| M8 | Ingestion Cron + Search API dedup (PRD §5.0) | Dedup logic; ATS domain allowlist filter | Cron trigger → discovered application created (mocked Search API response) |
| M9 | Eval harness (DeepEval/Ragas) + Drift Monitor + Trainer Agent + MLflow (§10, §11) | Metric-calculation wrapper tests | Eval harness run against a small fixture golden dataset (5–10 examples) producing real `eval_results` rows; drift comparison logic against a fixture baseline |
| M10 | Cost Circuit Breaker (§7.5) + Prometheus/Grafana/Langfuse wiring | Spend accumulation + cap comparison (pure functions) | Simulated spend breach → Policy Engine's `generate` decision flips to `stop`; human-reset flow via the approve endpoint |

**Backend E2E** (after M6 at minimum — this is the demo's actual proof point): automate TDD §12's sequence end to end against the full docker-compose stack, three scenarios:
1. Below-threshold JD → `below_threshold`, no documents generated.
2. Clean ATS fixture, good score → `submitted`.
3. CAPTCHA-fixture, good score → `ready_for_review` (the required edge case).

## 2. Frontend Implementation Plan

| # | Milestone | Unit tests | Integration tests |
|---|---|---|---|
| F0 **[EARLIEST DEMOABLE]** | React app scaffolding, API client, auth stub | — | — |
| F1 **[EARLIEST DEMOABLE]** | Apply view: JD submit form, score breakdown with evidence (retrieved chunks shown, TDD §6.4) | Form validation; score-breakdown rendering given mock data, including the below-threshold "stop" state | API client against MSW mocking the real request/response contract from TDD §9 |
| F2 **[EARLIEST DEMOABLE]** | Review queue: confidence-band grouping (PRD §5.2), bulk-approve, `needs_input` resolution | Band-grouping logic as a pure function (score → band); bulk-select state management | Review queue against MSW fixtures spanning both confidence bands + a `needs_input` case |
| F3 | History view: past applications, outcome updates | Sorting/filtering logic | Fetch + render against MSW fixtures |
| F4 | Model & Eval view (§3.3): model version list, drift alerts, promotion approve action | Status-badge logic (candidate/staging/production/archived → display state) | Approve action triggers the correct API call and reflects the resulting state |
| F5 | Accessibility — **baked into F1 onward, not a separate late pass** | `axe-core` automated checks added to every component's test suite starting at F1 | — |

`ENTERPRISE_READINESS.md` §9 already flags accessibility as "cheap to build in from the start, expensive to retrofit" — F5 isn't a milestone number so much as a standing requirement on every milestone from F1 forward; listed separately here only to make it visible, not to imply it's deferred.

**Frontend E2E**: Playwright (same tool as the Filler Agent — one browser-automation dependency for the whole project, not two) driving the real React app against the full backend stack:
1. Paste a good JD → watch it move through scoring → generation → fill → land in the review queue → approve → see terminal state.
2. Paste a below-threshold JD → see the stop message and score breakdown, nothing else happens.
3. A `needs_input` case → answer the flagged field → watch it resume.

## 3. Sequencing Backend and Frontend Together

**Frontend does not need to wait for backend code to exist.** `docs/API_REFERENCE.md` and `backend/api/openapi.yaml` are the frozen contract as of this plan — the frontend team can start F0–F2 immediately against MSW-mocked responses built from that spec, in parallel with backend M0 onward, not sequentially after it. The two tracks only need to sync when the *real* backend needs to replace the mocks (frontend integration tests, then e2e) — recommended sync points:

```
Backend:  M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10 → [Backend E2E]
Frontend: F0 → F1 → F2 → F3 → F4 → F5 -----------------------→ [Frontend E2E]
          (against openapi.yaml mocks from day one)              (against real backend)
```

Contract discipline matters more than usual here because of this parallelism: if backend implementation needs to diverge from `openapi.yaml` during M1–M10, update the spec in the same change and flag it to the frontend team immediately — a silent drift between what frontend mocked against and what backend actually shipped is exactly the failure mode this parallel structure is trying to avoid.

The **[EARLIEST DEMOABLE]**-tagged milestones (M0–M6, F0–F2, both E2E suites) remain useful as a checkpoint — if the timeline gets tight, that subset is still a legitimate fallback demo — but the target is now the complete set, M0–M10 and F0–F5, since the full system is the demo.
