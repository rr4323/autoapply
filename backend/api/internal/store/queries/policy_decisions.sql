-- name: CreatePolicyDecision :one
INSERT INTO policy_decisions (application_id, decision_point, action, reasons_json, rules_version)
VALUES ($1, $2, $3, $4, $5)
RETURNING *;

-- name: ListPolicyDecisionsForApplication :many
SELECT * FROM policy_decisions WHERE application_id = $1 ORDER BY created_at ASC;
