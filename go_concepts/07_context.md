# `context.Context`

## What it is

`context.Context` carries **deadlines, cancellation signals, and request-scoped values** across API boundaries. The convention: **every function that does I/O takes a `context.Context` as its first argument**, so the caller — not the callee — decides how long it's willing to wait.

## Verified example

```go
func slowOperation(ctx context.Context) error {
	select {
	case <-time.After(2 * time.Second):
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel() // always release the timer, even on the fast path

	start := time.Now()
	err := slowOperation(ctx)
	fmt.Printf("result after %v: %v\n", time.Since(start).Round(time.Millisecond), err)
}
```
```
$ go run context.go
result after 501ms: context deadline exceeded
```
`slowOperation` "would" take 2 seconds, but `ctx` only budgeted 500ms — it returned after 501ms with `context deadline exceeded`, not 2 full seconds.

## Reading the pieces

- **`context.Background()`** — the root context, used at the very top of a program (or per-request, in an HTTP handler `r.Context()` gives you the request's own context, already wired to cancel if the client disconnects).
- **`context.WithTimeout(parent, duration)`** — returns a derived context that auto-cancels after `duration`, plus a `cancel func()` you must call (usually via `defer cancel()`) to release the underlying timer even if the operation finishes early.
- **`ctx.Done()`** — a channel that closes when the context is cancelled or times out; a `select` on it alongside your real work is the standard way to make any operation cancellable.
- **`ctx.Err()`** — `nil` normally, otherwise `context.DeadlineExceeded` or `context.Canceled`.

## A second cancellation source: OS signals, not just timers

Verified in `backend/api/cmd/api/main.go`:
```go
stopCtx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
defer stop()
<-stopCtx.Done()
```
Same `Done()`/cancellation mechanism as `WithTimeout` above, but the thing causing cancellation is an **OS signal** (Ctrl+C → `os.Interrupt`/SIGINT, or `docker stop`/`kill` → `SIGTERM`) instead of a clock. `<-stopCtx.Done()` — a bare receive with nothing assigned — is idiomatic Go for "block here until this channel produces something; I only care that it did." This is the actual mechanism behind graceful shutdown: `main()` parks on this line doing nothing while a goroutine serves requests, and the moment a shutdown signal arrives, execution falls through to `srv.Shutdown(...)`.

`defer stop()` here is attached to `main()` itself, so it doesn't fire the instant `Done()` unblocks — it fires when `main()` finally returns, after shutdown cleanup finishes. It releases the signal registration so this process reverts to default OS signal handling once it's done needing to intercept SIGTERM/SIGINT.

## A third use: carrying request-scoped values, not just cancellation

Verified in `backend/api/internal/middleware/usercontext.go`:
```go
type contextKey string

const userIDContextKey contextKey = "user_id"

func UserContext(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		userID := r.Header.Get("X-Demo-User-ID")
		if userID == "" {
			userID = DefaultStubUserID
		}
		ctx := context.WithValue(r.Context(), userIDContextKey, userID)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func UserIDFromContext(ctx context.Context) (string, bool) {
	id, ok := ctx.Value(userIDContextKey).(string)
	return id, ok
}
```
`context.WithValue(parent, key, value)` attaches a value to a derived context, retrievable later via `ctx.Value(key)`. This is how a middleware hands data to every handler further down the chain without a shared global or threading an extra parameter through every function signature.

**Why `type contextKey string` and not a bare string key**: verified —
```go
ctx := context.WithValue(ctx, userIDKey, "user-123")           // userIDKey is type contextKey
ctxOther := context.WithValue(ctx2, otherContextKey("user_id"), "should-not-collide")
// looking up with userIDKey against ctxOther: found=false
```
Go's `context.Value` lookup compares both the key's **type** and its value. Two different named types (`contextKey` vs. some other package's own private key type) never collide even if the underlying string happens to be identical — this is exactly what stops one package's context key from accidentally shadowing another's in a large codebase. A bare `"user_id"` string key wouldn't have this protection.

## Standard use case

- `/readyz` pings Postgres and Redis each with `context.WithTimeout(r.Context(), 2*time.Second)` — a hung DB connection can't hang the health check forever.
- Graceful shutdown (`http.Server.Shutdown(ctx)`) uses a context to bound how long in-flight requests get to finish before the process exits.
- `UserContext`/`UserIDFromContext` (above) is Phase 1's entire auth stand-in — real session/JWT auth later only needs to change what populates the context, since every handler already reads identity from it rather than from a header directly.
- Every `pgxpool` query and every LLM API call anywhere in the Python/Go split ultimately traces back to this same pattern — it's also literally how `trace_id` propagation (`TDD.md` §4.1, §11.1) rides through the system: context values carry it hop to hop.
