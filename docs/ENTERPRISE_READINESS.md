# AgentOS — Enterprise Readiness Gap Analysis

| | |
|---|---|
| Status | Draft v1 |
| Owner | Rajeev Ranjan |
| Date | 2026-08-08 |
| Scope | Audits `PRD.md` + `TDD.md` (Phase 1: single-user apply agent) against what a real enterprise rollout would require — i.e., the GTM strategy's eventual Phase 3 recruiter/B2B product, or any paying multi-tenant customer |

---

## 0. Why this document exists, and how to read it

PRD.md and TDD.md are explicit, on purpose, that Phase 1 is a single-user demo (PRD §3: "not the primary user... recruiters," TDD §16: "nothing in this document is implemented yet"). That scoping decision is correct for what Phase 1 needs to prove. This document exists to make the *distance* between that scope and an enterprise-grade system explicit and enumerated, rather than discovered ad hoc later — the kind of accounting a Tech Lead is expected to be able to produce on demand ("what gets cut if the budget is halved," "what's the minimum bar to sell to one real customer").

Every row below is classified:
- ✅ **Addressed** — already designed in PRD/TDD, cited.
- ⚠️ **Deferred (documented)** — PRD/TDD already says this is out of scope for Phase 1, with a stated reason. Not a blind spot; a decision.
- ❌ **Blind spot** — not mentioned anywhere in PRD/TDD. This is the category worth the most attention, since an undocumented gap is the one that gets discovered at the worst possible time.

Priority is relative to **"selling this to one real enterprise customer,"** not to Phase 1's current single-user goal:
- **P0** — blocks any enterprise pilot; table-stakes for a paying B2B customer or handling real user PII at any scale beyond one person.
- **P1** — blocks general availability; needed before broad release even if a single pilot could survive without it.
- **P2** — blocks scale; needed once there are many tenants/regions/models, not before.

## 1. Identity, Access & Multi-Tenancy

| Capability | Status | Current state | Gap |
|---|---|---|---|
| Multi-tenancy (org/workspace model) | ⚠️ Deferred (now designed) | Phase 1 data model (TDD §8) is still flat — this remains correctly out of Phase 1 scope — but `MULTI_TENANCY_AND_PRICING.md` now has the full design: shared-schema + `tenant_id` + Postgres RLS, an implicit single-person org per Phase 1 user so the migration has no ambiguous backfill case, and a concrete per-layer change list | No longer a blind spot — the retrofit path is designed, just not built |
| RBAC / roles & permissions | ❌ Blind spot | No roles concept exists; every API endpoint (TDD §9) implicitly assumes "the one logged-in user acting on their own data" | No admin/support role, no read-only viewer role, no way to scope the MLOps dashboard (§3.3) to only people who should approve model promotions |
| SSO / SAML / OIDC | ❌ Blind spot | Auth is a one-word bullet ("Auth" in TDD §3.1's Go control-plane list) — mechanism (session vs. JWT vs. OAuth) isn't even specified | Any enterprise buyer will require SSO as a checkbox item during procurement |
| MFA | ❌ Blind spot | Not mentioned | Same as above — standard enterprise security questionnaire item |
| Admin impersonation / support access (with audit trail) | ❌ Blind spot | Not mentioned | Support/debugging on a user's account currently has no defined, audited path — someone would just query Postgres directly |

**Priority**: P0 for Phase 3 (recruiter/B2B product per GTM strategy) — this is the single largest gap, since almost every other enterprise requirement below assumes a multi-tenant, RBAC'd foundation that doesn't exist yet. P2 for continued single-user Phase 1 (genuinely not needed there).

## 2. Data Governance, Privacy & Compliance

| Capability | Status | Current state | Gap |
|---|---|---|---|
| Encryption at rest for credentials | ✅ Addressed | TDD §14: per-platform credentials encrypted, scoped, revocable | — |
| Scoped LLM data exposure | ✅ Addressed | TDD §14/§6: only retrieved chunks sent to the LLM, not bulk profile dumps | — |
| Working-memory TTL | ✅ Addressed | TDD §5: Redis working memory is TTL'd, cleared at terminal state | — |
| Data retention policy (episodic memory) | ❌ Blind spot | TDD §5 explicitly calls episodic memory **"Permanent"** — no retention window, no purge policy | No answer to "how long do we keep a rejected application's JD/resume/generated docs" — indefinite retention is itself a compliance liability |
| Right-to-erasure (GDPR/CCPA "delete my data") | ❌ Blind spot, and in **direct tension** with an existing design principle | `application_events` is explicitly append-only and permanent (TDD §8) — that's the moat dataset (GTM strategy §0.1) | A user's legal right to deletion cuts directly against "the moat is 12 months of verified scoring data." This isn't just an unaddressed feature, it's an unresolved conflict between two of the document's own stated goals and needs a real answer (e.g., pseudonymize-on-delete rather than hard-delete, keep aggregate/anonymized signal, purge PII fields but retain the score/outcome pair) — not currently designed either way |
| PII classification / data mapping | ❌ Blind spot | Not mentioned | No inventory of which fields across `profiles`, `profile_chunks`, `generated_documents`, Langfuse traces, and MLflow training data actually contain PII — needed before any DPA or compliance audit |
| Data residency / regional storage | ❌ Blind spot | Single Postgres instance implied throughout, no region discussion | Blocks any customer with an EU-only or India-only data residency requirement |
| DPA (Data Processing Agreement) readiness | ❌ Blind spot | Not mentioned | Standard requirement before any B2B contract touching candidate PII |
| Consent / liability disclosure for auto-submission | ❌ Blind spot | Policy Engine (TDD §7) governs *when* to auto-submit, but nothing addresses user consent language or liability if an auto-submitted application contains an error | If the agent submits something wrong on the user's behalf, there's no documented consent flow establishing what the user agreed to |

**Priority**: P0 across nearly this entire category before any paid product — even the current single-user Phase 1 is handling real PII (Rajeev's own resume/applications), so the retention/erasure conflict specifically is worth resolving in the design now, not deferred to "when we have enterprise customers."

## 3. Security Hardening

| Capability | Status | Current state | Gap |
|---|---|---|---|
| Service-to-service auth on internal endpoints | ✅ Addressed | TDD §14: `/internal/agent/callback` is shared-secret/mTLS authenticated | mTLS vs. shared secret is left as an "or" — not actually decided |
| Message bus payload minimization | ✅ Addressed | TDD §4.1/§14: references not blobs, reduces PII surface in the bus | — |
| Secrets management | ❌ Blind spot | No mention of where DB credentials, LLM API keys, MLflow/Langfuse credentials, or per-platform ATS credentials actually live (env vars? Vault? cloud secrets manager?) | With 8+ services now in the stack (Postgres, Redis, Go API, Python agent fleet, MLflow, Langfuse, Prometheus), secrets sprawl is a real, immediate risk without a named strategy |
| Key rotation policy | ❌ Blind spot | Not mentioned | — |
| Dependency / vulnerability scanning (SCA) | ❌ Blind spot | Not mentioned, despite the stack now pulling in LangGraph, Ragas, DeepEval, Playwright, MLflow, Langfuse — real supply-chain surface | — |
| SAST/DAST in CI | ❌ Blind spot | CI is mentioned only for tests/eval (TDD §10.1/§10.2), not security scanning | — |
| Rate limiting / abuse prevention on public API | ❌ Blind spot | TDD §9 API table has no rate-limit column or mention | `/api/applications` could be hammered with no documented protection — a real gap even at single-user scale if credentials leak |
| Penetration testing | ❌ Blind spot | Not mentioned | Standard pre-enterprise-sale requirement |
| SBOM / supply chain attestation | ❌ Blind spot | Not mentioned | Increasingly a procurement checkbox for enterprise/government buyers |

**Priority**: Secrets management + basic rate limiting = **P0**, cheap to build in now and expensive to retrofit. Pen testing / SAST-DAST / SBOM = **P1**, needed before enterprise sale but not before a personal-use Phase 1.

## 4. Reliability & Availability

| Capability | Status | Current state | Gap |
|---|---|---|---|
| Stateless, horizontally scalable agents | ✅ Addressed | TDD §13 | — |
| Backup/restore for the permanent dataset | ❌ Blind spot | Postgres holds the entire episodic memory / moat dataset (TDD §5) — no backup policy, no restore test, no defined RPO/RTO | Losing this database isn't just data loss, it undermines the GTM strategy's entire stated moat ("12 months of verified scoring data") — this is the single highest-consequence gap in the whole document |
| **Redis concentration risk** | ❌ Blind spot (specific architectural finding) | Redis currently serves **three distinct roles simultaneously**: working memory (§5), the message bus transport (§4), and the LangGraph checkpointer (§3.2.1) | A single Redis instance going down doesn't just slow one thing down — it simultaneously kills in-flight job state, all inter-agent communication, and every paused (`interrupt()`'d) HITL conversation at once. This is a real architecture concentration risk introduced by reusing Redis for multiple concerns (each individually a reasonable simplification, but not examined together) |
| Failover / HA for Redis and Postgres | ❌ Blind spot | Single-instance implied throughout | — |
| Circuit breakers / retry policy for external dependencies | ❌ Blind spot | No documented behavior for LLM provider outages, ATS site downtime, or Google Search API failures beyond "failed" status (TDD §16) | — |
| Graceful degradation | ❌ Blind spot | Not addressed — e.g., if a worker crashes mid-fill, is the LangGraph checkpoint actually resumable, or is Playwright's live browser session state lost even though the reasoning checkpoint persists? | Worth resolving explicitly, since the checkpointing story (§3.2.1) implies resumability that browser automation may not actually support |
| Defined SLA / uptime target | ❌ Blind spot | Not mentioned | Can't be sold to an enterprise without one |

**Priority**: Postgres backup/restore = **P0**, immediately, regardless of user count — this protects Phase 1's own stated goal (G4: capture scoring data from user #1), not just a future enterprise concern. Redis HA + RTO/RPO = **P1**. Multi-region = **P2**.

## 5. API & Platform Maturity

| Capability | Status | Current state | Gap |
|---|---|---|---|
| REST API surface | ✅ Addressed | TDD §9, reasonably complete for Phase 1's UI | — |
| API versioning | ❌ Blind spot | No `/v1/` prefix or version header scheme | Cheap to add now, expensive to retrofit once any external client depends on the current shape |
| Per-tenant rate limiting / quotas | ❌ Blind spot | Same gap as §3 above, specifically in a multi-tenant context | — |
| OpenAPI/Swagger spec | ❌ Blind spot | Not mentioned | Needed before any external integrator (or the eventual Phase 3 recruiter product) can build against this API |
| Public API / webhooks for integrators | ⚠️ Deferred (documented) | PRD §7 explicitly defers the recruiter-facing product | Correctly out of scope for Phase 1 — not a blind spot, just not yet relevant |

**Priority**: Versioning = **P1** (cheap now). Public API/webhooks = **P2**, correctly gated behind Phase 3 actually existing.

## 6. DevOps / SDLC Maturity

| Capability | Status | Current state | Gap |
|---|---|---|---|
| Unit/integration/eval tests in CI | ✅ Addressed | TDD §10.1/§10.2 | — |
| Infrastructure as Code | ❌ Blind spot | Not mentioned, despite the stack now including Postgres, Redis, Go services, Python agent fleet, MLflow, Langfuse, Prometheus/Grafana — 8+ operable services with zero mention of how they're provisioned | Even for a solo Phase 1 build, standing this up reproducibly (and being able to show it in the demo video) needs Terraform/Pulumi/Docker Compose named explicitly, not implied |
| Environment separation (dev/staging/prod) | ❌ Blind spot | Not mentioned | Directly relevant given how many times this document stresses the Policy Engine's safety-criticality (§1, §7) — there's currently no staged place to test a rule change before it's live |
| Deployment strategy (canary/blue-green) for the Policy Engine specifically | ❌ Blind spot | Not addressed — a Policy Engine rule change (TDD §7.1's YAML config) has no described rollout path | This is arguably an inconsistency worth flagging directly: the document treats the Policy Engine as the one component that must never behave unpredictably, yet says nothing about how a *change* to it gets safely rolled out |
| Rollback plan | ❌ Blind spot | Not mentioned for any component | — |

**Priority**: IaC + environment separation = **P0** — needed to build this reliably even solo, not just for enterprise scale. Staged rollout specifically for Policy Engine changes = **P1**, and worth resolving given how central that component's trustworthiness is to the rest of the design.

## 7. Legal, ToS & Liability

| Capability | Status | Current state | Gap |
|---|---|---|---|
| ATS bot-detection risk mitigation | ✅ Addressed | TDD §15, hybrid submit model throughout | Mitigates *detection*, not *permission* |
| Per-platform ToS legal review | ❌ Blind spot | Not addressed — no confirmation that Greenhouse/Lever's own terms actually permit automated form-filling even with human confirmation before submit | Detection risk and permission risk are different questions; only the first is addressed |
| AgentOS's own Terms of Service / liability disclosure to the user | ❌ Blind spot | Not mentioned | If the agent submits something erroneous on the user's behalf, there's no documented consent/liability framework establishing what the user agreed to |
| Insurance / liability coverage | ❌ Blind spot | Not mentioned | Standard question once this is a real product, not a demo |

**Priority**: P1 before any wide release — at minimum this should be a documented open question, not silent. P0 before any paid B2B product per the GTM strategy's Phase 3.

## 8. Observability → Operations (the human process behind the dashboards)

| Capability | Status | Current state | Gap |
|---|---|---|---|
| Metrics, dashboards, tracing | ✅ Addressed | TDD §11.1, genuinely thorough | — |
| Safety metric alerting | ✅ Addressed (partially) | TDD §11.1: "alerted on immediately, not just dashboarded" | Alerted *to whom*, *how*, and with what expected response time isn't specified |
| On-call rotation / paging policy | ❌ Blind spot | Not mentioned | The one metric this document calls "must stay exactly 0" (auto-submit with bot-check present) currently pages no one, specifically |
| Incident response runbook | ❌ Blind spot | Not mentioned | — |
| Defined severity levels / escalation path | ❌ Blind spot | Not mentioned | — |
| Status page | ❌ Blind spot | Not mentioned | Only relevant once there are users who'd check one |

**Priority**: On-call/paging for the Safety metric specifically = **P1**, and arguably should exist even solo (a self-page/notification for that one metric is cheap and closes a real gap the document itself calls critical). Full incident process/status page = **P2**, enterprise-scale concern.

## 9. Accessibility

| Capability | Status | Current state | Gap |
|---|---|---|---|
| WCAG compliance, keyboard nav, screen reader support | ❌ Blind spot | TDD §3.3 (React Dashboard) has zero accessibility mention | Most enterprise procurement (and any eventual B2B recruiter product) requires WCAG 2.1 AA attestation as a standard vendor security/accessibility questionnaire item |

**Priority**: P2 for Phase 1 (solo demo), **P0** before any enterprise procurement conversation — this is cheap to build in from the start of the React work and expensive to retrofit into an existing component library.

## 10. Testing Rigor Beyond Functional/Eval

| Capability | Status | Current state | Gap |
|---|---|---|---|
| Unit/integration tests | ✅ Addressed | TDD §10.1 | — |
| Agent/RAG evaluation harness | ✅ Addressed | TDD §10.2/§10.3 | — |
| Load / performance testing | ❌ Blind spot | Not mentioned | — |
| Chaos engineering | ❌ Blind spot | Notably absent given the message-bus idempotency gap already self-identified in TDD §16 ("designed but not yet load-tested under actual redelivery/failure scenarios") | The document already knows this is untested — chaos testing is the concrete way to close that specific, self-admitted gap |
| Security testing (SAST/DAST/pen test) | ❌ Blind spot | Covered above in §3 | — |

**Priority**: P1 — chaos testing specifically targets a gap the TDD already flags as known but unverified.

## 11. Cost Governance / FinOps

| Capability | Status | Current state | Gap |
|---|---|---|---|
| LLM cost tracking | ✅ Addressed | TDD §11.1: Langfuse tracks token cost per call | — |
| Third-party API quota awareness | ✅ Addressed | TDD §16: Google Search API free-tier cap explicitly flagged | — |
| Budget alerting | ❌ Blind spot | Cost is tracked but nothing alerts on a spend spike | — |
| Cost circuit-breaker | ❌ Blind spot | No automatic cutoff if, e.g., a retry bug caused runaway LLM calls | Directly analogous to the Policy Engine's existing philosophy (§1: "never touched by anything optimizing for engagement") — the same discipline isn't yet extended to spend |
| Per-user cost attribution | ❌ Blind spot | Not relevant at single-user Phase 1, but needed before multi-tenant billing | — |

**Priority**: A basic cost circuit-breaker = **P1**, cheap and consistent with a principle the document already holds elsewhere. Per-tenant attribution = **P2**, gated behind multi-tenancy existing at all.

---

## 12. Minimum Bar: "We need to sell one real enterprise pilot next quarter" (P0-only list)

If forced to answer the Track B–style question directly — budget is fixed, what's the smallest set of changes that makes this sellable, not just demoable — the P0 items above, in dependency order:

1. **Postgres backup/restore with a tested RPO/RTO** — protects the moat dataset even before anyone else is a customer.
2. **Multi-tenant data model (`organizations`/`tenant_id`)** — everything else in this section assumes this exists first; retrofitting it after the fact touches every table in TDD §8.
3. **RBAC + SSO/OIDC** — procurement-blocking without it.
4. **Secrets management + basic API rate limiting** — minimum security hygiene, cheap relative to everything else on this list.
5. **Data retention policy + a real answer to the right-to-erasure vs. permanent-audit-log tension** (§2 above) — this is a design decision, not just an engineering task, and needs to be made deliberately rather than discovered during a customer's legal review.
6. **IaC + dev/staging/prod separation** — needed to even deploy the above safely.
7. **AgentOS Terms of Service + per-platform ToS legal review** — before any paid usage, not after.

Everything else in this document (public API, multi-region, chaos engineering, full incident process, WCAG) is real but sequenced after this list, not blocking a first pilot.

## 13. What Was Already Right

Worth stating plainly, since a gap analysis skews toward what's missing: the existing design already has several things that most systems bolt on *after* an incident, not before —

- The Policy Engine (TDD §7) being a named, isolated, server-side-enforced component rather than inline logic is exactly the kind of separation enterprise security reviews look for.
- The eval harness (TDD §10) and drift/retrain loop (TDD §11) existing at all, before there's real production data to justify them, is unusual — most systems build this only after a quality incident forces it.
- Self-hosting Langfuse and MLflow specifically for data-residency reasons (TDD §14) is already halfway to the data-governance posture §2 above asks for — it just hasn't been extended to a full policy yet.
