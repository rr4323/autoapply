package store

import "path/filepath"

// AllMigrationFiles returns every .up.sql migration, in apply order, as
// absolute paths under migrationsDir. Used by integration tests (this
// package's and internal/handlers') that need a freshly migrated
// container — kept in one place after the same list drifted out of sync
// across two test files when migration 0006 was added.
//
// Ships in the production binary too (harmless — it's a handful of
// strings, not test-only logic) rather than duplicating this list a
// third time in a non-importable _test.go file.
func AllMigrationFiles(migrationsDir string) []string {
	names := []string{
		"0001_users_profiles.up.sql",
		"0002_episodic_memory.up.sql",
		"0003_ingestion.up.sql",
		"0004_output_and_audit.up.sql",
		"0005_eval_and_mlops.up.sql",
		"0006_profile_fixes.up.sql",
		"0007_semantic_memory.up.sql",
		"0008_auth.up.sql",
		"0009_multitenancy.up.sql",
	}
	paths := make([]string, len(names))
	for i, n := range names {
		paths[i] = filepath.Join(migrationsDir, n)
	}
	return paths
}
