-- name: ListGeneratedDocumentsForApplication :many
SELECT * FROM generated_documents WHERE application_id = $1 ORDER BY created_at ASC;
