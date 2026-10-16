-- name: CreateProfile :one
INSERT INTO profiles (user_id, base_resume_doc_id, skills, experience_json)
VALUES ($1, $2, $3, $4)
RETURNING *;

-- name: GetProfile :one
SELECT * FROM profiles WHERE id = $1;

-- name: GetProfileByUserID :one
SELECT * FROM profiles WHERE user_id = $1;

-- Profile is a singleton per user (migration 0006's unique index makes
-- this a valid ON CONFLICT target) — PUT /api/v1/profile always upserts,
-- whether or not the user has saved one before.
-- name: UpsertProfileForUser :one
INSERT INTO profiles (user_id, base_resume_doc_id, skills, experience_json)
VALUES ($1, $2, $3, $4)
ON CONFLICT (user_id) DO UPDATE SET
    base_resume_doc_id = EXCLUDED.base_resume_doc_id,
    skills = EXCLUDED.skills,
    experience_json = EXCLUDED.experience_json,
    updated_at = now()
RETURNING *;
