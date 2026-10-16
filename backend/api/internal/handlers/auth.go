// P1 of the SaaS pivot plan (/home/opstree/.claude/plans/peppy-scribbling-possum.md):
// real signup/login, issuing the JWTs internal/middleware.JWTAuth verifies.
// Deliberately minimal — email+password only, no SSO/MFA/refresh tokens
// (those stay on ENTERPRISE_READINESS.md §1's deferred list at this scale).
package handlers

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/rr4323/autoapply/backend/api/internal/auth"
	"github.com/rr4323/autoapply/backend/api/internal/store"
)

const uniqueViolationCode = "23505"

type signupRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type authResponse struct {
	Token  string `json:"token"`
	UserID string `json:"user_id"`
	Email  string `json:"email"`
}

type AuthHandler struct {
	Queries   *store.Queries
	JWTSecret []byte
}

func NewAuthHandler(q *store.Queries, jwtSecret []byte) *AuthHandler {
	return &AuthHandler{Queries: q, JWTSecret: jwtSecret}
}

// Signup handles POST /api/v1/auth/signup.
func (h *AuthHandler) Signup(w http.ResponseWriter, r *http.Request) {
	var req signupRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json", "request body must be valid JSON")
		return
	}
	req.Email = strings.TrimSpace(strings.ToLower(req.Email))

	if req.Email == "" || !strings.Contains(req.Email, "@") {
		writeJSONError(w, http.StatusBadRequest, "invalid_email", "a valid email is required")
		return
	}
	if len(req.Password) < 8 {
		writeJSONError(w, http.StatusBadRequest, "invalid_password", "password must be at least 8 characters")
		return
	}

	hash, err := auth.HashPassword(req.Password)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to hash password")
		return
	}

	user, err := h.Queries.CreateUserWithPassword(r.Context(), store.CreateUserWithPasswordParams{
		Email:        req.Email,
		PasswordHash: &hash,
	})
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == uniqueViolationCode {
			writeJSONError(w, http.StatusConflict, "email_taken", "an account with this email already exists")
			return
		}
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to create account")
		return
	}

	h.respondWithToken(w, user)
}

// Login handles POST /api/v1/auth/login.
func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	var req loginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json", "request body must be valid JSON")
		return
	}
	req.Email = strings.TrimSpace(strings.ToLower(req.Email))

	user, err := h.Queries.GetUserByEmail(r.Context(), req.Email)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeJSONError(w, http.StatusUnauthorized, "invalid_credentials", "invalid email or password")
			return
		}
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to look up account")
		return
	}

	// A user with no password_hash (e.g. a pre-auth test/demo row created
	// via CreateUser) has no password to check against — never a match.
	if user.PasswordHash == nil || !auth.CheckPassword(*user.PasswordHash, req.Password) {
		writeJSONError(w, http.StatusUnauthorized, "invalid_credentials", "invalid email or password")
		return
	}

	h.respondWithToken(w, user)
}

func (h *AuthHandler) respondWithToken(w http.ResponseWriter, user store.User) {
	token, err := auth.IssueToken(h.JWTSecret, uuidString(user.ID), auth.DefaultTokenTTL)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to issue token")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(authResponse{
		Token:  token,
		UserID: uuidString(user.ID),
		Email:  user.Email,
	})
}
