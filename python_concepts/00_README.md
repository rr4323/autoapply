# Python Concepts — a running reference, built alongside AgentOS

Same idea as [../go_concepts/](../go_concepts/00_README.md), for the Python agent fleet side (`backend/agents/`). Built **just-in-time** as the build steps in `docs/BACKEND_BUILD_STEPS.md` need each idea — nothing here is front-loaded. Every snippet is run and verified before being written down.

## Index (learning order)

| # | File | Concept | First needed in |
|---|---|---|---|
| 1 | [01_pydantic_basics.md](01_pydantic_basics.md) | `pydantic.BaseModel`, automatic validation, JSON round-trip | Step 4 |
| 2 | [02_asyncio_basics.md](02_asyncio_basics.md) | `async`/`await`, the cooperative event loop, `asyncio.gather` | Step 6 |
| 3 | [03_redis_streams_consumer_groups.md](03_redis_streams_consumer_groups.md) | `xgroup_create`, `xreadgroup`, `xpending`, `xautoclaim`, `xack` | Step 6 |
| 4 | [04_fakeredis_testing.md](04_fakeredis_testing.md) | `fakeredis` — Python's protocol fake, same idea as Go's `miniredis` | Step 6 |
| 5 | [05_cooperative_shutdown.md](05_cooperative_shutdown.md) | `asyncio.Event` — Python's counterpart to Go's `context.Done()` | Step 6 |
| 6 | [06_abstract_base_classes.md](06_abstract_base_classes.md) | `abc.ABC`/`@abstractmethod` — explicit contracts vs. Go's implicit interfaces | Step 6 |
| 7 | [07_callable_dependency_injection.md](07_callable_dependency_injection.md) | a `Callable` default parameter — the lightweight alternative to `ABC` for single-function dependencies | Step 18 |
| 8 | [08_async_http_streaming_and_mocking.md](08_async_http_streaming_and_mocking.md) | `httpx.AsyncClient.stream` + `respx` — streamed size caps, transport-level mocking | Step 19 |
| 9 | [09_strenum_field_types.md](09_strenum_field_types.md) | `enum.StrEnum` — a closed, typo-safe set of string values, Python's counterpart to sqlc's generated Go enums | Step 20 |
| 10 | [10_asyncpg_and_python_testcontainers.md](10_asyncpg_and_python_testcontainers.md) | `asyncpg` (Python's `pgx`) + Python `testcontainers` — real-Postgres-backed tests, not just `fakeredis` | Step 21 |
| 11 | [11_typeadapter_validating_a_bare_list.md](11_typeadapter_validating_a_bare_list.md) | `pydantic.TypeAdapter` — validating a bare JSON list, not a single `BaseModel` | Step 23 |
| 12 | [12_retry_with_injectable_sleep.md](12_retry_with_injectable_sleep.md) | Retry-with-backoff tested instantly via an injectable `sleep` — Callable DI and ABC used together, each where it fits | Step 24 |
| 13 | [13_conftest_and_pgvector_text_format.md](13_conftest_and_pgvector_text_format.md) | `conftest.py` fixture sharing across test files; pgvector's text input format (no `numpy` dependency needed) | Step 25 |
| 14 | [14_testing_vector_ranking_without_a_real_model.md](14_testing_vector_ranking_without_a_real_model.md) | Testing pgvector cosine-similarity ranking with a deterministic bag-of-words fake, not a real embedding model | Step 26 |
| 15 | [15_testing_a_trust_boundary_with_respx_callback.md](15_testing_a_trust_boundary_with_respx_callback.md) | `respx`'s callback `side_effect` to capture and assert on the actual outgoing request — testing a prompt-injection defense | Step 28 |
| 16 | [16_two_stage_guardrail_and_fail_safe_defaults.md](16_two_stage_guardrail_and_fail_safe_defaults.md) | Two-stage heuristic-then-LLM guardrails, and picking the right fail-safe direction per situation, not one rule for all | Step 36 |
| 17 | [17_testcontainers_nginx_readiness_gotcha.md](17_testcontainers_nginx_readiness_gotcha.md) | Debugging a `testcontainers` hang caused by a readiness probe hardcoded to `/`, not your actual served path | Step 39 |
| 18 | [18_playwright_ephemeral_contexts_and_egress_restriction.md](18_playwright_ephemeral_contexts_and_egress_restriction.md) | Playwright's `Browser`/`BrowserContext` split — ephemeral per-fill isolation and network-level egress restriction via `context.route` | Step 41 |
| 19 | [19_conftest_as_a_plain_importable_module.md](19_conftest_as_a_plain_importable_module.md) | `conftest.py` as a plain importable module (`from conftest import X`) vs. its auto-discovered-fixture role — why `tests.conftest` fails with no `__init__.py` | Step 43 |

## Why Python starts later than Go in this project

`docs/BACKEND_BUILD_STEPS.md` Phase A builds the Go control plane's HTTP skeleton first (Steps 1–3), then the message envelope contract both languages share (Step 4) — so Step 4 is genuinely the first Python code in the whole repo. Everything from here on alternates between the two runtimes as `TDD.md` §3's split requires (Go = control plane, Python = agent fleet), talking only through the message bus.
