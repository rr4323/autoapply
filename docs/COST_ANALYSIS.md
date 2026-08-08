# AgentOS — Cost Analysis (Total Cost of Ownership)

| | |
|---|---|
| Status | Draft v2 — Search API costs updated for the multi-profile Search Query Builder fix (§2) |
| Owner | Rajeev Ranjan |
| Date | 2026-08-08 |
| Scope | Extends `PERFORMANCE_SCALABILITY.md` §3 (LLM cost) and §9 (infra cost ballpark) into a full TCO — and closes two cost line items the GTM strategy named but the performance doc never actually modeled |

---

## 0. What was missing from the earlier cost model

`PERFORMANCE_SCALABILITY.md` modeled LLM token cost (§3) and gave an infra cost ballpark (§9) — but two costs the GTM strategy document itself flagged as real unit economics never made it into that model:

1. **CAPTCHA/proxy/anti-detection infrastructure** — `AgentOS_GTM_Strategy.pdf` §4 states "~$3/1,000 applications" as the assumed unit cost for this, in the context of the ban/reputation-risk mitigation. That number was never carried into `PERFORMANCE_SCALABILITY.md`'s per-application cost breakdown.
2. **Google Custom Search API overage** — `TDD.md` §16 flags the 100-queries/day free tier as a known constraint "fine for one user, a cost line item at scale" but never actually prices the overage.

Both are fixed here. This is the gap this document exists to close, alongside the unit-economics/margin question neither prior doc asked.

## 1. Full Per-Application Cost Model

Building directly on `PERFORMANCE_SCALABILITY.md` §3's $0.040/application LLM figure, adding the two missing components:

| Component | Cost/application | Source |
|---|---|---|
| LLM (Sonnet 5 scoring + generation, Haiku 4.5 groundedness/DOM checks) | $0.0403 | `PERFORMANCE_SCALABILITY.md` §3 |
| CAPTCHA/proxy/anti-detection infrastructure | $0.003 | GTM strategy §4 unit economics (~$3/1,000 applications) — applies per application that reaches the Filler Agent (60% of total per the traffic model), so blended across *all* applications it's $0.0018/application |
| Object storage (JD text + generated documents, ~28 KB/application) | ~$0.0000006 | S3-class pricing (~$0.023/GB/month) — negligible per-application, shows up at aggregate scale (§3 below) |
| **Total, blended across all applications (including gate-stopped ones)** | **≈ $0.042/application** | |

The CAPTCHA/proxy cost only applies once an application has cleared the score gate and reaches the Filler Agent — it's not incurred on the 40% that stop at scoring. That's a genuine cost *benefit* of the score gate beyond its stated honesty purpose (PRD G2): **the gate is also a cost control**, cutting anti-detection spend on applications that were never going to be worth applying to anyway. Worth stating explicitly since it wasn't framed this way before.

## 2. Google Search API Overage

**Updated for the Search Query Builder's multi-profile fix** (`TDD.md` §3.1.1): the Ingestion Cron now runs **one query per active search profile**, not one query per user — a user with 2 profiles (like PRD §5.0.1's worked example) generates 2 queries/day, up to the 3-profile cap. Modeled here at an **average of 1.5 active profiles/user** (most users run 1–2 tracks; few will max out at 3). Google's Custom Search JSON API gives 100 free queries/day *per API project*, not per user — so unless each user is provisioned a separate API key (not currently designed, and impractical), all users share one project's quota, which now depletes faster than the earlier one-query-per-user model assumed.

| Tier | Avg queries/day (users × 1.5) | Free-tier queries | Billable queries/day | Cost/day (~$5/1,000 queries, standard published rate) | Cost/month |
|---|---|---|---|---|---|
| T0 (1 user) | 2 (Rajeev's own 2-profile setup) | 2 | 0 | $0 | $0 |
| T1 (100 users) | 150 | 100 | 50 | $0.25 | ~$7.50 |
| T2 (10,000 users) | 15,000 | 100 | 14,900 | $74.50 | ~$2,235 |
| T3 (100,000 users) | 150,000 | 100 | 149,900 | $749.50 | ~$22,485 |

**This is a real, previously-unpriced cost that now becomes material at T1, not T2** — the multi-profile fix moved the free-tier exhaustion point earlier than the original single-query model assumed, which is exactly the kind of downstream cost effect a precision fix can have and is worth surfacing rather than letting the earlier (now-stale) "$0 at T1" claim stand uncorrected. Still small in absolute terms at T1, but the *trigger point* moved. At T1→T2, this remains also the point where a single shared API project starts being an operational risk (one quota, one key, one point of failure for every user's discovery pipeline) independent of the dollar cost — see `PERFORMANCE_SCALABILITY.md` §10.

## 3. Full TCO by Tier

Combining `PERFORMANCE_SCALABILITY.md` §3 (LLM) and §9 (infra), plus the two additions above:

| Tier | LLM | Infra (illustrative) | CAPTCHA/proxy | Search API overage | **Total/month** |
|---|---|---|---|---|---|
| T0 | ~$3.60 | ~$50–100 | ~$0.16 | $0 | **~$55–105** |
| T1 | ~$360 | ~$300–600 | ~$16 | ~$7.50 | **~$684–984** |
| T2 | ~$36,000 | ~$3,000–6,000 | ~$1,620 | ~$2,235 | **~$42,855–45,855** |
| T3 | ~$360,000 | ~$25,000–50,000 | ~$16,200 | ~$22,485 | **~$423,685–448,685** |

At every tier, **LLM cost remains the dominant line item** (80–86% of total at T2/T3) — this doesn't change the priority call already made in `PERFORMANCE_SCALABILITY.md` §11 (optimize LLM spend via caching/batching before infra), it reinforces it with the fuller picture.

## 4. Unit Economics — Cost Per User

| Tier | Total/month | Active users | Fully-loaded cost/user/month |
|---|---|---|---|
| T0 | ~$80 | 1 | n/a (fixed-cost solo build) |
| T1 | ~$834 | 100 | ~$8.34 |
| T2 | ~$44,355 | 10,000 | ~$4.44 |
| T3 | ~$436,185 | 100,000 | ~$4.36 |

Cost per user **drops and then flattens** from T1 to T2/T3 — the fixed infra floor (§9's baseline instance costs) dominates at T1's small denominator, while variable costs (LLM, proxy, search) that scale linearly with usage dominate at T2/T3, so the per-user figure converges rather than continuing to fall. Don't expect economy-of-scale cost reduction much below ~$4.35/user/month with this architecture as designed — further reduction would have to come from the LLM-cost-reduction levers (`PERFORMANCE_SCALABILITY.md` §3: caching, batching, or a cheaper model for the scoring pass specifically) rather than from infra consolidation.

**Framing against the GTM strategy**: the GTM doc's category comparison (§1) notes competitors pricing below $10/month, and envisions the eventual Phase 3 recruiter product at "$500/month or a placement fee" (§0.1) — not a consumer subscription. At ~$4.35–4.40/user/month fully loaded, a consumer subscription anywhere in the $10–15/month range (matching the competitive category) would clear a healthy margin at T2+ scale, *if* Phase 1's honest-scoring/RAG/eval investment doesn't change the unit cost materially as it matures — which the numbers here suggest it won't, since LLM and proxy costs (not the MLOps/eval overhead) dominate the total. This is a genuinely useful data point for the eventual monetization conversation the GTM doc defers past Phase 1 (GTM §5) — Phase 1 doesn't need to answer pricing, but it's worth knowing the unit economics support a normal SaaS subscription, not just the B2B recruiter model.

## 5. Design Fix: Cost Circuit Breaker Default Cap

`SECURITY_ANALYSIS.md` §2.5 identifies the missing cost circuit breaker as a security/availability finding and points here for the number. Using this tier data:

- At T2 (~10,000 users), *daily* LLM spend averages ~$1,200/day (~$36,000/30). A reasonable **daily generation-spend cap** for the circuit breaker (TDD §7.5) at this tier is **2–3× the trailing 7-day average** — tight enough to catch a genuine runaway (a bug or attack producing 2-3x normal volume) within a day, loose enough not to false-positive on ordinary demand variance (e.g., a Monday-morning application surge).
- This should be a **per-tier-recalculated config value**, not a hardcoded constant — the Policy Engine's rule model (TDD §7.1) already treats thresholds as config, and the spend cap should follow the same pattern, recalculated from a rolling average rather than set once and forgotten.

## 6. Gaps Still Open After This Pass

- **No per-user cost attribution** (`ENTERPRISE_READINESS.md` §11 already flags this as P2, gated behind multi-tenancy existing) — this doc's tier-level averages can't yet answer "which specific user is expensive," only "what does the fleet cost."
- **CAPTCHA/proxy vendor not chosen** — the $3/1,000 figure is the GTM doc's planning assumption, not a quoted vendor price; before this becomes a real budget line, get an actual quote from a proxy/anti-detection provider and replace the estimate.
- **No cost-per-successful-outcome metric** — everything here is cost per *application*, not cost per *interview* or *offer*. Once `application_outcomes` (TDD §5) has real data, a cost-per-outcome view would be the more honest efficiency metric, but there's no data for it at Phase 1.
