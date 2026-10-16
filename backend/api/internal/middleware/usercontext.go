// Package middleware holds the two HTTP middlewares from
// docs/BACKEND_BUILD_STEPS.md Step 14: a stub user-identity injector for
// the public API surface, and shared-secret protection for /internal/*.
package middleware

import (
	"context"
	"net/http"
)

type contextKey string

const userIDContextKey contextKey = "user_id"

// DefaultStubUserID stands in for real auth (TDD.md §16 — SSO/session
// auth is an explicit blind spot until Phase 3; Phase 1 is single-user).
// Swapping this middleware for real session/JWT auth later is the only
// place that needs to change — handlers only ever read from context.
const DefaultStubUserID = "00000000-0000-0000-0000-000000000001"

// UserContext injects a user id into the request context: the value of
// X-Demo-User-ID if present, otherwise DefaultStubUserID.
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

// UserIDFromContext reads back what UserContext injected.
func UserIDFromContext(ctx context.Context) (string, bool) {
	id, ok := ctx.Value(userIDContextKey).(string)
	return id, ok
}
