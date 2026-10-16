package handlers

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestProfilePut_InvalidJSON(t *testing.T) {
	h := &ProfileHandler{} // Queries is nil — must never be reached
	handler := withUserContext(h.Put)

	req := httptest.NewRequestWithContext(context.Background(), http.MethodPut, "/api/v1/profile",
		bytes.NewBufferString(`{not valid json`))
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestProfilePut_MissingUserContext(t *testing.T) {
	h := &ProfileHandler{}
	// deliberately NOT wrapped with UserContext middleware

	req := httptest.NewRequestWithContext(context.Background(), http.MethodPut, "/api/v1/profile",
		bytes.NewBufferString(`{"skills": ["Go"]}`))
	rec := httptest.NewRecorder()

	h.Put(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 with no user context, got %d", rec.Code)
	}
}

func TestProfileGet_MissingUserContext(t *testing.T) {
	h := &ProfileHandler{}

	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/api/v1/profile", nil)
	rec := httptest.NewRecorder()

	h.Get(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 with no user context, got %d", rec.Code)
	}
}
