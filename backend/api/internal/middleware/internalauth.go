package middleware

import (
	"crypto/subtle"
	"net/http"
)

// InternalAuth guards /internal/* endpoints with a shared secret (TDD.md
// §14 — service-to-service only, never reachable from the public API
// surface). A static shared secret, not JWT/mTLS, is enough for Phase 1's
// deployment shape; upgrading this is a named, deliberate future step,
// not something quietly deferred.
func InternalAuth(secret string) func(http.Handler) http.Handler {
	secretBytes := []byte(secret)

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			provided := r.Header.Get("X-Internal-Secret")

			// subtle.ConstantTimeCompare avoids a timing side-channel that
			// a plain "==" string comparison would leak (it returns as soon
			// as the first differing byte is found, so mismatch position is
			// observable via response latency).
			if provided == "" || subtle.ConstantTimeCompare([]byte(provided), secretBytes) != 1 {
				http.Error(w, "unauthorized", http.StatusUnauthorized)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}
