# Testing HTTP Handlers — `net/http/httptest`

## What it is

`net/http/httptest` lets you call an `http.Handler` function directly in a test — no real network socket, no real server listening on a port. You build a fake request and a fake response recorder, call the handler like a normal function, then inspect what it wrote.

## Verified example (from `backend/api/internal/health/health_test.go`)

```go
func TestReadyz_DBDown(t *testing.T) {
	c := NewChecker(fakePinger{err: errors.New("connection refused")}, fakePinger{})
	rec := httptest.NewRecorder()
	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/readyz", nil)

	c.Readyz(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d", rec.Code)
	}
}
```
```
$ go test ./internal/health/... -v
--- PASS: TestReadyz_AllHealthy (0.00s)
--- PASS: TestReadyz_DBDown (0.00s)
--- PASS: TestReadyz_RedisDown (0.00s)
--- PASS: TestHealthz_AlwaysOK (0.00s)
```

## The two pieces

- **`httptest.NewRecorder()`** — an in-memory stand-in for `http.ResponseWriter`. After the handler runs, `rec.Code` is the status code it wrote, `rec.Body` is what it wrote as the response body.
- **`httptest.NewRequestWithContext(ctx, method, target, body)`** — builds a fake `*http.Request`. Note this is `NewRequestWithContext`, not the older `NewRequest` — `golangci-lint`'s `noctx` linter (in our `.golangci.yml`) flags `NewRequest` specifically because it silently uses `context.Background()` internally; being explicit about the context is the same "every I/O-touching thing takes a context" discipline from [07_context.md](07_context.md), just applied to test setup too.

Because `c.Readyz` is just a plain function with the `func(w http.ResponseWriter, r *http.Request)` signature ([06_nethttp_basics.md](06_nethttp_basics.md)), calling `c.Readyz(rec, req)` directly in a test works exactly the same as a real router dispatching a real request to it — no server startup/teardown needed for a unit test.

## Standard use case

Every handler in the Go control plane (`POST /api/applications`, `GET /api/applications/:id`, the Policy Engine's internal callback endpoint, all of it) gets this same test shape: build a request, build a recorder, call the handler, assert on `rec.Code`/`rec.Body`. Combined with the `Pinger`-style fake-dependency pattern ([08_testable_interfaces.md](08_testable_interfaces.md)), this is how the whole API surface stays unit-testable without a real Postgres/Redis for every single test — those are saved for the integration-test layer (`testcontainers-go`), which is deliberately a separate, slower tier.

## A gap this pattern doesn't cover on its own: `chi.URLParam`

Calling a handler directly (`h.Get(rec, req)`) skips chi's router entirely — so `chi.URLParam(r, "id")` returns `""`, not whatever was in the URL path, because there's no chi routing context on the request at all. Verified: a test built exactly like the pattern above, hitting `/api/v1/applications/not-a-uuid`, still got `""` back from `chi.URLParam` — it happened to still produce the right test outcome (an empty string also fails UUID parsing), but for the wrong reason, silently testing something other than what the test claimed.

Fix — build the routing context by hand, the same way chi's router would:
```go
req := httptest.NewRequestWithContext(ctx, http.MethodGet, "/api/v1/applications/not-a-uuid", nil)
rctx := chi.NewRouteContext()
rctx.URLParams.Add("id", "not-a-uuid")
req = req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))
```
Now `chi.URLParam(r, "id")` genuinely resolves to `"not-a-uuid"`, and the test proves what it claims to.

**When you actually need this**: only when testing a handler *directly* with a route parameter it reads via `chi.URLParam`. Tests that go through the real router (`router.ServeHTTP(rec, req)` — see `internal/handlers/applications_integration_test.go`) don't need this at all, since the real router populates the routing context itself as part of matching the request.
