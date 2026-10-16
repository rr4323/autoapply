# AgentOS — Frontend

React. Talks to the Go control plane over the REST API documented in:

- **`../docs/API_REFERENCE.md`** — start here. Full request/response schemas, auth, pagination, error format, and an explicit "what not to assume yet" section (no document preview endpoint, no WebSocket push, admin-gate the MLOps views).
- **`../backend/api/openapi.yaml`** — same contract, machine-readable. Import into Postman/Swagger UI, or generate a TypeScript client from it (`openapi-typescript` or similar) instead of hand-writing types that can drift from the real API.

## Running it

```
make up        # full backend stack (postgres/redis/minio/api/agent-worker)
make dev-web    # Vite dev server at :5173, proxying /api/* to :8080 — no CORS, no base-URL env var
```

Phase 1 is explicitly single-user (`docs/TDD.md` §16 — SSO/session auth is a Phase 3 blind spot), so there's no login screen: every request hits the Go API's `DefaultStubUserID` demo user automatically.

## Views to build

Per `../docs/TDD.md` §3.3 and `../docs/IMPLEMENTATION_PLAN.md` §2 (milestones F0–F5):

1. **Apply view** — ✅ built (`src/pages/NewApplicationPage.tsx`, `ApplicationDetailPage.tsx`). Submits a JD URL/text, shows the score breakdown live as agents process it. `retrieved_evidence` is still always `[]` — the Go API never persisted per-application retrieval results (Step 26's `context.retrieved` is working-memory-only), so there's nothing to render yet.
2. **Review queue** — not built. Confidence-band grouping (`../docs/PRD.md` §5.2) and bulk-approve need `GET /api/v1/policy/thresholds`, which doesn't exist yet — the detail page's single confirm-submit button (`POST /applications/:id/confirm-submit`) covers the MVP path.
3. **History view** — partially built: `ApplicationsListPage.tsx` lists everything with status/score. Outcome tracking (`PATCH /api/v1/applications/:id/outcome`) isn't built on either side yet.
4. **Model & Eval view** — not built. Admin/debug, correctly out of MVP scope per this doc's original guidance.
5. **Profile view** — not in the original milestone list, but added: `src/pages/ProfilePage.tsx`, since the Apply flow needs *something* to score against. Known gap, flagged in the page itself: saving a profile doesn't trigger re-indexing (`docs/BACKEND_BUILD_STEPS.md` Step 25's chunk/embed/write pipeline exists in `backend/agents/.../retriever/indexer.py` but nothing calls it after a save), so scoring won't reflect profile edits until that trigger is built.

## Testing

Per `../docs/IMPLEMENTATION_PLAN.md` §2: Vitest/Jest + React Testing Library for unit tests (written alongside each component, not after), MSW (Mock Service Worker) for integration tests against the real API contract from `openapi.yaml`, Playwright for e2e — reused from the backend's Filler Agent rather than adopting a second browser-automation tool, so ask the backend team before reaching for Cypress or another alternative.

**Accessibility is not milestone F5, it's every milestone from F1 on** — `axe-core` checks belong in each component's test suite as it's built, not as a retrofit pass at the end (`../docs/ENTERPRISE_READINESS.md` §9 explains why the retrofit is the expensive path).

## Toolchain

Vite + React + TypeScript, `react-router-dom` for routing, no UI framework (plain CSS in `src/index.css`). Types in `src/api/types.ts` are hand-written against `backend/api/internal/handlers/dto.go`/`openapi.yaml` rather than codegen'd — `openapi-typescript` hit a peer-dependency conflict with this toolchain's TypeScript version; worth revisiting since the API surface is still small enough to hand-maintain without much drift risk.

No tests yet (`Testing` section above is still the target, not the current state) — this scaffold is unit/lint/build-verified and manually exercised against the real running stack, not test-covered.
