# Closures and the Middleware-Factory Pattern

## What it is

A **closure** is a function value that "remembers" variables from where it was created, even after that outer function has returned. Go middleware (`func(http.Handler) http.Handler`) is closures used for a specific job: wrapping one HTTP handler with extra behavior (auth, logging, ...) around it.

## Built up in three verified steps

**Step A — a function returning a function, with data baked in:**
```go
func adder(n int) func(int) int {
	return func(x int) int {
		return x + n
	}
}
add5 := adder(5)
add5(10) // 15 — the returned function still has n=5, even though adder() already returned
```

**Step B — a function that wraps another function (the decorator shape):**
```go
func withLogging(next func(int) int) func(int) int {
	return func(x int) int {
		fmt.Println("calling with", x)
		return next(x)
	}
}
```

**Step C — combine both, three layers deep — the exact shape of every middleware in this codebase:**
```go
func withPrefix(prefix string) func(func(int) int) func(int) int {
	return func(next func(int) int) func(int) int {
		return func(x int) int {
			fmt.Println(prefix, x)
			return next(x)
		}
	}
}
```
```
shout := withPrefix("SHOUTING:")   // layer 1: bake in config — runs once
loudDouble := shout(double)        // layer 2: wrap a handler — runs once per registration
loudDouble(4)                      // layer 3: the actual call — runs every time
```

## Mapped onto real code (`backend/api/internal/middleware/internalauth.go`)

```go
func InternalAuth(secret string) func(http.Handler) http.Handler {  // layer 1: config
	secretBytes := []byte(secret)

	return func(next http.Handler) http.Handler {                   // layer 2: wrap
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { // layer 3: per-request
			provided := r.Header.Get("X-Internal-Secret")
			if provided == "" || subtle.ConstantTimeCompare([]byte(provided), secretBytes) != 1 {
				http.Error(w, "unauthorized", http.StatusUnauthorized)
				return // stop — next is never called
			}
			next.ServeHTTP(w, r) // hand off to whatever this middleware wraps
		})
	}
}
```

**When each layer actually runs**, in `main.go`'s `r.Use(authmw.InternalAuth(cfg.InternalSharedSecret))`:
1. `InternalAuth(cfg.InternalSharedSecret)` — **once, at startup**. Produces the middleware, with the secret closed over.
2. The returned `func(next http.Handler) http.Handler` — **once per route registration**, when `chi` wires it into the router. Produces the final handler.
3. The innermost `func(w, r)` — **once per incoming HTTP request**. The actual check.

This is *why* it's three layers instead of one function: configuration, wrapping, and per-request execution genuinely happen at three different times, and closures are the mechanism that lets each layer hand its data down to the next without a shared global variable.

## Standard use case

Every middleware in this codebase — `UserContext`, `InternalAuth`, and anything added later (request logging, rate limiting) — follows this same three-layer shape. Recognizing "config → wrap → execute" is the key to reading any of them without getting lost in the nesting.
