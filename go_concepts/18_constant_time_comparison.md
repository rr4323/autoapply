# Constant-Time Comparison — `crypto/subtle`

## What it is

Comparing secrets (API keys, shared secrets, HMAC signatures) with a plain `==` leaks timing information: string comparison returns as soon as it finds the first differing byte, so a wrong guess that matches more leading characters takes measurably longer to reject. Repeated over enough requests, that timing difference is enough to reconstruct a secret byte-by-byte — a real, exploitable attack class, not a theoretical one. `crypto/subtle.ConstantTimeCompare` always examines every byte, taking the same time regardless of where (or whether) a mismatch occurs.

## Verified example (from `backend/api/internal/middleware/internalauth.go`)

```go
func InternalAuth(secret string) func(http.Handler) http.Handler {
	secretBytes := []byte(secret)

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			provided := r.Header.Get("X-Internal-Secret")

			if provided == "" || subtle.ConstantTimeCompare([]byte(provided), secretBytes) != 1 {
				http.Error(w, "unauthorized", http.StatusUnauthorized)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}
```
Confirmed via the middleware's own tests: valid secret → `200`, invalid secret → `401`, missing header entirely → `401` — same as a naive `==` check would produce, just without the timing leak.

## Reading the pieces

- **`subtle.ConstantTimeCompare(a, b []byte) int`** — returns `1` if equal, `0` otherwise. Note it's an `int`, not a `bool` — easy to accidentally write `if subtle.ConstantTimeCompare(...) {` and get a compile error, or worse, `if subtle.ConstantTimeCompare(...) == 0 {` inverted by mistake. Always compare explicitly against `1` or `0`.
- **The `provided == ""` short-circuit is fine** — an empty string is never a valid secret, so this isn't a secret-dependent branch; it's a length gate that's the same for every attacker.
- **This function does NOT handle different-length inputs specially in a secure way on its own** — reading Go's docs: if the two slices have different lengths, it returns `0` immediately, which is itself technically a (cheap, low-information) timing signal in adversarial contexts. Fine for this use case (an internal shared secret, not a public-facing password endpoint) — worth knowing as a limit, not a flaw in what's built here.

## Standard use case

Any place a secret gets compared against user/caller-supplied input: API keys, webhook signature verification (HMAC comparison), shared-secret service-to-service auth like `/internal/*` here. Never reach for `==` on a secret comparison once the value came from outside the process.
