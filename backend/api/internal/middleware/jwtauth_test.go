package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/rr4323/autoapply/backend/api/internal/auth"
)

func TestJWTAuth_ValidTokenSetsUserContext(t *testing.T) {
	secret := []byte("test-secret")
	token, err := auth.IssueToken(secret, "user-123", time.Hour)
	if err != nil {
		t.Fatalf("IssueToken failed: %v", err)
	}

	handler := JWTAuth(secret)(http.HandlerFunc(echoUserIDHandler))
	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/whoami", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	if rec.Body.String() != "user-123" {
		t.Fatalf("expected user-123, got %q", rec.Body.String())
	}
}

func TestJWTAuth_MissingHeaderIsUnauthorized(t *testing.T) {
	handler := JWTAuth([]byte("test-secret"))(http.HandlerFunc(echoUserIDHandler))
	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/whoami", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
}

func TestJWTAuth_InvalidTokenIsUnauthorized(t *testing.T) {
	handler := JWTAuth([]byte("test-secret"))(http.HandlerFunc(echoUserIDHandler))
	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/whoami", nil)
	req.Header.Set("Authorization", "Bearer not-a-real-token")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
}

func TestJWTAuth_WrongSecretIsUnauthorized(t *testing.T) {
	token, err := auth.IssueToken([]byte("secret-a"), "user-123", time.Hour)
	if err != nil {
		t.Fatalf("IssueToken failed: %v", err)
	}

	handler := JWTAuth([]byte("secret-b"))(http.HandlerFunc(echoUserIDHandler))
	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/whoami", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
}
