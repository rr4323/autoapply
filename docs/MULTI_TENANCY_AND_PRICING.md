# AgentOS — Multi-Tenancy & Pricing Design
### Forward design for Phase 2/3 — not in Phase 1 scope

| | |
|---|---|
| Status | Draft v1 |
| Owner | Rajeev Ranjan |
| Date | 2026-08-08 |
| Scope | `PRD.md`'s non-goals correctly exclude multi-tenancy and monetization from Phase 1 — this doc doesn't change that. It exists so Phase 1's schema and architecture don't have to be re-founded later; `ENTERPRISE_READINESS.md` §1 already flagged multi-tenancy as the single largest enterprise gap without designing it, and `COST_ANALYSIS.md` computed unit economics with nothing to price them against. Both are closed here — as design, not as something to build now. |

---

## 0. Why design this before Phase 1 needs it

Two failure modes if this waits until it's urgent: retrofitting a `tenant_id` onto a schema that's already accumulated real user data is a migration under pressure, not a clean addition; and a pricing model bolted on after the fact tends to either compromise the honesty principle (TDD §1 — score computation must never serve engagement) or require rebuilding the enforcement mechanism from scratch. Designing both now, deliberately not implementing either, avoids both — the same judgment call already made for the MLOps loop (TDD §11), designed before there was training data to run it on.

## 1. What "Tenant" Means Here

The GTM strategy's Phase 3 is a recruiter-facing product — recruiters or recruiting orgs managing visibility into candidates, not a second class of individual user. That shapes the tenant model: **Organization** is the tenant boundary, and every user belongs to exactly one — including Phase 1's solo users, who get an **implicit single-person organization** created automatically at signup rather than a nullable "no org" special case threaded through every table and query. This is a deliberate simplification: "does this user belong to an org" is never a branch in the code, because the answer is always yes.

| Tenant type | Example | Members |
|---|---|---|
| Individual (implicit org) | Rajeev, Phase 1 | 1 user, auto-created org |
| Team/cohort org | A career-services org licensing AgentOS for a student cohort | Many users, one paying account |
| Recruiter org (GTM Phase 3) | A recruiting firm | Recruiter seats + visibility into candidates who've opted in |

## 2. Isolation Strategy

Three standard options, evaluated against AgentOS's actual scale (per `PERFORMANCE_SCALABILITY.md`'s tiers — thousands to low hundreds of thousands of users, not thousands of large enterprise tenants each needing hard infrastructure isolation):

| Strategy | Fit here |
|---|---|
| Database-per-tenant | Wrong scale — operational overhead (migrations × N databases, connection pooling × N) isn't justified until tenants are large enterprises with compliance-mandated hard isolation, which isn't this product's near-term customer profile |
| Schema-per-tenant | Same problem, smaller degree — still N migration targets |
| **Shared schema, `tenant_id` column, Postgres Row-Level Security** | **Chosen** — one schema, one set of migrations, isolation enforced at the database layer as a backstop independent of application code always remembering to add `WHERE tenant_id = ?` |

**Why RLS specifically, not just app-layer filtering**: application code that forgets a `WHERE tenant_id` clause is a data breach; a Postgres RLS policy that enforces `tenant_id = current_setting('app.tenant_id')` on every query makes that mistake structurally impossible rather than something a code reviewer has to catch every time. This is the same "structural, not policy" instinct already applied elsewhere in this design (TDD §6.3's grounded generation, §14.1's content trust boundary) — enforce the invariant where a bug can't bypass it, not where a reviewer has to remember it.

## 3. What Changes at Each Layer

| Layer | Change |
|---|---|
| **Data model** | New `organizations` table. Every table currently scoped by `user_id` (TDD §8: `applications`, `profile_chunks`, `application_events`, `generated_documents`, etc.) gains a denormalized `tenant_id` alongside it — denormalized rather than joined through `users`, because RLS policies and query performance both want it directly on the row, not one hop away. |
| **Auth / RBAC** | The blind spot `ENTERPRISE_READINESS.md` §1 already named — org roles (Admin, Member) become real here, on top of whatever individual-user auth Phase 1 ships. |
| **Working memory (Redis)** | Keys gain a tenant prefix (`tenant:{id}:job:{job_id}`, not just `job:{job_id}`) — prevents cross-tenant key collision and makes a Redis-level audit/scan tenant-scoped if ever needed for an incident. |
| **Message bus envelope (§4.1)** | `tenant_id` joins `job_id`/`trace_id` as a standard envelope field — every consumer can enforce or audit tenant scoping per message without re-deriving it from a join. |
| **Policy Engine (§7)** | Rules become tenant-scoped rule sets, not one global YAML file — this is *exactly* the trigger TDD §7.6 already named for moving off flat YAML toward a real rules DSL (OPA/Rego): per-recruiter-client rule customization. That decision was made before this doc existed and holds up here without revision. |
| **MLflow / Langfuse (§11)** | Both natively support project/workspace scoping — one MLflow experiment and one Langfuse project per tenant, so one org's admins never see another org's LLM traces or training runs. |
| **Playwright fleet (§14.3)** | No change needed — fills already run in a fresh ephemeral browser context per application, which happens to already be stronger isolation than tenant-level would require. Worth noting as a case where a Phase 1 security decision paid forward for free. |
| **Cost Circuit Breaker (§7.5)** | **Must change**, not just extend: `daily_spend` is currently a single global counter. With multiple paying tenants, one tenant's runaway spend must not pause generation for every other tenant — the breaker becomes per-tenant, and its cap becomes plan-aware (§6 below), not a single hardcoded number. |

## 4. Migration Path from Phase 1

Phase 1 ships with no `tenant_id` at all. The migration, when it happens: add `organizations` and a nullable-during-migration `tenant_id` to every scoped table, backfill by auto-creating a single-person org per existing user and setting `tenant_id` accordingly, then make the column `NOT NULL` and add the RLS policies. Because every user always has exactly one org (§1), there's no ambiguous backfill case to handle manually.

## 5. Pricing Model

Grounded in `COST_ANALYSIS.md` §4's fully-loaded cost of **~$4.30/user/month** at scale, and the GTM strategy's two stated price points — a competitive consumer category under $10–15/month (GTM §1) and a Phase 3 recruiter product at "$500/month or a placement fee" (GTM §0.1):

| Plan | Target | Price | Included | Enforcement |
|---|---|---|---|---|
| **Free** | Trial / low-intent users | $0 | Capped applications/month (e.g., 10), scoring + honest-fit shown for every application, but generation/auto-submit gated to a small subset | Plan quota gate (§6) — same mechanism as the Cost Circuit Breaker, generalized |
| **Individual** | Active job seeker (PRD §3 persona) | ~$15–19/month | High-cap or unlimited applications, full RAG/eval features, full hybrid auto-submit | Soft cap with overage billing, or hard cap — TBD, see §9 |
| **Team/Org** | Career-services cohorts, small recruiter orgs (GTM Phase 3) | Per-seat or per-managed-candidate, anchored near GTM's $500/month reference point | Everything in Individual, plus org-level dashboard, RBAC, referral-trust visibility (once that layer exists) | Same plan-quota mechanism, scoped to the org's aggregate usage rather than one user |

**The one invariant that must never move**: plan tier affects *quota and feature availability only* — never the score computation or the gate thresholds themselves. TDD §1 already states score computation has no dependency on any ranking/recommendation/engagement code path; this extends that same sentence to say it has no dependency on *billing* either. A free-tier user's score is exactly as honest as a paying org's — degrading that to drive upgrades would be the single fastest way to become the "spam volume over honesty" competitor category this product is explicitly positioned against (GTM §0.1).

## 6. Metering & Enforcement — Reusing the Cost Circuit Breaker, Not Reinventing It

The pricing module's enforcement mechanism **is the Cost Circuit Breaker (TDD §7.5), generalized**, not a new system:

- Today (§7.5): one global `daily_spend` counter, one global cap, gates the Policy Engine's `generate` decision.
- With pricing: `daily_spend` becomes **per-tenant**, and the cap is no longer a single operator-set number — it's derived from the tenant's active plan's included quota (§5), with the same `stop` outcome on the post-scoring decision (TDD §7.2) when quota is exhausted.
- The reasons array (TDD §7.2) that already makes every Policy Engine decision explainable now also explains quota exhaustion the same way it explains a low score or a spend cap — one mechanism, one UI pattern, no special-cased "you're out of credits" path bolted on separately.

This is the same design instinct as everywhere else in this document set: extend an existing, already-trusted mechanism rather than add a parallel one that has to be kept consistent with it by hand.

## 7. Billing Integration

- **Provider**: Stripe (Billing + metered usage), as the standard choice for subscription + usage-based billing rather than building payment infrastructure from scratch.
- **New data**: `plans(id, name, price_usd_monthly, included_applications, overage_price_per_application, features_json)`, `subscriptions(id, tenant_id, plan_id, status, stripe_subscription_id, current_period_start, current_period_end)`, `usage_records(id, tenant_id, application_id, event_type, cost_usd, billed, created_at)`.
- **New component**: a Billing Service (Go, control plane) subscribed to `application.terminal` (TDD §4/§12) — records a usage event per terminal application, periodically reconciles against Stripe's metering API. This piggybacks on an event that already exists rather than adding new instrumentation to the agent fleet.
- **Dashboard**: React (TDD §3.3) gains a plan/usage/billing view — same component that already renders the score breakdown and review queue, extended rather than a separate app.

## 8. Free-Tier Abuse Prevention

Reuses the existing `velocity_cap_per_day` pattern (TDD §7.1) rather than inventing anti-abuse logic — free-tier tenants simply get a stricter velocity cap and a lower plan-quota ceiling (§6), enforced by the same Policy Engine path every other gate already goes through. No separate fraud/abuse subsystem needed at this scale.

## 9. Open Questions (genuinely unresolved, flagged rather than guessed at)

1. Individual plan: hard cap vs. soft cap with overage billing — hard cap is simpler and matches the existing all-or-nothing feel of the Policy Engine's other gates; overage billing matches typical SaaS expectations but adds real billing-system complexity (metered overage reconciliation) this document hasn't sized.
2. Team/Org pricing: per-seat vs. per-managed-candidate — GTM's "$500/month or a placement fee" framing doesn't disambiguate this, and it's a real go-to-market decision, not a technical one.
3. Does a free tier exist at all in Phase 2, or does the product go straight to a paid-only individual tier — free tiers are a customer-acquisition cost that should be modeled against `COST_ANALYSIS.md`'s per-user figures before committing, not assumed by default.
4. Trial-to-paid conversion mechanics (grace period, downgrade behavior on non-payment) are entirely undesigned here.

None of §5–§9 should be read as a commitment — they're a considered starting shape, deliberately built to extend Phase 1's actual architecture (§6 in particular) rather than a generic SaaS pricing template, so that whenever Phase 2/3 pricing work actually starts, it starts from something concrete instead of a blank page.
