-- name: CreateApplication :one
INSERT INTO applications (user_id, jd_url, jd_text, company, role_title, source)
VALUES ($1, $2, $3, $4, $5, $6)
RETURNING *;

-- name: GetApplication :one
SELECT * FROM applications WHERE id = $1;

-- Scoped by user_id too, not just id — a request for someone else's
-- application by guessed/leaked id must not resolve.
-- name: GetApplicationForUser :one
SELECT * FROM applications WHERE id = $1 AND user_id = $2;

-- name: ListApplicationsByUser :many
SELECT * FROM applications WHERE user_id = $1 ORDER BY created_at DESC;

-- name: ListApplicationsByStatus :many
SELECT * FROM applications WHERE status = $1 ORDER BY created_at DESC;

-- Optional status filter: pass an empty array to mean "no filter." Cast
-- to text[]/text rather than application_status[] — pgx has no default
-- encode plan for a Go slice of a custom enum type, and casting on the
-- Postgres side avoids needing one.
-- Velocity cap input (TDD.md §7.1's velocity_cap_per_day) — counted from
-- Go's own submitted_at record, not anything an agent claims, so the
-- §7.3 enforcement boundary's re-check is independently verifiable.
-- name: CountSubmittedApplicationsToday :one
SELECT count(*) FROM applications
WHERE user_id = $1 AND status = 'submitted' AND submitted_at >= date_trunc('day', now());

-- name: MarkApplicationSubmitted :one
UPDATE applications SET status = 'submitted', submitted_at = now(), updated_at = now()
WHERE id = $1
RETURNING *;

-- name: MarkApplicationNeedsReview :one
UPDATE applications SET status = 'ready_for_review', updated_at = now()
WHERE id = $1
RETURNING *;

-- name: MarkApplicationBelowThreshold :one
UPDATE applications SET status = 'below_threshold', updated_at = now()
WHERE id = $1
RETURNING *;

-- name: ListApplicationsByUserFiltered :many
SELECT * FROM applications
WHERE user_id = $1
  AND (
    cardinality(sqlc.arg(status_filter)::text[]) = 0
    OR status::text = ANY(sqlc.arg(status_filter)::text[])
  )
ORDER BY created_at DESC
LIMIT sqlc.arg(row_limit);
