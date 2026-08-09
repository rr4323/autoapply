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

## Why Python starts later than Go in this project

`docs/BACKEND_BUILD_STEPS.md` Phase A builds the Go control plane's HTTP skeleton first (Steps 1–3), then the message envelope contract both languages share (Step 4) — so Step 4 is genuinely the first Python code in the whole repo. Everything from here on alternates between the two runtimes as `TDD.md` §3's split requires (Go = control plane, Python = agent fleet), talking only through the message bus.
