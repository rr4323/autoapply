# Go Concepts — a running reference, built alongside AgentOS

This directory is a personal Go reference, one file per concept, built up **just-in-time** as the `backend/api` build steps (`docs/BACKEND_BUILD_STEPS.md`) actually need each idea — not a front-loaded tutorial. Every code snippet in here has been run and its output verified before being written down; nothing is copy-pasted from memory.

**How to use this:**
- Read a file when the concept first comes up in a build step, or whenever you want to refresh it.
- Copy any snippet into a scratch `.go` file and `go run` it — none of these need external dependencies unless the file says so.
- New files get added as later steps introduce new ideas (goroutines/channels, JSON encoding, table-driven tests, generics, etc.) — this list grows with the project, it isn't fixed.

## Index (learning order)

| # | File | Concept | First needed in |
|---|---|---|---|
| 1 | [01_modules_and_gomod.md](01_modules_and_gomod.md) | `go.mod`, module paths, `go.sum`, `go get` | Step 1 |
| 2 | [02_packages_and_imports.md](02_packages_and_imports.md) | packages, `package main`, `internal/`, unused imports | Step 1 |
| 3 | [03_structs_and_methods.md](03_structs_and_methods.md) | structs, receiver methods | Step 3 |
| 4 | [04_interfaces.md](04_interfaces.md) | structural typing, small-interface idiom | Step 3 |
| 5 | [05_error_handling.md](05_error_handling.md) | multiple return values, `if err != nil` | Step 1 |
| 6 | [06_nethttp_basics.md](06_nethttp_basics.md) | `http.Handler`, `HandleFunc`, request/response shape | Step 3 |
| 7 | [07_context.md](07_context.md) | `context.Context`, timeouts, cancellation | Step 3 |
| 8 | [08_testable_interfaces.md](08_testable_interfaces.md) | "accept interfaces, return structs" — the `Pinger` pattern | Step 3 |
| 9 | [09_build_run_test.md](09_build_run_test.md) | `go run` vs `go build` vs `go test` vs `go install` | Step 1 |
| 10 | [10_testing_http_handlers.md](10_testing_http_handlers.md) | `httptest.NewRecorder`/`NewRequestWithContext` — testing handlers without a real server | Step 3 |
| 11 | [11_json_marshaling.md](11_json_marshaling.md) | `encoding/json`, struct tags, no built-in "required" | Step 4 |
| 12 | [12_redis_streams_basics.md](12_redis_streams_basics.md) | `XADD`/`XRANGE` via go-redis | Step 5 |
| 13 | [13_testing_with_fake_servers.md](13_testing_with_fake_servers.md) | interface fakes vs. protocol fakes (`miniredis`) | Step 5 |
| 14 | [14_build_tags.md](14_build_tags.md) | `//go:build` — excluding integration tests from the default build | Step 7 |
| 15 | [15_testcontainers.md](15_testcontainers.md) | `testcontainers-go` — real Docker containers for integration tests | Step 7 |
| 16 | [16_exec_command.md](16_exec_command.md) | `os/exec` — launching and verifying a subprocess (across languages) | Step 7 |

## Where each concept actually lands in AgentOS

Not abstract exercises — every one of these is load-bearing somewhere in `docs/TDD.md`:
- **Interfaces + testable interfaces (4, 8)**: the Policy Engine (`TDD.md` §7) needs to be unit-tested against every rule branch without a real database — same `Pinger`-style pattern, bigger stakes.
- **Context (7)**: every DB query, every HTTP call to an LLM provider, every Redis operation in the whole backend takes a `context.Context` — it's not optional plumbing, it's how timeouts and graceful shutdown propagate everywhere.
- **Error handling (5)**: the Policy Engine's `reasons` array (§7.2) and the adversarial "Go wins" enforcement boundary (§7.3) both depend on errors being handled explicitly and audibly, never silently swallowed.
- **Structs (3)**: your `Config`, `Decision`, `Application` types — basically every piece of data moving through the Go control plane.
