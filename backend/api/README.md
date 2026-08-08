# Go Control Plane

Implements the REST API in `openapi.yaml` (source of truth — see `../../docs/API_REFERENCE.md` for the human-readable walkthrough), the Policy Engine (`TDD.md` §7), the Ingestion Cron (§5.0 in `PRD.md`), the Eval/Drift Cron (`TDD.md` §11.2), and the Cost Circuit Breaker (`TDD.md` §7.5).

Not yet scaffolded — first real code here is `IMPLEMENTATION_PLAN.md` M1 (data model migrations + CRUD endpoints).

Nothing in this directory should implement business logic the Policy Engine owns without going through it — see `TDD.md` §1's design principles and §7.3's enforcement boundary before adding any code path that decides `generate`/`submit`/`require_review`.
