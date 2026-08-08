# AgentOS — Frontend

React. Talks to the Go control plane over the REST API documented in:

- **`../docs/API_REFERENCE.md`** — start here. Full request/response schemas, auth, pagination, error format, and an explicit "what not to assume yet" section (no document preview endpoint, no WebSocket push, admin-gate the MLOps views).
- **`../backend/api/openapi.yaml`** — same contract, machine-readable. Import into Postman/Swagger UI, or generate a TypeScript client from it (`openapi-typescript` or similar) instead of hand-writing types that can drift from the real API.

## Views to build

Per `../docs/TDD.md` §3.3 and `../docs/IMPLEMENTATION_PLAN.md` §2 (milestones F0–F5):

1. **Apply view** — submit a JD URL/text, show the score breakdown with retrieved evidence (`GET /api/v1/applications/:id`'s `score_breakdown` + `retrieved_evidence`) before the user commits.
2. **Review queue** — confidence-band grouping (`../docs/PRD.md` §5.2): applications scoring within a small margin below `min_autosubmit_score` (fetch the real number from `GET /api/v1/policy/thresholds`, never hardcode it) get a bulk-approve action; everything else needs individual review. Also handles `needs_input` resolution.
3. **History view** — past applications, user-updatable outcome (`PATCH /api/v1/applications/:id/outcome`).
4. **Model & Eval view** — model version list, drift alerts, promotion approve action. Admin/debug — gate behind whatever role check exists once backend RBAC lands (`../docs/ENTERPRISE_READINESS.md` §1); don't ship it visible to a general user in the meantime.

## Testing

Per `../docs/IMPLEMENTATION_PLAN.md` §2: Vitest/Jest + React Testing Library for unit tests (written alongside each component, not after), MSW (Mock Service Worker) for integration tests against the real API contract from `openapi.yaml`, Playwright for e2e — reused from the backend's Filler Agent rather than adopting a second browser-automation tool, so ask the backend team before reaching for Cypress or another alternative.

**Accessibility is not milestone F5, it's every milestone from F1 on** — `axe-core` checks belong in each component's test suite as it's built, not as a retrofit pass at the end (`../docs/ENTERPRISE_READINESS.md` §9 explains why the retrofit is the expensive path).

## Not yet scaffolded

No `package.json`/build tooling committed yet (`IMPLEMENTATION_PLAN.md` F0). Pick the toolchain (Vite recommended for a React+TS SPA) and commit the scaffold as the first PR into this directory.
