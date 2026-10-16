DROP INDEX IF EXISTS idx_profiles_user_id;
CREATE INDEX idx_profiles_user_id ON profiles(user_id);

ALTER TABLE profiles ALTER COLUMN experience_json SET DEFAULT '{}'::jsonb;
-- Data backfill is intentionally not reversed here — "was always []"
-- and "was reverted from {}" aren't distinguishable after the fact.
