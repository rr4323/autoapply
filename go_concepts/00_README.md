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
| 7 | [07_context.md](07_context.md) | `context.Context` — timeouts, OS-signal cancellation, request-scoped values (`WithValue`) | Step 3 / 14 |
| 8 | [08_testable_interfaces.md](08_testable_interfaces.md) | "accept interfaces, return structs" — the `Pinger` pattern | Step 3 |
| 9 | [09_build_run_test.md](09_build_run_test.md) | `go run` vs `go build` vs `go test` vs `go install` | Step 1 |
| 10 | [10_testing_http_handlers.md](10_testing_http_handlers.md) | `httptest.NewRecorder`/`NewRequestWithContext` — testing handlers without a real server | Step 3 |
| 11 | [11_json_marshaling.md](11_json_marshaling.md) | `encoding/json`, struct tags, no built-in "required" | Step 4 |
| 12 | [12_redis_streams_basics.md](12_redis_streams_basics.md) | `XADD`/`XRANGE` via go-redis | Step 5 |
| 13 | [13_testing_with_fake_servers.md](13_testing_with_fake_servers.md) | interface fakes vs. protocol fakes (`miniredis`) | Step 5 |
| 14 | [14_build_tags.md](14_build_tags.md) | `//go:build` — excluding integration tests from the default build | Step 7 |
| 15 | [15_testcontainers.md](15_testcontainers.md) | `testcontainers-go` — real Docker containers for integration tests | Step 7 |
| 16 | [16_exec_command.md](16_exec_command.md) | `os/exec` — launching and verifying a subprocess (across languages) | Step 7 |
| 17 | [17_sqlc_codegen.md](17_sqlc_codegen.md) | `sqlc` — type-safe Go generated from real SQL, no ORM | Step 13 |
| 18 | [18_constant_time_comparison.md](18_constant_time_comparison.md) | `crypto/subtle` — comparing secrets without a timing leak | Step 14 |
| 19 | [19_closures_and_middleware.md](19_closures_and_middleware.md) | closures — the config → wrap → execute middleware-factory pattern | Step 14 |
| 20 | [20_embedded_structs_json.md](20_embedded_structs_json.md) | embedded struct fields flatten in JSON — Go's answer to OpenAPI `allOf` | Step 15 |
| 21 | [21_pgx_custom_enum_arrays.md](21_pgx_custom_enum_arrays.md) | a real bug: `pgx` can't encode `[]CustomEnumType` — cast to `text[]` instead | Step 15 |
| 22 | [22_pgx_transactions_and_sqlc_withtx.md](22_pgx_transactions_and_sqlc_withtx.md) | `pgx.Tx` + sqlc's `WithTx` — and why "same transaction" can't extend to Redis | Step 17 |
| 23 | [23_yaml_config_loading.md](23_yaml_config_loading.md) | `gopkg.in/yaml.v3`, the wrapper-struct trick for a nested top-level key, `*float64` for a YAML `null` | Step 31 |
| 24 | [24_go_side_stream_consumer.md](24_go_side_stream_consumer.md) | A Go-side Redis Streams consumer — `context.Context` cancellation instead of `asyncio.Event`, error-return instead of exception for "don't ack on failure" | Step 32 |
| 25 | [25_password_hashing_bcrypt.md](25_password_hashing_bcrypt.md) | `bcrypt` — salted, deliberately-slow password hashing, `CompareHashAndPassword` vs. `==` | SaaS pivot P1 |
| 26 | [26_jwt_tokens.md](26_jwt_tokens.md) | JWTs — claims, HMAC signing, `ParseWithClaims`'s algorithm-pinning callback | SaaS pivot P1 |
| 27 | [27_errors_as_typed_extraction.md](27_errors_as_typed_extraction.md) | `errors.As` — recovering a concrete typed error (e.g. `*pgconn.PgError`) out of a wrapped chain | SaaS pivot P1 |

## Where each concept actually lands in AgentOS

Not abstract exercises — every one of these is load-bearing somewhere in `docs/TDD.md`:
- **Interfaces + testable interfaces (4, 8)**: the Policy Engine (`TDD.md` §7) needs to be unit-tested against every rule branch without a real database — same `Pinger`-style pattern, bigger stakes.
- **Context (7)**: every DB query, every HTTP call to an LLM provider, every Redis operation in the whole backend takes a `context.Context` — it's not optional plumbing, it's how timeouts and graceful shutdown propagate everywhere.
- **Error handling (5)**: the Policy Engine's `reasons` array (§7.2) and the adversarial "Go wins" enforcement boundary (§7.3) both depend on errors being handled explicitly and audibly, never silently swallowed.
- **Structs (3)**: your `Config`, `Decision`, `Application` types — basically every piece of data moving through the Go control plane.
