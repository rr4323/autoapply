package handlers

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAgentCallback_InvalidJSON(t *testing.T) {
	h := &AgentCallbackHandler{} // Queries/Pool/Engine nil — must never be reached

	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/internal/agent/callback",
		bytes.NewBufferString(`{not valid json`))
	rec := httptest.NewRecorder()

	h.Callback(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestAgentCallback_UnsupportedAction(t *testing.T) {
	h := &AgentCallbackHandler{}

	body := `{"job_id": "b7e6c2b4-3f1a-4c9e-9d2a-1a2b3c4d5e6f", "action": "fill"}`
	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/internal/agent/callback",
		bytes.NewBufferString(body))
	rec := httptest.NewRecorder()

	h.Callback(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestAgentCallback_InvalidJobID(t *testing.T) {
	h := &AgentCallbackHandler{}

	body := `{"job_id": "not-a-uuid", "action": "submit"}`
	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/internal/agent/callback",
		bytes.NewBufferString(body))
	rec := httptest.NewRecorder()

	h.Callback(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}
