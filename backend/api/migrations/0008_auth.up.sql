-- P1 (SaaS pivot): real auth replaces the Phase 1 stub user. password_hash
-- is nullable rather than NOT NULL — existing test/demo users created via
-- CreateUser(email) (no password) keep working; only signup-created users
-- ever have a non-null hash, and login requires one.
ALTER TABLE users ADD COLUMN password_hash TEXT;
