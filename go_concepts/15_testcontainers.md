# `testcontainers-go` — Real Infrastructure for Integration Tests

## What it is

A library that starts real Docker containers from Go test code and tears them down afterward — the integration-test-tier equivalent of [13_testing_with_fake_servers.md](13_testing_with_fake_servers.md)'s `miniredis`, but a genuine container instead of an in-memory protocol implementation. `docs/IMPLEMENTATION_PLAN.md` §0 names it explicitly for this tier: *"testcontainers-go (real Postgres/Redis in CI)."*

## Verified example

```go
container, err := tcredis.Run(ctx, "redis:7-alpine")
// ...
t.Cleanup(func() { _ = container.Terminate(context.Background()) })

addr, err := container.PortEndpoint(ctx, "6379/tcp", "")
// addr is a bare "host:port" string — pass "" as the proto argument to
// skip the "redis://" scheme prefix, since redis.Options{Addr: ...} wants
// a bare address, not a URI.

client := redis.NewClient(&redis.Options{Addr: addr})
```
Real output from the actual run:
```
🐳 Creating container for image redis:7-alpine
✅ Container created: df4458d233cb
🐳 Starting container: df4458d233cb
⏳ Waiting for container id ... Waiting for: all of: [port 6379/tcp to be listening, log message "* Ready to accept connections"]
🔔 Container is ready: df4458d233cb
--- PASS: TestRoundTrip_GoPublishesPythonConsumes (7.73s)
🐳 Terminating container: df4458d233cb
```

## Reading the pieces

- **`tcredis.Run(ctx, image)`** — starts the container, blocks until its readiness check passes (here: port open *and* the "Ready to accept connections" log line — both, not just one), returns a handle.
- **`container.PortEndpoint(ctx, "6379/tcp", "")`** — Docker maps the container's internal port to some *dynamically chosen* port on the host (so multiple test runs, or parallel CI jobs, never collide on a fixed port like `6379`). This method resolves the actual mapped host:port for you rather than you having to guess or hardcode it.
- **`t.Cleanup(func() { container.Terminate(...) })`** — guarantees the container is torn down even if the test fails partway through, same `t.Cleanup` pattern as [10_testing_http_handlers.md](10_testing_http_handlers.md) and the `miniredis` examples.
- **`ryuk`** (visible in the log output as a second container) — testcontainers' own cleanup sidecar, a safety net that kills orphaned containers if a test process crashes before its own `Terminate` call runs.

## Why not just point at the existing `docker-compose` Redis?

Because a test that reuses a long-running dev-environment container isn't isolated — leftover keys from a previous run, or another test running concurrently against the same instance, can make results depend on execution order. A fresh container per test run means the round-trip test starts from a genuinely empty Redis every time, which is exactly why it worked correctly on the very first run with no manual `FLUSHALL` needed first.

## Standard use case

Any integration test in `docs/BACKEND_BUILD_STEPS.md` needing "real Postgres/Redis" per the testing philosophy — this is the mechanism, not just a name in a table. The round-trip test (Step 7) is the first real use; later steps (M1's Postgres CRUD integration tests, for instance) will reach for the Postgres variant the same way.
