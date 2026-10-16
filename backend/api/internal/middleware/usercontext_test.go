package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func echoUserIDHandler(w http.ResponseWriter, r *http.Request) {
	id, ok := UserIDFromContext(r.Context())
	if !ok {
		http.Error(w, "no user id in context", http.StatusInternalServerError)
		return
	}
	_, _ = w.Write([]byte(id))
}

func TestUserContext_DefaultsWhenHeaderMissing(t *testing.T) {
	handler := UserContext(http.HandlerFunc(echoUserIDHandler))
	rec := httptest.NewRecorder()
	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/whoami", nil)

	handler.ServeHTTP(rec, req)

	if rec.Body.String() != DefaultStubUserID {
		t.Fatalf("expected default stub id %q, got %q", DefaultStubUserID, rec.Body.String())
	}
}

func TestUserContext_HonorsOverrideHeader(t *testing.T) {
	handler := UserContext(http.HandlerFunc(echoUserIDHandler))
	rec := httptest.NewRecorder()
	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/whoami", nil)
	req.Header.Set("X-Demo-User-ID", "some-other-user")

	handler.ServeHTTP(rec, req)

	if rec.Body.String() != "some-other-user" {
		t.Fatalf("expected overridden id, got %q", rec.Body.String())
	}
}

func TestUserIDFromContext_AbsentWhenMiddlewareNotApplied(t *testing.T) {
	_, ok := UserIDFromContext(context.Background())
	if ok {
		t.Fatal("expected no user id in a plain context")
	}
}
