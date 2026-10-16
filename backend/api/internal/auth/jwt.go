package auth

import (
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// ErrInvalidToken covers every reason a bearer token is unusable —
// expired, malformed, wrong signature — deliberately not distinguished
// further: the caller's only correct response in every case is 401.
var ErrInvalidToken = errors.New("invalid or expired token")

// DefaultTokenTTL is how long an issued access token stays valid. No
// refresh-token flow exists yet (that's SSO/session-maturity work, out of
// scope per docs/ENTERPRISE_READINESS.md §1's P2 call for Phase 1 scale) —
// a user just logs in again once this expires.
const DefaultTokenTTL = 24 * time.Hour

// IssueToken signs a JWT whose subject is userID, expiring after ttl.
func IssueToken(secret []byte, userID string, ttl time.Duration) (string, error) {
	claims := jwt.RegisteredClaims{
		Subject:   userID,
		IssuedAt:  jwt.NewNumericDate(time.Now()),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(ttl)),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(secret)
}

// ParseToken verifies tokenString's signature and expiry and returns the
// subject (user id) it was issued for.
func ParseToken(secret []byte, tokenString string) (string, error) {
	token, err := jwt.ParseWithClaims(tokenString, &jwt.RegisteredClaims{}, func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, ErrInvalidToken
		}
		return secret, nil
	})
	if err != nil || !token.Valid {
		return "", ErrInvalidToken
	}
	claims, ok := token.Claims.(*jwt.RegisteredClaims)
	if !ok || claims.Subject == "" {
		return "", ErrInvalidToken
	}
	return claims.Subject, nil
}
