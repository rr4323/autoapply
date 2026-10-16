-- name: AppendApplicationEvent :one
INSERT INTO application_events (application_id, event_type, produced_by_agent, payload_json)
VALUES ($1, $2, $3, $4)
RETURNING *;

-- name: ListApplicationEvents :many
SELECT * FROM application_events WHERE application_id = $1 ORDER BY created_at ASC;

-- HasApplicationEvent is the idempotency check (TDD.md §4.2) every
-- consumer runs before acting — Go's counterpart to
-- agentos_agents.common.idempotency.ApplicationEventsIdempotency.already_handled.
-- name: HasApplicationEvent :one
SELECT EXISTS (
    SELECT 1 FROM application_events WHERE application_id = $1 AND event_type = $2
) AS exists;
