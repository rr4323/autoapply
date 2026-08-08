# AgentOS — Product Requirements Document (PRD)
**Phase 1: "Apply Agent with Honest Scoring"**

| | |
|---|---|
| Status | Draft v1 |
| Owner | Lakshya Chhipa |
| Date | 2026-08-08 |
| Related | `AgentOS_GTM_Strategy.pdf` v1, whiteboard concept, `ENTERPRISE_READINESS.md`, `PERFORMANCE_SCALABILITY.md`, `SECURITY_ANALYSIS.md`, `COST_ANALYSIS.md`, `MULTI_TENANCY_AND_PRICING.md` |

---

## 1. Problem Statement

Job seekers applying to multiple roles repeat the same low-value, high-friction work for every application:

- Manually re-matching their resume against each job description
- Re-typing the same profile data into a different form on every ATS (Greenhouse, Workday, Naukri, company career sites, Google/MS Forms)
- No way to know, before applying, whether they're actually a fit — so they either spray-and-pray (hurts response rate, trains recruiters to distrust automation) or under-apply out of uncertainty
- Interview prep, notes, and revision live on a separate platform from the job itself, disconnected from the specific role's actual requirements
- Referrals are the highest-converting channel, but a referrer has no data to back their vouch — so people are reluctant to ask or refer

None of this is unsolved because it's hard to build — every existing autofill/auto-submit tool (Simplify, LazyApply, Sonara, FastApply, AutoApplyMax) already does some form of matching and filling. It's unsolved because every existing tool stops at submission. Nobody turns "did this person apply well, prepare well, and get referred well" into a trustworthy, persistent signal.

**This document scopes Phase 1 only**: the apply agent + honest scoring layer that seeds that signal. Referral trust, recruiter dashboard, and multi-platform expansion are explicitly deferred (see §7).

## 2. Goals

- **G1** — Eliminate manual form-filling and resume/cover-letter tailoring for Greenhouse/Lever-class job applications.
- **G2** — Show the user an honest JD-fit score *before* they apply, so the product's incentive is accuracy, not volume.
- **G3** — Remove the riskiest part of automation (the submit click) from platforms with bot-verification, while keeping the labor-saving part (matching, tailoring, filling) everywhere.
- **G4** — Instrument every run so structured scoring data (JD-fit, resume-match) is captured from user #1, even though nothing is monetized on it yet.
- **G5** — Ship something a single user can demo end-to-end: paste a JD → get a scored, tailored application → watch it get filled → see it either auto-submit or wait for one manual click.
- **G6** — Every factual claim in a generated resume/cover letter must be traceable back to the user's own profile data (retrieved, not invented) — this is what makes G2's "honest score" promise structurally true rather than just a prompt instruction. See TDD §6 (RAG Pipeline).
- **G7** — The system's own quality (retrieval relevance, generation groundedness, scoring accuracy) must be measurable against a fixed evaluation set, not judged by feel — so regressions are caught before they reach the user. See TDD §10 (Evaluation Strategy).
- **G8** — Quality must be monitored continuously in production, and a detected drop (drift) must be able to trigger retraining of the scoring model — with a human approval step before a retrained model goes live. See TDD §11 (Monitoring & MLOps Feedback Loop).

### Non-Goals (Phase 1)

- Not building a job board or job discovery/search engine — user supplies the JD/link.
- Not solving Workday or LinkedIn automation (different anti-automation posture; deferred).
- Not building the referral-trust layer or recruiter-facing product (no track record exists yet to power it).
- Not optimizing for application *volume*. A hard minimum match-score gate is a feature, not a limitation.
- Not building mock-interview/training-assistant agents yet (mentioned on the original whiteboard, sequenced for Phase 2 — needs the JD-fit scoring pipeline built first since it's meant to reuse that scoring logic, not duplicate it).

## 3. Target User / Persona

**Primary**: An active job seeker (e.g., a working professional or new grad) applying to 10–50 roles over a few weeks, technically comfortable enough to paste a job link and review a generated document, who is frustrated by repetitive form-filling and unsure of their real fit per role.

**Explicitly not the primary user in Phase 1**: recruiters. They're a Phase 3 audience who benefit from the data this phase generates, but nothing is built for them yet.

## 4. User Stories

1. As a job seeker, I paste a job posting URL (Greenhouse/Lever) and get back a JD-fit score and a resume-match score before I decide to apply.
2. As a job seeker, I get a tailored resume and cover letter generated from my base profile + the specific JD, so I don't hand-edit for every application.
3. As a job seeker, if the platform has no bot-verification and my score clears the minimum threshold, the agent fills and submits the application for me automatically.
4. As a job seeker, if the platform has a CAPTCHA/bot-check, the agent fills everything and prepares the application, then notifies me that it's ready for one manual click — I don't re-do any of the work, I just confirm.
5. As a job seeker, if a required field can't be resolved automatically (e.g., a custom screener question, salary expectation, work authorization), the agent flags it and batches it into a single review step rather than interrupting me application-by-application.
6. As a job seeker, I can see a running history of every application: score at time of apply, what was auto-submitted vs. manually confirmed, and outcome status if I update it.
7. As a job seeker, I will not be shown an inflated score to get me to apply — if my fit is genuinely low, the agent tells me and by default won't auto-apply.

## 5. Key Flows

### 5.0 Ingestion Flow (Daily, Automated)
1. A scheduled cron job runs once a day (configurable) and calls the Google Search API **once per active search profile** (§5.0.1) — a user with two profiles gets two searches, not one combined search.
2. Results are filtered to the ATS domain allowlist (Greenhouse, Lever, Workday, iCIMS, Jobvite, Ashby, SmartRecruiters) and deduplicated against previously-seen URLs.
3. Each new, unseen result is created as a `discovered` application, tagged with the profile that found it, and enters the same Apply Flow (§5.1) as if the user had pasted the URL — it still goes through scoring and the gate; discovery does **not** bypass the honesty/score gate.
4. User sees newly discovered roles land in their queue already scored, rather than having to find and paste links manually.

This replaces relying on Google Alerts emails: same underlying search, but pulled on our own schedule via API rather than parsed out of an inbox — no Gmail API/OAuth scope needed, and results are structured JSON instead of parsed HTML email.

**5.0.1 Search Query Builder — one query per named profile, not one combined query.** The query is **compiled from structured facets the user configures**, using the same Google search-operator vocabulary the [Google Hacking Database](https://www.exploit-db.com/google-hacking-database) catalogs, applied to job discovery instead of security recon — fully specified in `TDD.md` §3.1.1.

**Why profiles, not one flat facet set**: a single combined role list and skill list means any role paired with any skill counts as a match — "senior backend engineer" AND "LangChain" would pass even though that's not a real target combination. Rajeev's actual search intent is really **two distinct tracks**, so it's configured as two profiles (max 3 allowed per user, TDD §3.1.1):

**Profile 1 — "AI Engineer track"**:
```
(site:myworkdayjobs.com OR site:greenhouse.io OR site:lever.co OR site:icims.com OR site:jobvite.com OR site:ashbyhq.com OR site:smartrecruiters.com)
intitle:("senior AI engineer" OR "AI/ML engineer" OR "senior Python developer")
("LLM" OR "Generative AI" OR "LangChain" OR "Python")
("Delhi NCR" OR "Bangalore" OR "remote")
```

**Profile 2 — "Backend Engineer track"**:
```
(site:myworkdayjobs.com OR site:greenhouse.io OR site:lever.co OR site:icims.com OR site:jobvite.com OR site:ashbyhq.com OR site:smartrecruiters.com)
intitle:("senior software engineer" OR "senior backend engineer" OR "senior Golang developer")
("Golang" OR "Kubernetes" OR "AWS" OR "GCP")
("Delhi NCR" OR "Gurugram" OR "Noida" OR "remote")
```

Both profiles share the same ATS domain allowlist and exclusion set (`-"staffing agency" -intern -"contract to hire"`, TDD §3.1.1) — those aren't role-specific, so they're configured once, not per profile.
The role facet now defaults to `intitle:`-scoped (higher precision — a JD's page title reliably contains the role name, a bare keyword match doesn't) and a default exclusion facet filters recruiter-agency/internship noise the original hand-typed query never addressed. The user can still see and edit the compiled string directly (never a black box), but builds it from facets by default rather than starting from a blank query.

### 5.1 Apply Flow (happy path)
1. User submits a job URL (or pastes JD text) + selects their base profile/resume — either manually, or automatically via the Ingestion Flow above.
2. Agent scrapes/parses the JD.
3. Agent computes JD-fit score + resume-match score against the base profile.
4. If score < minimum threshold → agent stops, shows the score and the gap (missing skills/requirements), does **not** proceed to fill/apply unless user explicitly overrides.
5. If score ≥ threshold → agent generates tailored resume + cover letter + draft screener answers.
6. Agent opens the target ATS form and fills all resolvable fields.
7. Agent detects bot-verification presence:
   - **Not present** → auto-submits, logs the event.
   - **Present** → stops short of submit, marks application "ready for manual submit," notifies user.
8. Any unresolved required field is added to a batched review queue instead of blocking mid-fill.
9. Every step (score, decision, fill result, submit result) is logged as structured data.

### 5.2 Manual Review / Batch Confirm Flow
1. User opens a review queue showing all applications in "ready for manual submit" or "needs input" state.
2. **"Ready for manual submit" is grouped by confidence band, not shown as one flat list** *(resolved — see §9 item 2)*: applications scoring within a small margin below the auto-submit threshold (`min_autosubmit_score`) land in a "Ready — high confidence" band with a one-click "approve all in this band" bulk action; everything else lands in "Ready — lower confidence" and requires individual review. This reuses the score already computed for every application (TDD §7) rather than introducing new UI-only logic, and keeps the actual bulk-approve decision anchored to the same honesty signal the rest of the product is built around — a user bulk-approving is still trusting the score, not bypassing it.
3. For "needs input": user answers the flagged field(s) once; agent applies the answer and proceeds. Screener-answer fields the Generator answered are validated against an inferred field type/length before reaching this state (TDD §6.5) — a genuine mismatch routes here instead of being silently submitted wrong.

## 6. Scope — Phase 1 Feature List

| # | Feature | Priority |
|---|---|---|
| 1 | JD ingestion — manual (URL/pasted text) + automated daily search-API cron for Greenhouse/Lever-class ATS | P0 |
| 1a | Search Query Builder with named, multi-profile search (up to 3 per user) — per-profile role/skill/location facets, shared platform/exclusion config, compiled query with live preview before saving (TDD §3.1.1) | P1 |
| 2 | JD-fit / resume-match scoring, shown before apply | P0 |
| 3 | Resume tailoring + cover letter generation, retrieval-grounded (RAG) against the user's own profile — no invented experience | P0 |
| 4 | Form auto-fill on target ATS | P0 |
| 5 | Bot-verification detection → hybrid submit decision | P0 |
| 6 | Hard minimum match-score gate before any auto-apply fires | P0 |
| 7 | Structured event logging (score, decision, fill/submit outcome) | P0 |
| 8 | Batched review queue for unresolved fields / manual-submit-ready applications | P1 |
| 9 | Application history view | P1 |
| 10 | User override of the score gate (apply anyway, with a warning) | P2 |
| 11 | Offline evaluation harness (retrieval quality, generation groundedness, scoring accuracy) run on every prompt/retrieval/policy change | P1 |
| 12 | Production monitoring (metrics, dashboards, tracing) + nightly drift detection against the eval harness | P1 |
| 13 | Retraining pipeline for the scoring calibration model, gated by champion/challenger eval + human approval before promotion | P2 |

## 7. Out of Scope / Explicitly Deferred

- Referral-trust scoring and UI
- Recruiter dashboard / recruiter-facing product
- Mock interview / training assistant agent
- Marketing/blog agent, job-networking-platform monitoring, mail monitoring
- Workday, LinkedIn, and other non-Greenhouse/Lever platforms
- Multi-tenant / marketplace-of-agents model from the original whiteboard

## 8. Success Metrics (Phase 1)

Since this phase is about proving the mechanism, not revenue:

- **Correctness**: % of applications where auto-fill correctly populates all standard fields without manual correction.
- **Honesty check**: score shown pre-apply correlates with actual downstream outcome (recruiter response/interview) once enough data exists — this is qualitative in Phase 1 given small N.
- **Safety**: 0 auto-submits on any platform with a detected bot-check (this must be exact, not approximate).
- **Time saved**: manual time per application, before vs. after (self-reported / timed for demo purposes).

## 9. Open Questions — Resolved

Carried from the GTM strategy doc; all four are now resolved rather than open (kept here as a decision log, not deleted, so the reasoning behind each isn't lost):

1. **Resolved** — auto-submit requires both no bot-check *and* a stricter score bar than the general minimum (`min_autosubmit_score` > `min_generate_score`, TDD §7.1) — not a purely technical CAPTCHA check.
2. **Resolved** — see §5.2 above: confidence-band grouping with bulk-approve limited to the high-confidence band, not a flat bulk-approve-everything action.
3. **Resolved** — the cheapest validation is Rajeev's own Phase 1 usage: run ~20 AgentOS-gated applications against ~20 manually-selected "spray" applications over the same window and compare response/interview rate. No A/B infrastructure is worth building for an N of one user — that's a Phase 2+ investment, once there's a real user cohort to run a statistically meaningful test on.
4. **Resolved** — hard rule in code, not policy: score computation (TDD §6) has no code path that touches ranking/recommendation/engagement logic, and the Policy Engine (TDD §7) that gates on the score has no such dependency either — see TDD §1's design principles and §7.3's enforcement boundary.

## 10. Risks (product-level; technical mitigations in TDD §10)

- **ToS / bot-detection risk** on target ATS platforms — mitigated by hybrid submit model, not eliminated.
- **Reputational spam risk**: if the score gate is ever weakened for growth, this product degrades into exactly the category problem it's meant to solve (see GTM doc §2, §4).
- **Cold start**: with one user (the builder), there's no outcome data yet to validate the score's honesty against real results — Phase 1 demo leans on transparency of methodology (showing *why* a score was given) rather than proven predictive accuracy.
