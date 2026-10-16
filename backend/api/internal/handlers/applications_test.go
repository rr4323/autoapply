package handlers

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"

	"github.com/rr4323/autoapply/backend/api/internal/middleware"
)

// withUserContext wraps a handler with the real UserContext middleware so
// tests exercise the same context-injection path production traffic does.
func withUserContext(h http.HandlerFunc) http.Handler {
	return middleware.UserContext(h)
}

func TestCreate_InvalidJSON(t *testing.T) {
	h := &ApplicationsHandler{} // Queries is nil — this test must never reach it
	handler := withUserContext(h.Create)

	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/api/v1/applications",
		bytes.NewBufferString(`{not valid json`))
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestCreate_BothFieldsPresent(t *testing.T) {
	h := &ApplicationsHandler{}
	handler := withUserContext(h.Create)

	body := `{"jd_url": "https://boards.greenhouse.io/x/jobs/1", "jd_text": "some text"}`
	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/api/v1/applications",
		bytes.NewBufferString(body))
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 when both jd_url and jd_text present, got %d", rec.Code)
	}
}

func TestCreate_NeitherFieldPresent(t *testing.T) {
	h := &ApplicationsHandler{}
	handler := withUserContext(h.Create)

	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/api/v1/applications",
		bytes.NewBufferString(`{}`))
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 when neither jd_url nor jd_text present, got %d", rec.Code)
	}
}

func TestCreate_MissingUserContext(t *testing.T) {
	h := &ApplicationsHandler{}
	// deliberately NOT wrapped with UserContext middleware

	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/api/v1/applications",
		bytes.NewBufferString(`{"jd_url": "https://boards.greenhouse.io/x/jobs/1"}`))
	rec := httptest.NewRecorder()

	h.Create(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 with no user context, got %d", rec.Code)
	}
}

func TestGet_InvalidID(t *testing.T) {
	h := &ApplicationsHandler{} // must never reach Queries — id fails to parse first
	handler := withUserContext(h.Get)

	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/api/v1/applications/not-a-uuid", nil)
	// chi.URLParam needs real routing context to resolve "{id}" — simulate
	// what chi's router sets up, so this genuinely tests "not-a-uuid"
	// failing to parse, not just an empty/unresolved param.
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("id", "not-a-uuid")
	req = req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for a non-UUID id, got %d", rec.Code)
	}
}

func TestConfirmSubmit_InvalidID(t *testing.T) {
	h := &ApplicationsHandler{} // must never reach Queries/Pool — id fails to parse first
	handler := withUserContext(h.ConfirmSubmit)

	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost,
		"/api/v1/applications/not-a-uuid/confirm-submit", nil)
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("id", "not-a-uuid")
	req = req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for a non-UUID id, got %d", rec.Code)
	}
}

func TestConfirmSubmit_MissingUserContext(t *testing.T) {
	h := &ApplicationsHandler{}
	// deliberately NOT wrapped with UserContext middleware

	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost,
		"/api/v1/applications/00000000-0000-0000-0000-000000000001/confirm-submit", nil)
	rec := httptest.NewRecorder()

	h.ConfirmSubmit(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 with no user context, got %d", rec.Code)
	}
}
