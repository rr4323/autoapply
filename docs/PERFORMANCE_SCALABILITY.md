# AgentOS — Performance, Scalability & Capacity Planning
### Back-of-the-envelope calculations

| | |
|---|---|
| Status | Draft v1 |
| Owner | Rajeev Ranjan |
| Date | 2026-08-08 |
| Scope | Companion to `TDD.md` — turns its qualitative scalability claims (§13) into numbers: traffic, storage growth, LLM cost, the actual bottleneck, and at what scale each Phase-1 simplification needs revisiting |

---

## 0. Method

This is a back-of-envelope estimate, not a load test — the kind of estimation a system-design interview asks for: state assumptions explicitly, compute from them transparently, and flag which numbers are load-bearing versus illustrative. Every figure below traces to an assumption in §1; change an assumption and the downstream numbers change with it — that traceability is the point, not the specific digits.

**Four scale tiers**, used throughout so every section answers "at what point does this matter":

| Tier | Active users | Definition |
|---|---|---|
| **T0 — Solo** | 1 | Current Phase 1 target (PRD §3) |
| **T1 — Pilot** | 100 | First real cohort beyond the builder |
| **T2 — Growth** | 10,000 | Meaningful product-market signal |
| **T3 — Scale** | 100,000 | Volume that would actually feed the GTM strategy's Phase 3 recruiter product |

"Active user" = someone currently job-searching and using the product on a given day, per §1.

## 1. Assumptions (explicit, auditable)

| Assumption | Value | Basis |
|---|---|---|
| Applications per active user per day | 3 | PRD §3 persona: "10–50 roles over a few weeks" ≈ 1–3/day; using the upper end for headroom |
| JD length | ~800 words ≈ 1,100 tokens | Typical job posting |
| Base resume corpus per user | ~18 chunks × ~150 tokens ≈ 2,700 tokens | TDD §6.1 (chunked by experience entry/bullet) |
| Retrieval fan-out | top-k=5 per JD requirement, ~6 requirements/JD, deduped to ~15 unique chunks used | TDD §6.2 |
| Score-gate stop rate | 40% of applications stop at `below_threshold` (TDD §7.1) | Conservative — assumes decent but imperfect upstream targeting |
| Auto-submit rate among applications that pass the gate | 50% (no bot-check + score clears `min_autosubmit_score`) | Reasonable split given Greenhouse/Lever-class targets (TDD §7.1's stricter bar) |
| ATS layout previously unseen (triggers Filler Agent LLM-assisted DOM analysis, TDD §3.2) | 20% of fills | First-fill-per-domain cost before procedural memory (TDD §5) takes over |
| LLM assignment | **Claude Sonnet 5** for scoring/generation (quality-sensitive); **Claude Haiku 4.5** for groundedness checks and DOM analysis (cheap, high-volume, lower-stakes) | Pricing per current rate card (below); a deliberate cost-tiering choice, not a single-model default |
| Pricing (per MTok, standard rate) | Sonnet 5: $3.00 in / $15.00 out — Haiku 4.5: $1.00 in / $5.00 out | Current Anthropic API pricing as of this doc's date; Sonnet 5 has an introductory $2.00/$10.00 rate through 2026-08-31 — figures below use the standard rate as the durable baseline, not the temporary discount |
| Playwright fill duration | 15–30s per application (page load, field detection, fill, submit-check) | Typical headless-browser ATS interaction |

## 2. Traffic Model

| Tier | Active users | Apps/day | Apps/month | Peak req/sec (12hr active window, 2× burst multiplier) |
|---|---|---|---|---|
| T0 | 1 | 3 | ~90 | negligible |
| T1 | 100 | 300 | ~9,000 | ~0.014 |
| T2 | 10,000 | 30,000 | ~900,000 | ~1.4 |
| T3 | 100,000 | 300,000 | ~9,000,000 | ~14 |

Even at T3, peak request rate into the Go API (TDD §9) is trivial for a stateless service — this system is never bottlenecked on API request throughput. The bottlenecks are elsewhere (§6, §10).

## 3. LLM Cost Model

**Per-application token/cost breakdown**, following the pipeline in TDD §12:

| Stage | Model | Applies to | Input tokens | Output tokens | Cost/call |
|---|---|---|---|---|---|
| Scoring (semantic pass) | Sonnet 5 | 100% of applications | ~3,650 (JD + retrieved chunks + system) | ~250 (score breakdown) | $0.0147 |
| Generation (resume + cover letter + screener answers) | Sonnet 5 | 60% (pass the gate) | ~3,650 | ~1,800 | $0.0380 |
| Groundedness/citation check (§6.3) | Haiku 4.5 | 60% (same cohort as generation) | ~2,500 | ~150 | $0.0033 |
| Filler DOM analysis (unseen ATS layout) | Haiku 4.5 | 20% of the 60% that generate (=12% of all) | ~4,000 | ~500 | $0.0065 |

**Blended cost per 1,000 applications:**

```
1,000 × $0.0147 (scoring, all)                    = $14.70
  600 × $0.0380 (generation, 60%)                  = $22.80
  600 × $0.0033 (groundedness, 60%)                =  $1.98
  120 × $0.0065 (DOM analysis, 12%)                =  $0.78
                                                     -------
                                            Total    $40.26
```

**≈ $0.040 per application** — about 4 cents, blended across the full pipeline including the cheap stopped-at-gate path.

| Tier | Applications/month | LLM cost/month |
|---|---|---|
| T0 | ~90 | ~$3.60 |
| T1 | ~9,000 | ~$360 |
| T2 | ~900,000 | ~$36,000 |
| T3 | ~9,000,000 | ~$360,000 |

This is the number the cost circuit-breaker in `ENTERPRISE_READINESS.md` §11 is meant to protect — a retry bug that doubled call volume at T3 would silently add $360K/month, not a rounding error. Two cheap levers available before this becomes a real problem: **Message Batches API** (50% discount, viable for the nightly Drift Monitor eval runs which aren't latency-sensitive) and **prompt caching** (TDD's retrieved-chunk context is largely stable per user between applications within a session — a real caching opportunity not yet designed in, worth a follow-up).

## 4. Storage Growth Model

**Per-application footprint:**

| Component | Size | Where |
|---|---|---|
| `applications` row + `score_breakdown_json` | ~1 KB | Postgres |
| `application_events` (avg ~8 events/application) | ~4 KB | Postgres |
| `generated_documents` rows (metadata only, ×3) | ~0.6 KB | Postgres |
| `policy_decisions` rows (×2) | ~0.6 KB | Postgres |
| **Postgres subtotal** | **~6.2 KB** | |
| JD text + tailored resume + cover letter + screener answers (actual content) | ~28 KB | Object storage |

**Per-user footprint (one-time, grows only on profile edits):**

`profile_chunks` (pgvector): ~18 chunks × (~700 bytes text + 1536-dim float32 embedding ≈ 6 KB) ≈ **~120 KB/user**.

**Monthly growth by tier:**

| Tier | Postgres/month (incl. ~2× index overhead) | Object storage/month | pgvector (cumulative, one-time per user) |
|---|---|---|---|
| T0 | ~1.1 MB | ~2.5 MB | ~120 KB |
| T1 | ~112 MB | ~250 MB | ~12 MB |
| T2 | ~11 GB | ~25 GB | ~1.2 GB |
| T3 | ~112 GB | ~250 GB | ~12 GB |

At T2, roughly **130 GB/year** of Postgres growth and **300 GB/year** of object storage — still comfortably within a single well-resourced Postgres instance and any standard object store. At T3, Postgres growth (~1.3 TB/year) is where partitioning `application_events` by month (it's append-only per TDD §8 — a natural partition key) becomes worth doing proactively rather than reactively.

**pgvector scale check** (answers TDD §17 open question 7 concretely): at T3, cumulative `profile_chunks` reaches ~1.8M vectors (100,000 users × 18 chunks). An HNSW index on pgvector handles single-digit millions of vectors well on a properly resourced instance — **~1–2M vectors is a reasonable inflection point** to start evaluating a dedicated vector store, which lands somewhere between T2 and T3 on this traffic model. Below that, pgvector-on-primary-Postgres (TDD §5) remains the right simplification.

## 5. Message Bus Throughput

Each application generates 8 bus messages (one per topic hop in TDD §4). At T3 peak (~14 req/sec applications × 8 messages) ≈ **~110 messages/sec** sustained, with bursts higher. Redis Streams handles tens of thousands of ops/sec on modest hardware — **the message bus is not a throughput bottleneck at any tier modeled here.** Its risk is the concentration-of-concerns issue already flagged in `ENTERPRISE_READINESS.md` §4 (working memory + bus + LangGraph checkpointer sharing one instance), not raw capacity.

## 6. The Actual Bottleneck: Playwright Fleet Sizing

TDD §13 states Playwright browser instances are "the actual bottleneck" without a number. Here's the number:

- Applications reaching the Filler Agent = 60% of total (passed the score gate).
- At T2: 30,000/day × 60% = 18,000 fills/day, concentrated in a ~12-hour active window → **~0.42 fills/sec average**.
- At ~20s average fill duration, average concurrency needed = 0.42 × 20 ≈ **~8–9 concurrent browser instances**.
- Real traffic isn't uniform — applying a 2–3× peak multiplier for burst periods (e.g., right after the daily Ingestion Cron delivers new discovered jobs, §8) → **~20–25 concurrent Playwright instances at peak**.
- Each headless browser instance: ~300–500 MB RAM → **~10–12 GB RAM** just for the fill farm at T2, before Go/Python service overhead.

| Tier | Avg concurrent browsers | Peak concurrent browsers | Peak RAM (fill farm only) |
|---|---|---|---|
| T1 | <1 | ~2–3 | ~1.5 GB |
| T2 | ~8–9 | ~20–25 | ~10–12 GB |
| T3 | ~85–90 | ~200–250 | ~100–125 GB |

This is the number that actually drives the Filler Agent's replica count (TDD §13's "queue depth per topic drives replica count" — this section supplies the queue-depth math). At T3, the fill farm alone becomes a meaningfully sized fleet, and it's worth revisiting the 15–30s fill duration assumption specifically — any reduction there (e.g., via procedural-memory selector caching, TDD §5, cutting first-fill DOM analysis) has an outsized effect on this line, more than optimizing any other stage in the pipeline.

## 7. Latency Budget (End-to-End, Happy Path)

Per-hop estimate for a single application that auto-submits (TDD §12 sequence):

| Hop | Latency |
|---|---|
| Scrape/parse JD (fetch + LLM extraction) | 2–3s |
| Retrieve (embed query + pgvector search) | 0.5–1s |
| Score (Sonnet 5 call) | 2–4s |
| Policy decision (Go, in-memory rule eval) | <0.05s |
| Generate (Sonnet 5 call, larger output) | 5–10s |
| Fill (Playwright) | 15–30s |
| Bot-check + submit | 2–3s |
| **Total** | **~27–51s** |

**User-facing expectation: results in under a minute** for the auto-submit path. The `ready_for_review` path is faster to the point of stopping (skips the final submit step) but the user then adds their own review time on top, which is outside the system's control.

## 8. Synchronized-Burst Risk: Per-User Cron Scheduling

TDD §3.1's Ingestion Cron and Eval/Drift Cron are described per-mechanism but not per-schedule. If every user's daily Ingestion Cron fires at the same wall-clock time (e.g., everyone defaults to "6:00 AM UTC"), that's a **synchronized burst**: at T3, with the Search Query Builder's multi-profile fix (`TDD.md` §3.1.1) now running one query per active search profile, that's up to **~150,000 simultaneous Google Search API calls** (100,000 users × ~1.5 avg profiles, `COST_ANALYSIS.md` §2 — worse than the single-query-per-user figure this section originally cited), followed by a correlated spike in newly-discovered applications hitting the scoring pipeline all at once — exactly the kind of thundering-herd problem the Playwright fleet (§6) is least equipped to absorb, since its sizing above assumes traffic spread across a 12-hour window, not a 5-minute spike. The multi-profile fix makes this mitigation *more* important than it was before, not less.

**Mitigation**: jitter each user's cron trigger time within their configured window (e.g., ±15% of the interval, floored/capped — the same pattern used for scheduled-deployment firing jitter in comparable systems) rather than firing all users at one fixed UTC time. Cheap to add now (TDD §3.1), expensive to retrofit once T2+ traffic exists and the burst is already happening in production.

## 9. Infra Cost — Illustrative Order of Magnitude

**Caveat up front: these are ballpark figures for planning discussion, not vendor quotes** — actual cost depends on cloud provider, region, reserved vs. on-demand pricing, and negotiated rates. Use §3's LLM cost model for anything that needs to be precise; this section is for "is this roughly $100/month or roughly $100,000/month" sanity-checking.

| Tier | Postgres | Redis | Playwright fleet (compute) | Go/Python services | Monitoring stack (self-hosted MLflow/Langfuse/Prometheus) | Rough total/month |
|---|---|---|---|---|---|---|
| T0 | Free tier / single small instance | Free tier | 1 instance, shared | Minimal | Single small VM | **~$50–100** |
| T1 | Small managed instance | Small managed instance | Few instances | Few small instances | Single small VM | **~$300–600** |
| T2 | Medium managed instance, read replica worth considering | Medium instance | ~20–25 instance-equivalents (§6) | Modest fleet | Dedicated small VM | **~$3,000–6,000** |
| T3 | Large instance + read replicas, partitioning (§4) | Larger instance, HA config (per `ENTERPRISE_READINESS.md` §4) | ~200–250 instance-equivalents (§6) | Larger fleet | Dedicated instance(s) | **~$25,000–50,000** |

At T3, infra cost (~$25–50K/month) is roughly **7–14% of LLM cost** (~$360K/month, §3) — the dominant cost driver at scale is the LLM spend, not infrastructure, which argues for prioritizing the caching/batching optimizations noted in §3 over infra cost-cutting once the product reaches that scale.

## 10. When Each Phase-1 Simplification Needs Revisiting

Cross-referencing TDD's "revisit if it grows" statements with the numbers above:

| Simplification (TDD reference) | Fine at | Revisit around | Why (this doc's number) |
|---|---|---|---|
| pgvector on primary Postgres, not dedicated vector store (§5) | T0–T2 | ~1–2M vectors (between T2 and T3) | §4 |
| Redis Streams, not Kafka/NATS (§4) | T0–T3 and beyond | Not driven by throughput — Redis handles the modeled load at every tier (§5) | §5 |
| Single Postgres instance, no read replica | T0–T1 | T2, proactively | ~11 GB/month growth (§4) starts to make read-heavy queries (application history, eval dashboards) worth offloading |
| `application_events` unpartitioned | T0–T2 | T3 | ~112 GB/month growth (§4) — partition by month before it's forced |
| Nightly-only Drift Monitor / Trainer cadence (§11.3) | T0–T2 | T3, if retraining needs to happen more than daily | §13's note that this isn't a scaling concern until then still holds — no new evidence here to move it earlier |
| Fixed per-user cron trigger time (implicit in §3.1) | T0 (no burst risk with 1 user) | **T1, before it's a production incident** | §8 — cheapest fix window is now, before real user schedules exist to migrate |

## 11. Summary

| Tier | Bottleneck | What changes first |
|---|---|---|
| T0 (1 user) | None — every number here rounds to "negligible" | Nothing; this tier validates the mechanism, not the infrastructure |
| T1 (100 users) | None yet, but cron jitter (§8) should ship before real schedules exist | Add jitter to the Ingestion Cron now, cheaply |
| T2 (10K users) | Playwright fleet sizing (§6) becomes real (~20–25 concurrent instances); Postgres read load worth a replica | Scale the Filler Agent replica count; consider a read replica |
| T3 (100K users) | LLM cost (~$360K/month) dominates total spend; Playwright fleet becomes a genuinely large fleet (~200–250 instances); `application_events` needs partitioning; pgvector needs revisiting | Prioritize prompt caching/batching (§3) over infra optimization — LLM spend is 7–14× infra cost at this scale |
