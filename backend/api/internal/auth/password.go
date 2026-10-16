// Package auth implements P1 of the SaaS pivot plan: password hashing and
// JWT issuance/verification, replacing the Phase 1 stub user
// (internal/middleware.DefaultStubUserID). Handlers still only ever read
// the user id via middleware.UserIDFromContext — this package only changes
// how that context value gets populated for real requests.
package auth

import "golang.org/x/crypto/bcrypt"

// HashPassword bcrypt-hashes a plaintext password for storage in
// users.password_hash. The default cost (bcrypt.DefaultCost) is
// deliberately not raised here — this is a login-throughput/cost tradeoff
// worth revisiting with real traffic, not a security default to guess at.
func HashPassword(password string) (string, error) {
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", err
	}
	return string(hash), nil
}

// CheckPassword reports whether password matches the given bcrypt hash.
func CheckPassword(hash, password string) bool {
	return bcrypt.CompareHashAndPassword([]byte(hash), []byte(password)) == nil
}
