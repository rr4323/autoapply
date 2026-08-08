# AgentOS — API Reference (Frontend-Facing)

| | |
|---|---|
| Status | Draft v1 |
| Owner | Rajeev Ranjan |
| Date | 2026-08-08 |
| Scope | The REST contract between the React frontend (`frontend/`) and the Go control plane (`backend/api/`), per `TDD.md` §9. Fills in request/response schemas, auth, pagination, and error format that §9's endpoint table didn't specify — those gaps are resolved here, not left for the frontend team to guess at. `/internal/agent/callback` (service-to-service only) is intentionally excluded — nothing here is reachable from that surface. |

---

## 0. Conventions

**Base URL**: `/api/v1` — versioned prefix added here (TDD §9 didn't have one; `ENTERPRISE_READINESS.md` §5 flagged versioning as cheap now, expensive later, so it's in from the start).

**Auth**: `Authorization: Bearer <token>` on every request except `POST /api/v1/auth/login`. Session/JWT-based (the mechanism `TDD.md` §3.1 left as a one-word bullet — resolved here as the minimum frontend needs to build against; full SSO/OIDC is `ENTERPRISE_READINESS.md` §1 territory, not Phase 1).

**Content type**: `application/json` for all request/response bodies except file upload (`multipart/form-data`, profile resume upload).

**Pagination** (list endpoints): cursor-based.
```json
{ "data": [ /* items */ ], "next_cursor": "opaque-string-or-null" }
```
Request a page with `?cursor=<value>&limit=<n>` (default `limit=20`, max `100`).

**Error format** (every non-2xx response):
```json
{
  "error": {
    "code": "SCORE_BELOW_THRESHOLD",
    "message": "Human-readable explanation, safe to show in UI.",
    "details": { }
  }
}
```

| HTTP status | Meaning |
|---|---|
| 400 | Malformed request (validation error) |
| 401 | Missing/invalid auth token |
| 403 | Authenticated but not permitted (e.g., another user's application) |
| 404 | Resource doesn't exist |
| 409 | Conflict (e.g., confirming an application that isn't in `ready_for_review`) |
| 429 | Rate limited |
| 500 | Server error |

**Real-time updates**: Phase 1 frontend polls `GET /api/v1/applications/:id` — recommended interval **3–5s** while an application is in a non-terminal state (`pending`, `scored`, `filling`), stop polling once `status` is terminal (`below_threshold`, `submitted`, `ready_for_review`, `needs_input`, `failed`). A push-based WebSocket endpoint is a documented future option (TDD §12's sequence diagram allows either), not built for Phase 1 — don't build UI that assumes it exists yet.

---

## 1. Auth

### `POST /api/v1/auth/login`
**Auth**: none required.
```json
// Request
{ "email": "user@example.com", "password": "..." }

// 200 Response
{ "token": "eyJ...", "expires_at": "2026-08-09T00:00:00Z", "user": { "id": "usr_123", "email": "user@example.com" } }
```

### `POST /api/v1/auth/logout`
**200**: `{}` — invalidates the current token.

### `GET /api/v1/auth/session`
**200**: `{ "user": { "id": "usr_123", "email": "..." } }` — use on app load to check if the stored token is still valid.

---

## 2. Applications

### `POST /api/v1/applications`
Submit a JD manually (the Ingestion Cron creates `discovered` applications server-side — this endpoint is the `manual` path, PRD §5.1 step 1).

```json
// Request — one of jd_url or jd_text required
{ "jd_url": "https://boards.greenhouse.io/acme/jobs/12345" }
// or
{ "jd_text": "Full pasted job description text..." }
```

**202 Response** (processing started, not yet scored):
```json
{ "id": "app_abc123", "status": "pending", "source": "manual", "created_at": "2026-08-08T10:00:00Z" }
```

### `GET /api/v1/applications`
List applications for the current user.

**Query params**: `status` (filter, repeatable — e.g., `?status=ready_for_review&status=needs_input`), `source` (`manual` | `discovered`), `cursor`, `limit`.

```json
// 200 Response
{
  "data": [
    {
      "id": "app_abc123",
      "company": "Acme Corp",
      "role_title": "Senior Backend Engineer",
      "source": "discovered",
      "search_profile_id": "sp_1",
      "search_profile_name": "AI Engineer track",
      "jd_fit_score": 82,
      "resume_match_score": 79,
      "status": "ready_for_review",
      "bot_check_detected": true,
      "submitted_at": null,
      "created_at": "2026-08-08T06:00:00Z"
    }
  ],
  "next_cursor": "eyJpZCI6..."
}
```

`status` values (TDD §8): `pending`, `scored`, `below_threshold`, `filling`, `ready_for_review`, `needs_input`, `submitted`, `failed`.

### `GET /api/v1/applications/:id`
Full detail — this is what the Apply view's score breakdown (TDD §6.4) and the review queue's per-item detail render from.

```json
// 200 Response
{
  "id": "app_abc123",
  "company": "Acme Corp",
  "role_title": "Senior Backend Engineer",
  "jd_url": "https://boards.greenhouse.io/acme/jobs/12345",
  "source": "discovered",
  "search_profile_id": "sp_1",
  "search_profile_name": "AI Engineer track",
  "status": "ready_for_review",
  "jd_fit_score": 82,
  "resume_match_score": 79,
  "score_breakdown": {
    "deterministic_keyword_overlap": 0.71,
    "llm_semantic_score": 0.86,
    "final_score": 82,
    "reasons": [
      "Strong match on required skills: Go, Kubernetes, distributed systems",
      "Missing: 5+ years people management (JD lists as required)"
    ]
  },
  "retrieved_evidence": [
    { "chunk_id": "chunk_789", "text": "Led a team of 4 backend engineers...", "similarity": 0.91 }
  ],
  "generated_documents": [
    {
      "id": "doc_456",
      "type": "resume",
      "storage_ref": "s3://agentos-docs/app_abc123/resume.pdf",
      "source_chunk_ids": ["chunk_789", "chunk_101"],
      "groundedness_score": 0.94
    },
    { "id": "doc_457", "type": "cover_letter", "storage_ref": "s3://...", "source_chunk_ids": ["chunk_789"], "groundedness_score": 0.91 }
  ],
  "policy_decisions": [
    { "decision_point": "post_scoring", "action": "generate", "reasons": ["score 82 >= min_generate_score 60"], "created_at": "2026-08-08T06:00:05Z" },
    { "decision_point": "pre_submit", "action": "require_review", "reasons": ["bot_check_detected"], "created_at": "2026-08-08T06:00:45Z" }
  ],
  "bot_check_detected": true,
  "outcome": null,
  "submitted_at": null,
  "created_at": "2026-08-08T06:00:00Z",
  "updated_at": "2026-08-08T06:00:45Z"
}
```

### `POST /api/v1/applications/:id/confirm-submit`
User confirms a single `ready_for_review` application (PRD §5.2 step 2, individual path).

**409** if the application isn't currently `ready_for_review`.

```json
// 200 Response
{ "id": "app_abc123", "status": "submitted", "submitted_at": "2026-08-08T10:05:00Z" }
```

### `POST /api/v1/applications/bulk-confirm-submit`
Bulk-approve within the high-confidence band (PRD §5.2's resolved confidence-band design). Frontend computes which applications fall in the "high confidence" band client-side from the score already present in the list response, or the backend can be asked to filter — **backend is the source of truth for the band boundary** (`min_autosubmit_score` from the Policy Engine, TDD §7.1), so the frontend should not hardcode that number; see `GET /api/v1/policy/thresholds` below.

```json
// Request
{ "ids": ["app_abc123", "app_abc124", "app_abc125"] }

// 200 Response
{
  "results": [
    { "id": "app_abc123", "status": "submitted" },
    { "id": "app_abc124", "status": "submitted" },
    { "id": "app_abc125", "status": "failed", "error": "ATS form structure changed, needs manual review" }
  ]
}
```
Partial success is expected and normal — render per-item results, don't treat the whole batch as failed if one item fails.

### `POST /api/v1/applications/:id/resolve-input`
Answer flagged fields for a `needs_input` application (PRD §5.1 step 8, §6.5's field-validation routing).

```json
// Request
{ "fields": [ { "field_name": "salary_expectation", "value": "$150,000 - $170,000" } ] }

// 200 Response
{ "id": "app_abc123", "status": "filling" }
```

### `PATCH /api/v1/applications/:id/outcome`
User-supplied outcome update (TDD §5's episodic memory — this is what eventually feeds the calibration model, TDD §11.3).

```json
// Request
{ "outcome": "interview" }  // "interview" | "rejected" | "no_response"

// 200 Response
{ "id": "app_abc123", "outcome": "interview" }
```

---

## 3. Profile

### `GET /api/v1/profile`
```json
// 200 Response
{
  "id": "usr_123",
  "base_resume_doc_id": "doc_001",
  "skills": ["Go", "Python", "Kubernetes", "distributed systems"],
  "experience": [
    { "id": "exp_1", "company": "Previous Co", "title": "Staff Engineer", "start_date": "2022-01", "end_date": null, "bullets": ["Led a team of 4...", "Designed the payments platform..."] }
  ]
}
```

### `PUT /api/v1/profile`
Updates trigger re-chunking/re-embedding (TDD §6.1, §9) — this call is not instant; response reflects the update accepted, not that indexing has finished.
```json
// Request — same shape as GET response, without id
{ "skills": [...], "experience": [...] }

// 202 Response
{ "id": "usr_123", "reindexing": true }
```

### `POST /api/v1/profile/resume` (multipart/form-data)
Upload a new base resume file. Field name: `file`.
```json
// 202 Response
{ "base_resume_doc_id": "doc_002", "reindexing": true }
```

---

## 4. Search Criteria & Search Profiles (Ingestion, PRD §5.0.1 / TDD §3.1.1)

**Two-level model, not a single facet set**: `search-criteria` is shared config (one per user — which ATS platforms, what to exclude); `search-profiles` is per-track config (up to 3 per user — role, skills, location for one search intent, e.g. "AI Engineer track"). This split exists specifically to avoid cross-pollination — one flat role×skill list would let "senior backend engineer" match against "LangChain" even though that pairing was never intended (TDD §3.1.1 has the full reasoning). **The frontend should render this as: one shared settings panel (platforms + exclusions) plus a list of named profile cards (add/edit/delete/toggle active), not a single form.**

### `GET /api/v1/search-criteria` — shared config
```json
{
  "ats_domain_allowlist": ["greenhouse.io", "lever.co", "myworkdayjobs.com"],
  "exclusion_terms": ["staffing agency", "intern", "contract to hire"]
}
```

### `PUT /api/v1/search-criteria`
Same shape as the request body.

### `GET /api/v1/search-profiles` — list this user's profiles (max 3)
```json
{
  "data": [
    {
      "id": "sp_1",
      "name": "AI Engineer track",
      "role_titles": ["senior AI engineer", "AI/ML engineer"],
      "title_scoped": true,
      "skill_keywords": ["LLM", "LangChain", "Python"],
      "locations": ["remote", "Bangalore"],
      "compiled_query_text": "(site:greenhouse.io OR site:lever.co OR site:myworkdayjobs.com) intitle:(\"senior AI engineer\" OR \"AI/ML engineer\") (\"LLM\" OR \"LangChain\" OR \"Python\") (\"remote\" OR \"Bangalore\") -\"staffing agency\" -intern -\"contract to hire\"",
      "compiled_at": "2026-08-08T09:00:00Z",
      "active": true
    }
  ]
}
```
Note the compiled query already includes the shared `ats_domain_allowlist`/`exclusion_terms` from §4's `search-criteria` — the frontend doesn't need to merge them client-side, the backend compiles the full string.

### `POST /api/v1/search-profiles`
Request: `{ name, role_titles, title_scoped, skill_keywords, locations }`. **409** if the user already has 3 active profiles (the cap, TDD §3.1.1) — surface this as a clear limit reached message, not a generic error.

### `PUT /api/v1/search-profiles/:id` / `DELETE /api/v1/search-profiles/:id`
Update or remove a profile. `PUT` recompiles and returns the updated `compiled_query_text` — show it to the user as confirmation of what will actually run, never a silent save.

### `POST /api/v1/search-profiles/preview`
Same body shape as `POST /search-profiles` (no `id` needed — this previews a profile that may not exist yet), **does not save**. For live-preview-as-you-type in the profile editor.
```json
// 200 Response
{ "compiled_query_text": "...", "estimated_length_chars": 380, "within_length_limit": true }
```
`within_length_limit: false` means the compiler would drop lowest-priority terms to fit (TDD §3.1.1) — surface this in the UI, don't let the user discover it only after saving.

### Application attribution
`GET /api/v1/applications` and `GET /api/v1/applications/:id` (§2) now include `search_profile_id`/`search_profile_name` on `discovered`-source applications — render which track surfaced a given result (e.g., a small "via AI Engineer track" tag), not just that it was discovered.

---

## 5. Policy Thresholds (read-only, for frontend band logic)

### `GET /api/v1/policy/thresholds`
Lets the frontend render "why" without hardcoding numbers that live in the Policy Engine's config (TDD §7.1) — e.g., the confidence-band boundary in the review queue (PRD §5.2).
```json
{ "min_generate_score": 60, "min_autosubmit_score": 80 }
```
Intentionally excludes `velocity_cap_per_day`, `max_daily_generate_spend_usd`, and anything else operational — this endpoint exposes only what the UI needs to render, not the full rule set.

---

## 6. Evaluation & MLOps (admin/debug — gate behind a role check, not shown to a general user)

### `GET /api/v1/eval/latest`
```json
{ "run_type": "nightly", "dataset_version": "golden-v1", "completed_at": "2026-08-08T02:00:00Z",
  "results": [ { "metric_name": "faithfulness", "value": 0.87 }, { "metric_name": "context_precision", "value": 0.81 } ] }
```

### `GET /api/v1/mlops/models`
```json
{ "data": [ { "id": "mv_1", "mlflow_model_name": "scoring-calibration", "mlflow_version": 3, "current_stage": "Staging", "promoted_at": null, "eval_metrics": { "mae": 4.2 } } ] }
```

### `GET /api/v1/mlops/drift`
```json
{ "data": [ { "checked_at": "2026-08-08T02:00:00Z", "metric_name": "calibration_error", "value": 5.1, "baseline_value": 4.0, "breached": true } ] }
```

### `POST /api/v1/mlops/models/:id/approve`
```json
{ "id": "mv_1", "current_stage": "Production", "promoted_at": "2026-08-08T10:00:00Z", "promoted_by": "usr_123" }
```

---

## 7. What the Frontend Should NOT Assume

- **No endpoint returns raw document content** — `generated_documents[].storage_ref` is a pointer; fetching actual file bytes needs a separate signed-URL step not yet designed (flag this to backend if the Apply/Review views need inline document preview, not just download).
- **No server-sent events / WebSocket endpoint exists yet** — poll, per §0.
- **`GET /api/v1/eval/latest` and `/mlops/*` are not scoped to a "safe for any logged-in user" contract yet** — treat as admin-only until backend confirms an RBAC model (`ENTERPRISE_READINESS.md` §1).
- **Bulk actions can partially fail** — always render per-item results from `bulk-confirm-submit`, never assume all-or-nothing.
