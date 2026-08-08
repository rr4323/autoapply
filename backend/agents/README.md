# Python Agent Fleet

Eight independent message-bus consumers, per `../../docs/TDD.md` §3.2 — each its own process, subscribed to exactly one input topic (§4), sharing nothing in-process:

| Agent | Subscribes to | Publishes |
|---|---|---|
| Scraper | `jd.discovered` | `jd.parsed` |
| Retriever (RAG) | `jd.parsed` | `context.retrieved` |
| Scoring | `context.retrieved` | `application.scored` |
| Generator | `policy.decision=generate` | `documents.generated` |
| Filler (Playwright) | `documents.generated` | `form.filled` |
| Verifier/Submit | `form.filled` | `application.terminal` |
| Drift Monitor | Eval/Drift Cron trigger | `model.drift_detected` |
| Trainer | `model.drift_detected` | `model.promoted` |

Frameworks: LangGraph (intra-agent reasoning, TDD §3.2.1), Ragas + DeepEval (evaluation, §10), MLflow (training/registry, §11.3) — see `TDD.md` §2.1 for the full framework table and why each was chosen.

Build order: `../../docs/IMPLEMENTATION_PLAN.md` §1, milestones M2 (Scraper) through M9 (eval/Drift/Trainer) — sequenced so each agent is independently testable against a fixture before the next one depends on it.

**Security-critical**: every agent that touches scraped JD/DOM content must follow the content trust boundary in `TDD.md` §14.1 — that content is data, never instructions. Read it before writing a Scraper, Retriever, or Generator prompt.
