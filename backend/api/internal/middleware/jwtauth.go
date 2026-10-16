package middleware

import (
	"context"
	"net/http"
	"strings"

	"github.com/rr4323/autoapply/backend/api/internal/auth"
)

// JWTAuth is P1 of the SaaS pivot: it replaces UserContext (the Phase 1
// stub) on the real public API. It reads "Authorization: Bearer <token>",
// verifies it, and injects the subject into the same context key
// UserContext used — UserIDFromContext and every handler that calls it
// (docs/BACKEND_BUILD_STEPS.md Step 14's design intent) don't change at
// all. UserContext itself is left in place, still used by the existing
// handler test suites' setupTestRouter helpers.
func JWTAuth(secret []byte) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			header := r.Header.Get("Authorization")
			tokenString, ok := strings.CutPrefix(header, "Bearer ")
			if !ok || tokenString == "" {
				writeUnauthorized(w)
				return
			}

			userID, err := auth.ParseToken(secret, tokenString)
			if err != nil {
				writeUnauthorized(w)
				return
			}

			ctx := context.WithValue(r.Context(), userIDContextKey, userID)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func writeUnauthorized(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusUnauthorized)
	_, _ = w.Write([]byte(`{"error":{"code":"unauthorized","message":"missing or invalid bearer token"}}`))
}
