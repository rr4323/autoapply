# Testable Interfaces — "Accept Interfaces, Return Structs"

## What it is

A design idiom, not a language feature: **define the smallest interface your code actually needs, at the point where you use it** — don't depend on a concrete external type (like `*pgxpool.Pool`) directly if a narrow interface would do. This is what makes unit tests possible without spinning up real infrastructure.

## Verified example

```go
// Pinger is a narrow interface — only what a health check actually needs.
// We define this ourselves; it's not something the pgx/redis libraries hand us.
type Pinger interface {
	Ping(ctx context.Context) error
}

// realDB stands in for *pgxpool.Pool, which already has a
// Ping(ctx context.Context) error method — so it satisfies Pinger for free,
// with no adapter code needed.
type realDB struct{}

func (realDB) Ping(ctx context.Context) error { return nil }

// fakeDB is what a UNIT TEST uses instead of a real database — no network
// call, no docker container required, fully controlled.
type fakeDB struct{ err error }

func (f fakeDB) Ping(ctx context.Context) error { return f.err }

// checkReady only knows about Pinger — it has no idea whether it's
// talking to a real database or a test double.
func checkReady(ctx context.Context, db Pinger) string {
	if err := db.Ping(ctx); err != nil {
		return "not ready: " + err.Error()
	}
	return "ready"
}
```
```
$ go run pinger.go
ready
not ready: connection refused
```

## Why this matters here specifically

`checkReady` never imports `pgx` or `redis` — it only knows about `Pinger`, which we defined ourselves. That means:
- **In production**, pass it the real `*pgxpool.Pool` — it already has a `Ping(ctx) error` method, so it satisfies `Pinger` automatically, zero glue code.
- **In a unit test**, pass it `fakeDB{err: someError}` and assert the handler returns `503` — no real Postgres container, no `testcontainers`, runs in milliseconds.

This is exactly what `docs/BACKEND_BUILD_STEPS.md` Step 3's test requirement — *"Unit: ready-fails-when-dep-down"* — means concretely: the test never touches a real database at all.

## Standard use case

Anywhere a unit test needs to force a failure path that's hard or slow to trigger for real: a DB connection drop, a Redis timeout, an LLM API error. Define the interface at the narrowest point that needs it (next to the function that uses it, not in some central `interfaces.go` file), and both the real implementation and the test double satisfy it automatically — that's structural typing ([04_interfaces.md](04_interfaces.md)) doing the actual work.

## Correction from real code: "satisfies for free" isn't guaranteed

Building the real `backend/api` health check (Step 3) turned up the case this file's demo glossed over: `*pgxpool.Pool` happens to have `Ping(ctx context.Context) error` — an exact signature match, so it satisfies `Pinger` automatically. `*redis.Client` does **not** — go-redis's `Ping` returns `*redis.StatusCmd`, not a bare `error`. Structural typing only works when the method signature matches *exactly* (name, params, return types); a near-match doesn't count.

The fix is a **one-method adapter struct**, still tiny, still local to where it's used:
```go
// redisPinger adapts *redis.Client to health.Pinger. go-redis's Ping
// returns *redis.StatusCmd, not a bare error, so a thin wrapper is needed
// here, unlike *pgxpool.Pool which matches the interface shape exactly.
type redisPinger struct {
	client *redis.Client
}

func (p redisPinger) Ping(ctx context.Context) error {
	return p.client.Ping(ctx).Err()
}
```
Verified: `backend/api/cmd/api/main.go` passes `redisPinger{redisClient}` (not `redisClient` directly) to `health.NewChecker`. This isn't a failure of the pattern — needing a small adapter when an external library's method shape doesn't line up exactly is normal and common; the interface stays narrow and the adapter stays one method, so it's still cheap.
