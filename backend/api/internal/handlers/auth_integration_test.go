//go:build integration

// Signup/login round trip against a real Postgres container — P1 of the
// SaaS pivot plan. Reuses setupTestRouter's Postgres+migrations setup
// (applications_integration_test.go) purely for its *store.Queries; the
// handlers are exercised directly since neither takes a path param.
package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

var testJWTSecret = []byte("integration-test-secret")

func doAuthRequest(h http.HandlerFunc, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/api/v1/auth/x", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	h(rec, req)
	return rec
}

func TestAuthAPI_SignupThenLoginRoundTrip(t *testing.T) {
	_, queries, _, _ := setupTestRouter(t)
	authHandler := NewAuthHandler(queries, testJWTSecret)

	signupRec := doAuthRequest(authHandler.Signup, `{"email":"new-user@example.com","password":"correct-horse-battery"}`)
	if signupRec.Code != http.StatusOK {
		t.Fatalf("expected 200 on signup, got %d: %s", signupRec.Code, signupRec.Body.String())
	}
	var signupResp authResponse
	if err := json.Unmarshal(signupRec.Body.Bytes(), &signupResp); err != nil {
		t.Fatalf("failed to decode signup response: %v", err)
	}
	if signupResp.Token == "" || signupResp.UserID == "" {
		t.Fatalf("expected token and user_id in signup response, got %+v", signupResp)
	}

	loginRec := doAuthRequest(authHandler.Login, `{"email":"new-user@example.com","password":"correct-horse-battery"}`)
	if loginRec.Code != http.StatusOK {
		t.Fatalf("expected 200 on login, got %d: %s", loginRec.Code, loginRec.Body.String())
	}
	var loginResp authResponse
	if err := json.Unmarshal(loginRec.Body.Bytes(), &loginResp); err != nil {
		t.Fatalf("failed to decode login response: %v", err)
	}
	if loginResp.UserID != signupResp.UserID {
		t.Fatalf("expected same user id from login, got signup=%s login=%s", signupResp.UserID, loginResp.UserID)
	}
}

func TestAuthAPI_SignupRejectsDuplicateEmail(t *testing.T) {
	_, queries, _, _ := setupTestRouter(t)
	authHandler := NewAuthHandler(queries, testJWTSecret)

	first := doAuthRequest(authHandler.Signup, `{"email":"dupe@example.com","password":"correct-horse-battery"}`)
	if first.Code != http.StatusOK {
		t.Fatalf("expected 200 on first signup, got %d: %s", first.Code, first.Body.String())
	}

	second := doAuthRequest(authHandler.Signup, `{"email":"dupe@example.com","password":"another-password"}`)
	if second.Code != http.StatusConflict {
		t.Fatalf("expected 409 on duplicate signup, got %d: %s", second.Code, second.Body.String())
	}
}

func TestAuthAPI_LoginRejectsWrongPassword(t *testing.T) {
	_, queries, _, _ := setupTestRouter(t)
	authHandler := NewAuthHandler(queries, testJWTSecret)

	signup := doAuthRequest(authHandler.Signup, `{"email":"wrongpass@example.com","password":"correct-horse-battery"}`)
	if signup.Code != http.StatusOK {
		t.Fatalf("expected 200 on signup, got %d: %s", signup.Code, signup.Body.String())
	}

	login := doAuthRequest(authHandler.Login, `{"email":"wrongpass@example.com","password":"totally-wrong"}`)
	if login.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 on wrong password, got %d: %s", login.Code, login.Body.String())
	}
}

func TestAuthAPI_LoginRejectsUnknownEmail(t *testing.T) {
	_, queries, _, _ := setupTestRouter(t)
	authHandler := NewAuthHandler(queries, testJWTSecret)

	login := doAuthRequest(authHandler.Login, `{"email":"nobody@example.com","password":"whatever123"}`)
	if login.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for unknown email, got %d: %s", login.Code, login.Body.String())
	}
}

func TestAuthAPI_LoginRejectsUserWithNoPassword(t *testing.T) {
	ctx := context.Background()
	_, queries, _, _ := setupTestRouter(t)
	authHandler := NewAuthHandler(queries, testJWTSecret)

	// CreateUser (used by every other integration test in this package) never
	// sets password_hash — such a user must never be able to log in.
	if _, err := queries.CreateUser(ctx, "no-password@example.com"); err != nil {
		t.Fatalf("failed to create user: %v", err)
	}

	login := doAuthRequest(authHandler.Login, `{"email":"no-password@example.com","password":"anything"}`)
	if login.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for a user with no password set, got %d: %s", login.Code, login.Body.String())
	}
}
