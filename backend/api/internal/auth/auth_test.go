package auth

import (
	"testing"
	"time"
)

func TestHashPassword_CheckPassword_RoundTrip(t *testing.T) {
	hash, err := HashPassword("correct horse battery staple")
	if err != nil {
		t.Fatalf("HashPassword failed: %v", err)
	}
	if !CheckPassword(hash, "correct horse battery staple") {
		t.Fatal("expected matching password to check out")
	}
	if CheckPassword(hash, "wrong password") {
		t.Fatal("expected wrong password to fail the check")
	}
}

func TestIssueToken_ParseToken_RoundTrip(t *testing.T) {
	secret := []byte("test-secret")
	token, err := IssueToken(secret, "user-123", time.Hour)
	if err != nil {
		t.Fatalf("IssueToken failed: %v", err)
	}

	userID, err := ParseToken(secret, token)
	if err != nil {
		t.Fatalf("ParseToken failed: %v", err)
	}
	if userID != "user-123" {
		t.Fatalf("expected user-123, got %q", userID)
	}
}

func TestParseToken_RejectsWrongSecret(t *testing.T) {
	token, err := IssueToken([]byte("secret-a"), "user-123", time.Hour)
	if err != nil {
		t.Fatalf("IssueToken failed: %v", err)
	}

	if _, err := ParseToken([]byte("secret-b"), token); err != ErrInvalidToken {
		t.Fatalf("expected ErrInvalidToken for a token signed with a different secret, got %v", err)
	}
}

func TestParseToken_RejectsExpiredToken(t *testing.T) {
	secret := []byte("test-secret")
	token, err := IssueToken(secret, "user-123", -time.Hour) // already expired
	if err != nil {
		t.Fatalf("IssueToken failed: %v", err)
	}

	if _, err := ParseToken(secret, token); err != ErrInvalidToken {
		t.Fatalf("expected ErrInvalidToken for an expired token, got %v", err)
	}
}

func TestParseToken_RejectsGarbage(t *testing.T) {
	if _, err := ParseToken([]byte("test-secret"), "not-a-jwt"); err != ErrInvalidToken {
		t.Fatalf("expected ErrInvalidToken for a malformed token, got %v", err)
	}
}
