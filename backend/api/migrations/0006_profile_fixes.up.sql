-- Two corrections surfaced while building GET/PUT /api/v1/profile
-- (docs/BACKEND_BUILD_STEPS.md Step 16), against backend/api/openapi.yaml's
-- Profile schema:

-- 1. `experience` is documented as an array of entries, but the column
--    defaulted to an empty JSON *object* ('{}'), not an empty array —
--    unmarshaling that into a Go slice would fail. Conceptually a list,
--    so it should default and backfill to '[]'.
ALTER TABLE profiles ALTER COLUMN experience_json SET DEFAULT '[]'::jsonb;
UPDATE profiles SET experience_json = '[]'::jsonb WHERE experience_json = '{}'::jsonb;

-- 2. openapi.yaml's GET /profile returns a single object, not a list —
--    "profile" is a singleton per user, but nothing enforced that.
--    Replace the plain index with a unique one (also what makes
--    ON CONFLICT (user_id) upsert semantics possible for PUT /profile).
DROP INDEX IF EXISTS idx_profiles_user_id;
CREATE UNIQUE INDEX idx_profiles_user_id ON profiles(user_id);
