-- Minimal — just enough to satisfy the user_id FK in profiles/applications
-- tests. Full users CRUD isn't in Step 13's scope.

-- name: CreateUser :one
INSERT INTO users (email)
VALUES ($1)
RETURNING *;

-- Idempotent upsert-and-return — used at startup to ensure Phase 1's
-- stub demo user (internal/middleware.DefaultStubUserID) exists as a
-- real row, so the applications/profiles FK constraints have something
-- valid to reference. ON CONFLICT DO UPDATE (a no-op re-set) rather than
-- DO NOTHING specifically because DO NOTHING can't RETURNING the
-- existing row.
-- name: EnsureUserByID :one
INSERT INTO users (id, email)
VALUES ($1, $2)
ON CONFLICT (id) DO UPDATE SET email = users.email
RETURNING *;

-- P1 (SaaS pivot, real auth): signup creates a user with a bcrypt hash.
-- name: CreateUserWithPassword :one
INSERT INTO users (email, password_hash)
VALUES ($1, $2)
RETURNING *;

-- name: GetUserByEmail :one
SELECT * FROM users WHERE email = $1;

-- P2 (SaaS pivot, multi-tenancy): looked up once per request by
-- middleware.TenantContext, on the plain (non-RLS) pool — users isn't
-- RLS-protected, so this is safe to run before any tenant context is set.
-- name: GetUserOrganizationID :one
SELECT organization_id FROM users WHERE id = $1;
