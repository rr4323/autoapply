package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func okHandler(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
}

func TestInternalAuth_ValidSecret(t *testing.T) {
	handler := InternalAuth("correct-secret")(http.HandlerFunc(okHandler))
	rec := httptest.NewRecorder()
	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/internal/ping", nil)
	req.Header.Set("X-Internal-Secret", "correct-secret")

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 with valid secret, got %d", rec.Code)
	}
}

func TestInternalAuth_InvalidSecret(t *testing.T) {
	handler := InternalAuth("correct-secret")(http.HandlerFunc(okHandler))
	rec := httptest.NewRecorder()
	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/internal/ping", nil)
	req.Header.Set("X-Internal-Secret", "wrong-secret")

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 with invalid secret, got %d", rec.Code)
	}
}

func TestInternalAuth_MissingSecret(t *testing.T) {
	handler := InternalAuth("correct-secret")(http.HandlerFunc(okHandler))
	rec := httptest.NewRecorder()
	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/internal/ping", nil)
	// no X-Internal-Secret header at all

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 with missing secret, got %d", rec.Code)
	}
}
